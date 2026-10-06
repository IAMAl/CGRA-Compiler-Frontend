#!/usr/bin/env python3
##################################################################
##
##	ElectronNest_CP
##	Copyright (C) 2024  Shigeyuki TAKANO
##
##  GNU AFFERO GENERAL PUBLIC LICENSE
##	version 3.0
##
##################################################################
"""
CGRA Compiler Pipeline Orchestrator

Manages the entire compilation pipeline from LLVM IR to AGU/Datapath code.
Provides error recovery and automatic cleanup of intermediate files.

Usage:
    python pipeline.py --src my_program.ll --output agu_code

Stages:
    1. CFG Node Merging (optional)
    2. Graph Generation (CFG/DFG)
    3. Adjacency Matrix Generation
    4. Path Extraction
    5. Loop Detection
    6. Code Generation (AGU/Datapath)
"""

import glob
import os
import sys
import argparse
import subprocess
import traceback
from typing import List, Optional
from dataclasses import dataclass
from utils.IRNormalize import hoist_constant_geps, strip_debug
from utils.FileConfig import FileNamingConfig, FileCleanup


@dataclass
class StageResult:
    """Result of a pipeline stage execution"""
    stage_name: str
    success: bool
    error_message: Optional[str] = None
    generated_files: List[str] = None
    execution_time: float = 0.0

    def __post_init__(self):
        if self.generated_files is None:
            self.generated_files = []


class PipelineOrchestrator:
    """
    Orchestrates the complete CGRA compilation pipeline.
    Handles error recovery and intermediate file cleanup.
    """

    def __init__(self, source_file: str, output_name: str,
                 source_path: str = ".", output_path: str = ".",
                 cleanup_on_error: bool = True, keep_intermediates: bool = False):
        """
        Initialize pipeline orchestrator.

        Args:
            source_file: LLVM IR source file name (e.g., "program.ll")
            output_name: Base name for output files
            source_path: Directory containing source file
            output_path: Directory for output files
            cleanup_on_error: Clean up intermediate files on error
            keep_intermediates: Keep intermediate files after success
        """
        # A directory in --src belongs to the source path. Keeping it in
        # the file name made every stage prefix its outputs with it, so
        # the intermediates were written under <output>/<that dir>/ and
        # the cleanup sweep deleted whatever else lived there -- given
        # `--src test_mmm/mmm.ll` from the repository, the committed
        # reference files.
        directory, source_file = os.path.split(source_file)
        if directory:
            source_path = os.path.join(source_path, directory)
        self.source_path = os.path.abspath(source_path)
        # `program` is accepted for `program.ll`.
        if (not os.path.exists(os.path.join(self.source_path, source_file))
                and os.path.exists(os.path.join(self.source_path, source_file + '.ll'))):
            source_file += '.ll'
        self.source_file = source_file
        self.output_name = output_name
        self.output_path = os.path.abspath(output_path)
        self.cleanup_on_error = cleanup_on_error
        self.keep_intermediates = keep_intermediates

        # Extract base name without extension
        self.base_name = os.path.splitext(source_file)[0]

        self.config = FileNamingConfig()
        self.cleanup = FileCleanup()

        # Track pipeline state
        self.stage_results: List[StageResult] = []
        self.generated_files: List[str] = []
        # Glob patterns covering every intermediate this run may create.
        # Filled in once the stage base name is known.
        self.intermediate_patterns: List[str] = []
        # The source IR, when --skip-merge had to copy it to the output
        # directory; an intermediate like any other.
        self.copied_source: Optional[str] = None

        # Ensure paths exist
        os.makedirs(self.output_path, exist_ok=True)
        # What the output directory held before this run, with each
        # file's modification time: the cleanup removes only what this
        # run wrote (a new file, or one it rewrote), never a file that
        # merely matches an intermediate's pattern -- a graph rendered
        # from an earlier run's `--keep-intermediates` output, say.
        self.untouched: Dict[str, float] = {}
        for name in os.listdir(self.output_path):
            path = os.path.join(self.output_path, name)
            if os.path.isfile(path):
                self.untouched[name] = os.path.getmtime(path)

    def wrote(self, path: str) -> bool:
        """Whether this run created or rewrote the file."""
        name = os.path.basename(path)
        return name not in self.untouched or os.path.getmtime(path) != self.untouched[name]

    @staticmethod
    def script_cmd(script_name: str) -> List[str]:
        """
        Build the argv prefix that runs one pipeline stage script.

        Uses sys.executable rather than a literal 'python3': on Windows
        there is usually no 'python3' on PATH (the Store stub exits 9009),
        and inside a virtualenv 'python3' would not be the interpreter the
        orchestrator itself is running under. The script is addressed
        absolutely so the pipeline does not depend on the caller's cwd.
        """
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   script_name)
        return [sys.executable, script_path]

    def read_block_names(self, stage_base_name: str) -> List[str]:
        """
        Read the basic block names from the parsed program text.

        Returns an empty list if the file cannot be read; callers then
        simply assert nothing about the per-block outputs rather than
        failing the stage.
        """
        parsed = os.path.join(self.output_path,
                              self.config.parsed_prog(stage_base_name))
        names: List[str] = []
        try:
            with open(parsed, 'r') as f:
                for line in f:
                    if line.startswith('begin bblock '):
                        names.append(line.split(' ', 2)[2].strip())
        except OSError as e:
            print(f"Warning: could not read block names from {parsed}: {e}")
        return names

    def run_stage(self, stage_name: str, command: List[str],
                  expected_outputs: List[str]) -> StageResult:
        """
        Run a single pipeline stage.

        Args:
            stage_name: Name of the stage
            command: Command to execute as list
            expected_outputs: List of expected output files

        Returns:
            StageResult with execution status
        """
        import time

        print(f"\n{'='*60}")
        print(f"Stage: {stage_name}")
        print(f"{'='*60}")
        print(f"Command: {' '.join(command)}")

        start_time = time.time()

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=300  # 5 minute timeout
            )
            # A stage's diagnostics (`Note: ...`) are worth seeing even
            # when it succeeds: a loop that is not carried as a counter,
            # an irreducible cycle nobody reports a loop for.
            for line in completed.stdout.splitlines():
                if line.startswith(('Note:', 'Warning:', 'Error:')):
                    print(f"  {line}")
            # What a stage wrote to stderr on success is a diagnostic too.
            for line in completed.stderr.splitlines():
                if line.strip():
                    print(f"  {line}")

            # Check expected outputs
            missing_files = []
            for file in expected_outputs:
                full_path = os.path.join(self.output_path, file)
                if not os.path.exists(full_path):
                    missing_files.append(file)

            if missing_files:
                error_msg = f"Expected files not generated: {', '.join(missing_files)}"
                print(f"[FAIL] FAILED: {error_msg}")
                return StageResult(
                    stage_name=stage_name,
                    success=False,
                    error_message=error_msg,
                    generated_files=[],
                    execution_time=time.time() - start_time
                )

            # Track generated files
            self.generated_files.extend(expected_outputs)

            exec_time = time.time() - start_time
            print(f"[ OK ] SUCCESS (completed in {exec_time:.2f}s)")
            if expected_outputs:
                print(f"Generated: {', '.join(expected_outputs)}")

            return StageResult(
                stage_name=stage_name,
                success=True,
                generated_files=expected_outputs,
                execution_time=exec_time
            )

        except subprocess.TimeoutExpired:
            error_msg = "Stage execution timed out (>5 minutes)"
            print(f"[FAIL] TIMEOUT: {error_msg}")
            return StageResult(
                stage_name=stage_name,
                success=False,
                error_message=error_msg,
                execution_time=time.time() - start_time
            )

        except subprocess.CalledProcessError as e:
            error_msg = f"Command failed with exit code {e.returncode}"
            print(f"[FAIL] FAILED: {error_msg}")
            if e.stdout:
                print(f"STDOUT:\n{e.stdout}")
            if e.stderr:
                print(f"STDERR:\n{e.stderr}")

            return StageResult(
                stage_name=stage_name,
                success=False,
                error_message=error_msg,
                execution_time=time.time() - start_time
            )

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"[FAIL] ERROR: {error_msg}")
            traceback.print_exc()

            return StageResult(
                stage_name=stage_name,
                success=False,
                error_message=error_msg,
                execution_time=time.time() - start_time
            )

    def run_full_pipeline(self, gen_type: str = 'both',
                         skip_merge: bool = False,
                         branch_leaf_paths: bool = False) -> bool:
        """
        Run the complete compilation pipeline.

        Args:
            gen_type: Type of code generation ('agu', 'datapath', 'both')
            skip_merge: Skip CFG node merging stage
            branch_leaf_paths: Also enumerate every branch-to-leaf path
                per block in stage 4. Nothing downstream reads them and
                their number is exponential in a graph that fans out and
                joins, so they are off unless asked for.

        Returns:
            True if pipeline completed successfully
        """
        try:
            # Stage 1: CFG Node Merging (optional)
            if not skip_merge:
                result = self.run_stage(
                    stage_name="1. CFG Node Merging",
                    command=[
                        *self.script_cmd('mer_cfgnode.py'),
                        '--src_path', self.source_path,
                        '--src_name', self.source_file,
                        '--w_path', self.output_path
                    ],
                    expected_outputs=[self.config.merged_ir(self.base_name)]
                )
                self.stage_results.append(result)
                if not result.success:
                    return False

                # Use merged file for next stages
                source_for_next_stage = self.config.merged_ir(self.base_name)
                # Base name for subsequent stage outputs (merged file base name)
                stage_base_name = f"{self.base_name}_merged"
            else:
                source_for_next_stage = self.source_file
                stage_base_name = self.base_name
                # Every later stage reads its inputs from the output
                # directory, the code generator included: it re-reads the
                # IR from the directory holding the intermediates. With
                # the merge skipped nothing had put the IR there, so
                # stage 6 failed unless the two directories were the same.
                source = os.path.join(self.source_path, self.source_file)
                copied = os.path.join(self.output_path, self.source_file)
                if os.path.abspath(source) != os.path.abspath(copied):
                    # The merge stage also normalises the IR (constant
                    # getelementptr expressions hoisted, debug metadata
                    # dropped); skipping it must not skip that. The copy is
                    # an intermediate the cleanup removes, so it must not
                    # replace a file of the user's.
                    if os.path.exists(copied):
                        raise RuntimeError(
                            f"--skip-merge writes a normalised copy of the source to "
                            f"{copied}, which already exists; remove it or choose another "
                            f"output directory")
                    with open(source) as src, open(copied, 'w') as dst:
                        dst.write(hoist_constant_geps(strip_debug(src.read())))
                    self.copied_source = self.source_file
                else:
                    raise RuntimeError(
                        "--skip-merge needs an output directory other than the source's: "
                        "the normalised copy would overwrite the source")

            # Everything this run writes under the stage base name is an
            # intermediate; the final outputs use self.output_name instead
            # and are protected explicitly during cleanup.
            # The names are escaped: a base name with a glob metacharacter
            # (`[x]`, `*`) is matched literally, not as a pattern.
            escaped = glob.escape(stage_base_name)
            self.intermediate_patterns = [
                f"{escaped}_bblock_*",
                f"{escaped}_cfg*",
                f"{escaped}_dfg*",
                glob.escape(self.config.parsed_prog(stage_base_name)),
            ]
            if not skip_merge:
                # Only a merge this run performed is this run's to remove.
                self.intermediate_patterns.append(glob.escape(self.config.merged_ir(self.base_name)))
            if self.copied_source:
                self.intermediate_patterns.append(glob.escape(self.copied_source))

            # Stage 2a: CFG Generation
            result = self.run_stage(
                stage_name="2a. Control Flow Graph Generation",
                command=[
                    *self.script_cmd('gen_graph.py'),
                    '--src_path', self.output_path,
                    '--src_name', source_for_next_stage,
                    '--w_path', self.output_path,
                    '--gen_type', 'cfg'
                ],
                expected_outputs=[
                    self.config.parsed_prog(stage_base_name),
                    # The next stage reads _cfg.dot; _cfg_r.dot is a
                    # de-duplicated copy nothing downstream consumes, so
                    # checking only that one let a missing _cfg.dot through.
                    self.config.cfg_graph(stage_base_name),
                    self.config.cfg_graph_refined(stage_base_name)
                ]
            )
            self.stage_results.append(result)
            if not result.success:
                return False

            # Stage 2b: DFG Generation
            result = self.run_stage(
                stage_name="2b. Data Flow Graph Generation",
                command=[
                    *self.script_cmd('gen_graph.py'),
                    '--src_path', self.output_path,
                    '--src_name', source_for_next_stage,
                    '--w_path', self.output_path,
                    '--gen_type', 'dfg',
                    '--block', 'yes'
                ],
                # Block names drive every per-block file name from here
                # on; stage 2a wrote the parsed program they come from.
                expected_outputs=[
                    self.config.bblock_dfg(stage_base_name, b)
                    for b in self.read_block_names(stage_base_name)
                ]
            )
            self.stage_results.append(result)
            if not result.success:
                return False

            block_names = self.read_block_names(stage_base_name)

            # Stage 3a: CFG Adjacency Matrix
            # Note: gen_am.py appends _cfg.dot to src_name, so pass stage_base_name (not stage_base_name_cfg)
            # The consumed pair is _am_inv.txt with _node_list.txt, so those
            # are the files whose absence fails the stage.
            result = self.run_stage(
                stage_name="3a. CFG Adjacency Matrix Generation",
                command=[
                    *self.script_cmd('gen_am.py'),
                    '--src_path', self.output_path,
                    '--src_name', stage_base_name,
                    '--w_path', self.output_path,
                    '--gen_type', 'cfg'
                ],
                expected_outputs=[
                    self.config.adjacency_matrix_inv(f"{stage_base_name}_cfg"),
                    self.config.node_list(f"{stage_base_name}_cfg")
                ]
            )
            self.stage_results.append(result)
            if not result.success:
                return False

            # Stage 3b: Per-block DFG Adjacency Matrix Generation
            result = self.run_stage(
                stage_name="3b. Per-block DFG Adjacency Matrix Generation",
                command=[
                    *self.script_cmd('gen_am.py'),
                    '--src_path', self.output_path,
                    '--src_name', stage_base_name,
                    '--w_path', self.output_path,
                    '--gen_type', 'dfg'
                ],
                expected_outputs=[
                    self.config.bblock_am_inv(stage_base_name, b) for b in block_names
                ] + [
                    self.config.bblock_node_list(stage_base_name, b) for b in block_names
                ]
            )
            self.stage_results.append(result)
            if not result.success:
                return False

            # Stage 4: Per-block Path Generation
            result = self.run_stage(
                stage_name="4. Per-block Path Generation",
                command=[
                    *self.script_cmd('gen_path.py'),
                    '--src_path', self.output_path,
                    '--src_name', stage_base_name,
                    '--w_path', self.output_path
                ] + (['--branch_leaf'] if branch_leaf_paths else []),
                expected_outputs=[
                    self.config.bblock_path_ld_ld(stage_base_name, b) for b in block_names
                ] + ([
                    self.config.bblock_path_branch_leaf(stage_base_name, b) for b in block_names
                ] if branch_leaf_paths else [])
            )
            self.stage_results.append(result)
            if not result.success:
                return False

            # Stage 5: Loop Detection
            # Note: det_loop.py outputs w_name + "_loop.txt", so expected is stage_base_name_cfg_loop.txt
            result = self.run_stage(
                stage_name="5. Loop Detection",
                command=[
                    *self.script_cmd('det_loop.py'),
                    '--src_path', self.output_path,
                    '--src_name', f"{stage_base_name}_cfg",
                    '--w_path', self.output_path,
                    '--w_name', f"{stage_base_name}_cfg"
                ],
                expected_outputs=[self.config.cfg_loop(f"{stage_base_name}_cfg")]
            )
            self.stage_results.append(result)
            if not result.success:
                return False

            # Stage 6: Code Generation. gen_prog.py keeps a manifest of the
            # final outputs it wrote under this name and removes, on its
            # next run, the ones it does not write again.
            result = self.run_stage(
                stage_name="6. AGU/Datapath Code Generation",
                command=[
                    *self.script_cmd('gen_prog.py'),
                    '--src_path', self.output_path,
                    '--src_name', f"{stage_base_name}_cfg",
                    '--w_path', self.output_path,
                    '--w_name', self.output_name,
                    '--gen_path', gen_type
                ] + ([] if self.cleanup_on_error else ['--no-cleanup_on_error']),
                # Which arrays exist is only known after analysis, so the
                # datapath is the one name that can be asserted up front.
                expected_outputs=(
                    [self.config.datapath_program(self.output_name)]
                    if gen_type in ('datapath', 'both') else []
                )
            )
            self.stage_results.append(result)
            if not result.success:
                return False

            print(f"\n{'='*60}")
            print("[ OK ] PIPELINE COMPLETED SUCCESSFULLY")
            print(f"{'='*60}")
            return True

        except Exception as e:
            print(f"\n{'='*60}")
            print(f"[FAIL] PIPELINE FAILED: {e}")
            print(f"{'='*60}")
            traceback.print_exc()
            return False

    def cleanup_intermediates(self):
        """
        Clean up intermediate files after successful completion.

        Sweeps by pattern rather than only over self.generated_files: the
        per-block artefacts (per-block dot/AM/path files) are
        never listed as a stage's expected output, so a list-based cleanup
        left the great majority of the intermediates on disk.
        """
        if not self.keep_intermediates:
            print("\nCleaning up intermediate files...")
            removed = 0
            for pattern in self.intermediate_patterns:
                removed += self.cleanup_pattern_excluding_outputs(pattern)
            print(f"  Removed {removed} intermediate file(s)")

    def final_output_names(self) -> set:
        """
        Names that must survive cleanup: the generated AGU/datapath code.

        The manifest lists what code generation wrote, and is read first;
        the globs (with the output name escaped, so `mmm_merged_cfg[x]`
        is the name and not a character class) cover a run that has no
        manifest yet. An unescaped name matched nothing, and every final
        output was then removed as an intermediate.
        """
        outputs = set()
        manifest = os.path.join(self.output_path, self.config.output_manifest(self.output_name))
        if os.path.exists(manifest):
            outputs.add(os.path.basename(manifest))
            with open(manifest) as f:
                outputs.update(line.strip() for line in f if line.strip())
        escaped = glob.escape(self.output_name)
        for pattern in (self.config.agu_program(escaped, '*'),
                        glob.escape(self.config.datapath_program(self.output_name)),
                        glob.escape(self.config.output_manifest(self.output_name))):
            for path in glob.glob(os.path.join(self.output_path, pattern)):
                outputs.add(os.path.basename(path))
        return outputs

    def cleanup_pattern_excluding_outputs(self, pattern: str) -> int:
        """
        Remove files matching pattern, never touching a final output.

        The guard matters when --output shares a prefix with the source
        base name, where a bare glob would delete the results as well.
        """
        protected = self.final_output_names()
        count = 0
        for path in glob.glob(os.path.join(self.output_path, pattern)):
            if os.path.basename(path) in protected or not self.wrote(path):
                continue
            try:
                os.remove(path)
                count += 1
            except OSError as e:
                print(f"Warning: Failed to remove {path}: {e}")
        return count

    def cleanup_on_failure(self):
        """
        Clean up all generated files on pipeline failure.

        The expected outputs of the completed stages are listed in
        generated_files; the per-block artefacts are not, so the same
        pattern sweep as after success is run too. Removing only the
        listed files left most of a failed run on disk.
        """
        if self.cleanup_on_error:
            print("\nCleaning up partial outputs due to failure...")
            results = self.cleanup.cleanup_files(self.generated_files, self.output_path)
            removed = sum(1 for v in results.values() if v is True)
            for pattern in self.intermediate_patterns:
                removed += self.cleanup_pattern_excluding_outputs(pattern)
            print(f"  Removed {removed} partial file(s)")

    def print_summary(self):
        """Print pipeline execution summary"""
        print(f"\n{'='*60}")
        print("PIPELINE SUMMARY")
        print(f"{'='*60}")

        total_time = sum(r.execution_time for r in self.stage_results)
        successful = sum(1 for r in self.stage_results if r.success)
        failed = len(self.stage_results) - successful

        for result in self.stage_results:
            status = "[ OK ]" if result.success else "[FAIL]"
            print(f"{status} {result.stage_name}: {result.execution_time:.2f}s")
            if not result.success and result.error_message:
                print(f"   Error: {result.error_message}")

        print(f"\nTotal stages: {len(self.stage_results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Total execution time: {total_time:.2f}s")


def main():
    """Main entry point for pipeline orchestrator"""
    parser = argparse.ArgumentParser(
        description="CGRA Compiler Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full pipeline for AGU generation
  python pipeline.py --src program.ll --output agu_code --gen agu

  # Generate both AGU and datapath, keep intermediates
  python pipeline.py --src program.ll --output code --gen both --keep-intermediates

  # Skip CFG merging stage
  python pipeline.py --src program.ll --output code --output-path out --skip-merge
        """
    )

    parser.add_argument('--src', required=True, help='Source LLVM IR file')
    parser.add_argument('--output', required=True, help='Output file base name')
    parser.add_argument('--src-path', default='.', help='Source file directory')
    parser.add_argument('--output-path', default='.', help='Output directory')
    parser.add_argument('--gen', choices=['agu', 'datapath', 'both'],
                       default='both', help='Generation type')
    parser.add_argument('--skip-merge', action='store_true',
                       help='Skip CFG node merging stage')
    parser.add_argument('--keep-intermediates', action='store_true',
                       help='Keep intermediate files after success')
    parser.add_argument('--branch-leaf-paths', action='store_true',
                       help='Also enumerate every branch-to-leaf path per block in stage 4 '
                            '(exponential in a graph that fans out and joins; off by default)')
    parser.add_argument('--no-cleanup', action='store_true',
                       help='Do not clean up on error')

    args = parser.parse_args()
    if os.sep in args.output or (os.altsep and os.altsep in args.output):
        parser.error(f"--output names the output files, not a path: {args.output!r} "
                     f"(use --output-path for the directory)")

    # Create orchestrator
    orchestrator = PipelineOrchestrator(
        source_file=args.src,
        output_name=args.output,
        source_path=args.src_path,
        output_path=args.output_path,
        cleanup_on_error=not args.no_cleanup,
        keep_intermediates=args.keep_intermediates
    )

    try:
        # Run pipeline
        success = orchestrator.run_full_pipeline(
            gen_type=args.gen,
            skip_merge=args.skip_merge,
            branch_leaf_paths=args.branch_leaf_paths
        )

        # Print summary
        orchestrator.print_summary()

        if success:
            # Clean up intermediates if requested
            if not args.keep_intermediates:
                orchestrator.cleanup_intermediates()
            sys.exit(0)
        else:
            # Clean up on failure
            orchestrator.cleanup_on_failure()
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        orchestrator.cleanup_on_failure()
        sys.exit(130)

    except Exception as e:
        print(f"\nFatal error: {e}")
        traceback.print_exc()
        orchestrator.cleanup_on_failure()
        sys.exit(1)


if __name__ == "__main__":
    main()
