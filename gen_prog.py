##################################################################
##
##	ElectronNest_CP
##	Copyright (C) 2024  Shigeyuki TAKANO
##
##  GNU AFFERO GENERAL PUBLIC LICENSE
##	version 3.0
##
##################################################################
import os
import sys
import argparse
import traceback
from utils.FileConfig import FileNamingConfig, FileCleanup
import funcs.Analyzer as analyzis
import funcs.Gen_AGU as gen_agu_prog
import funcs.Gen_DataPath as gen_datapath_prog

def verify_paths(src_path, w_path):
    """Verify input/output paths exist"""
    if not os.path.exists(src_path):
        print(f"Error: Source path {src_path} does not exist")
        return False

    if not os.path.exists(w_path):
        try:
            os.makedirs(w_path)
        except OSError as e:
            print(f"Error creating output path {w_path}: {e}")
            return False

    return True

def verify_files(src_path, src_name):
    """Verify required input files exist using centralized config"""
    config = FileNamingConfig()
    required_files = [
        config.cfg_loop(src_name),
        config.node_list(src_name)
    ]

    for f in required_files:
        path = os.path.join(src_path, f)
        if not os.path.exists(path):
            print(f"Error: Required file {f} not found in {src_path}")
            print(f"  Please ensure you have run the previous pipeline stages:")
            print(f"  1. gen_graph.py --gen_type=cfg")
            print(f"  2. gen_am.py --gen_type=cfg")
            print(f"  3. det_loop.py")
            return False

    return True

def replace_outputs(w_path, generated_files, previous, manifest_path, gen_agu, gen_path):
    """
    Rename the `.tmp` programs over the previous run's, drop the ones
    this run did not regenerate, and write the manifest.

    A rename that fails leaves the outputs half replaced; the manifest
    then lists what is actually there -- the renamed programs and the
    previous ones still in place -- so the next run knows what it owns.
    It used to be left as it was, describing the previous run.
    """
    renamed = []
    try:
        for name in generated_files:
            os.replace(os.path.join(w_path, name + '.tmp'), os.path.join(w_path, name))
            renamed.append(name)
    finally:
        if renamed != generated_files:
            present = [name for name in previous if os.path.isfile(os.path.join(w_path, name))]
            with open(manifest_path, 'w') as f:
                f.write('\n'.join(dict.fromkeys(present + renamed)) + '\n')
    regenerated = {name for name in previous
                   if (name.endswith('_agu.ll') and gen_agu) or (name.endswith('_datapath.ll') and gen_path)}
    for name in sorted(regenerated - set(generated_files)):
        stale = os.path.join(w_path, name)
        if os.path.exists(stale):
            os.remove(stale)
            print(f"  Removed (not regenerated): {name}")
    kept = [name for name in previous if name not in regenerated
            and os.path.exists(os.path.join(w_path, name))] + generated_files
    with open(manifest_path, 'w') as f:
        f.write('\n'.join(dict.fromkeys(kept)) + '\n')


if __name__ == "__main__":
    """Main entry point with error recovery"""
    config = FileNamingConfig()
    cleanup = FileCleanup()
    generated_files = []

    # Parsed outside the try block: the handlers below read args, so a
    # failure during parsing used to raise NameError inside the handler
    # and hide the original error.
    parser = argparse.ArgumentParser(description="AGU Generator for ElectronNest")
    parser.add_argument('--src_path', help='Source file path', default='.')
    parser.add_argument('--src_name', help='Source file name', required=True)
    parser.add_argument('--w_path', help='Output file path', default='.')
    parser.add_argument('--w_name', help='Output file name prefix', required=True)
    parser.add_argument('--gen_path', help='agu/datapath/both', default='agu',
                        choices=['agu', 'datapath', 'both'])
    # store_true with default=True could never be switched off, so the
    # documented opt-out did not exist. BooleanOptionalAction adds
    # --no-cleanup_on_error.
    parser.add_argument('--cleanup_on_error', help='Clean up partial outputs on error',
                        action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--debug', help='Print the full traceback on error',
                        action='store_true')
    args = parser.parse_args()

    try:
        if not verify_paths(args.src_path, args.w_path):
            sys.exit(1)

        if not verify_files(args.src_path, args.src_name):
            sys.exit(1)

        if args.gen_path == 'both':
            GEN_AGU = True
            GEN_PATH = True
        elif args.gen_path == 'agu':
            GEN_AGU = True
            GEN_PATH = False
        else:
            GEN_AGU = False
            GEN_PATH = True

        print("Starting pattern analysis...")
        # Pattern analysis
        analyzer = analyzis.Analyzer(args.src_path, args.src_name)
        array_patterns = analyzer.analyze()
        print("Pattern analysis completed")

        # What an earlier run under this output name wrote, from its
        # manifest: those files are replaced, and the ones this run does
        # not write again are removed, so the directory never holds a
        # mixed set. Files this run only regenerates are left to be
        # overwritten; a run that fails before writing changes nothing.
        manifest_path = os.path.join(args.w_path, config.output_manifest(args.w_name))
        previous = []
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                previous = [line.strip() for line in f if line.strip()]
        # A destination that is a directory cannot be replaced by a file;
        # found now, before anything is written, rather than halfway
        # through the renames below.
        for name in os.listdir(args.w_path):
            if os.path.isdir(os.path.join(args.w_path, name)) and (
                    name == config.datapath_program(args.w_name)
                    or (name.startswith(args.w_name + '_') and name.endswith('_agu.ll'))):
                raise RuntimeError(f"{name} in {args.w_path} is a directory, where a program would be written")

        if GEN_AGU:
            print("Starting AGU code generation...")
            # AGU program generation
            agu_generator = gen_agu_prog.AGUGenerator(
                array_patterns, args.src_path, args.src_name
            )
            agu_code = agu_generator.generate()
            if not agu_code:
                raise RuntimeError("the program addresses no memory object")

            # Write AGU code (to temporary names: the previous run's programs
            # stay until every new one is complete, see below)
            for array_name, program in agu_code.items():
                w_file_name = config.agu_program(args.w_name, array_name)
                w_path = os.path.join(args.w_path, w_file_name + '.tmp')
                generated_files.append(w_file_name)

                code = program.get('code')
                if not isinstance(code, list):
                    raise RuntimeError(
                        f"AGU program for '{array_name}' has no code section")
                with open(w_path, 'w') as f:
                    f.write('\n'.join(code))

                print(f"  Generated: {w_file_name}")

            print("AGU Code generation completed successfully")

        if GEN_PATH:
            print("Starting datapath code generation...")
            # Datapath program generation
            datapath_generator = gen_datapath_prog.DataPathGenerator(
                array_patterns, args.src_path, args.src_name
            )
            datapath_code = datapath_generator.ComputeDataPath()

            # Write datapath code
            w_file_name = config.datapath_program(args.w_name)
            w_path = os.path.join(args.w_path, w_file_name + '.tmp')
            generated_files.append(w_file_name)

            code = datapath_code.get('code')
            if not isinstance(code, list):
                raise RuntimeError("Datapath generation produced no code section")
            with open(w_path, 'w') as f:
                f.write('\n'.join(code))

            print(f"  Generated: {w_file_name}")
            print("Datapath Code generation completed successfully")

        # Everything was written: the new programs replace the old ones
        # in one sweep of renames. A failure before this point, or an
        # interruption, leaves only .tmp files to remove -- never the
        # previous run's outputs.
        replace_outputs(args.w_path, generated_files, previous, manifest_path, GEN_AGU, GEN_PATH)

        print(f"\nAll outputs written to: {args.w_path}")
        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        if args.cleanup_on_error and generated_files:
            print("Cleaning up partial outputs...")
            cleanup.cleanup_files([name + '.tmp' for name in generated_files], args.w_path)
        sys.exit(130)

    except Exception as e:
        print(f"\nError during code generation: {e}")
        print(f"Error type: {type(e).__name__}")

        if args.debug:
            print("\nFull traceback:")
            traceback.print_exc()

        # Cleanup on error if requested
        if args.cleanup_on_error and generated_files:
            print("\nCleaning up partial outputs...")
            results = cleanup.cleanup_files([name + '.tmp' for name in generated_files], args.w_path)
            cleaned = sum(1 for v in results.values() if v is True)
            print(f"  Removed {cleaned} partial output file(s)")

        print("\nTo see full error details, run with --debug flag")
        sys.exit(1)
