# CGRA Compiler Pipeline Guide

## Overview

The CGRA compiler frontend has been enhanced with:
- **Centralized file naming configuration** - Eliminates hardcoded file names
- **Automatic error recovery** - Cleans up partial outputs on failure
- **Pipeline orchestrator** - Single-command execution of entire pipeline

---

## Quick Start

### Option 1: Use Pipeline Orchestrator (Recommended)

Run the entire pipeline with a single command:

```bash
python pipeline.py --src my_program.ll --output agu_code --gen agu
```

This will automatically:
1. Merge CFG nodes
2. Generate CFG and DFG graphs
3. Create adjacency matrices
4. Extract data flow paths
5. Detect loops
6. Generate AGU code

### Option 2: Manual Stage Execution

Run each stage individually (for debugging or customization). Each stage's
output is the input for the next, so the base name evolves: `program` →
`program_merged` after Stage 1, then stays `program_merged` until Stage 6
where you choose the final output prefix.

```bash
# Stage 1: Merge CFG nodes (optional)
#   Accepts `program` or `program.ll` for --src_name.
python mer_cfgnode.py --src_name=program.ll
#   → produces program_merged.ll

# Stage 2: Generate graphs (use the merged IR)
python gen_graph.py --src_name=program_merged.ll --gen_type=cfg
python gen_graph.py --src_name=program_merged.ll --gen_type=dfg --block=yes
#   → produces program_merged_cfg.dot, program_merged_bblock_*_dfg.dot, etc.

# Stage 3a: CFG adjacency matrix
#   gen_am.py appends _cfg to --src_name in CFG mode, so pass the merged
#   base name (without _cfg).
python gen_am.py --src_name=program_merged --gen_type=cfg
#   → produces program_merged_cfg_am.txt, program_merged_cfg_node_list.txt

# Stage 3b: Per-block DFG adjacency matrices
#   gen_am.py iterates over blocks read from program_merged.txt.
python gen_am.py --src_name=program_merged --gen_type=dfg
#   → produces program_merged_bblock_<id>_am.txt etc. for every block

# Stage 4: Per-block path generation (consumes Stage 3b outputs)
python gen_path.py --src_name=program_merged
#   → produces program_merged_bblock_<id>_bpath_*.txt
#     (ld_ld, ld_leaf; branch_leaf only with --branch_leaf)

# Stage 5: Loop detection (consumes Stage 3a output)
python det_loop.py --src_name=program_merged_cfg --w_name=program_merged_cfg
#   → produces program_merged_cfg_loop.txt

# Stage 6: Code generation
#   --src_name is the *_cfg base (Analyzer strips _cfg to find the per-block
#   files). --w_name is the prefix used in the final outputs.
python gen_prog.py --src_name=program_merged_cfg --w_name=program --gen_path=both
#   → produces program_<array>_agu.ll and program_datapath.ll
```

If you skip the merge stage, use `program` (instead of `program_merged`)
as the base name for all subsequent stages.

---

## Pipeline Orchestrator Reference

### Basic Usage

```bash
python pipeline.py --src SOURCE.ll --output OUTPUT_NAME [OPTIONS]
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--src FILE` | Source LLVM IR file; a directory part is added to `--src-path` | *required* |
| `--output NAME` | Output file base name | *required* |
| `--src-path DIR` | Source directory | `.` |
| `--output-path DIR` | Output directory | `.` |
| `--gen TYPE` | Generation type: `agu`, `datapath`, `both` | `both` |
| `--skip-merge` | Skip CFG node merging stage (the source is copied to the output directory, normalised as the merge would: constant getelementptr expressions hoisted, debug metadata dropped) | `false` |
| `--keep-intermediates` | Keep intermediate files after success | `false` |
| `--no-cleanup` | Do not clean up files on error | `false` |
| `--branch-leaf-paths` | Also enumerate every branch-to-leaf path per block in stage 4 (exponential in a graph that fans out and joins) | `false` |

### Examples

**Generate AGU code only:**
```bash
python pipeline.py --src matrix_mult.ll --output mm_agu --gen agu
```

**Generate both AGU and datapath, keep intermediate files:**
```bash
python pipeline.py --src program.ll --output code \
  --gen both --keep-intermediates
```

**Use custom paths:**
```bash
python pipeline.py --src program.ll --output result \
  --src-path ./inputs --output-path ./outputs
```

**Skip CFG merging (if already merged; the output directory must differ
from the source's, since the normalised copy is written there, and must
not already hold a file of the source's name):**
```bash
python pipeline.py --src program_merged.ll --output code --output-path build --skip-merge
```

---

## Error Recovery Features

### Automatic Cleanup on Failure

When a pipeline stage fails, the orchestrator automatically:
1. Prints detailed error information
2. Cleans up partial/corrupted output files
3. Exits with appropriate error code

**Example error output:**
```
Stage: 3a. CFG Adjacency Matrix Generation
[FAIL] FAILED: Expected files not generated: program_cfg_am_inv.txt

Cleaning up partial outputs due to failure...
  Removed 35 partial file(s)
...
[FAIL] 3a. CFG Adjacency Matrix Generation: 0.00s
   Error: Expected files not generated: program_cfg_am_inv.txt
```

The files each stage is checked for are the ones the next stage reads:
`_am_inv.txt` with `_node_list.txt`, the per-block `_dfg.dot`, `_am_inv.txt`,
`_node_list.txt` and `_bpath_ld_ld.txt` files (`_bpath_branch_leaf.txt` too
when `--branch-leaf-paths` is given), the loop file, and the datapath
program.

Cleanup on failure sweeps the same intermediate patterns as cleanup after
success, so a failed run leaves nothing behind but the source (and, with
`--skip-merge`, nothing at all in the output directory).

Status markers are ASCII: the previous ✅/❌ raised UnicodeEncodeError on a
cp932 console, so the failure report crashed instead of printing.

### Manual Cleanup

The intermediates of a run are every file in the output directory that
starts with the stage base name (`program_merged` after a merge, `program`
with `--skip-merge`) other than the final outputs:

```bash
python pipeline.py --src program.ll --output code --keep-intermediates
# ... inspect ...
rm program_merged.ll program_merged.txt program_merged_cfg* program_merged_bblock_*
```

### Disable Cleanup (for debugging)

```bash
# Keep all files even on error
python pipeline.py --src program.ll --output code --no-cleanup
```

---

## File Naming Configuration

### Centralized Configuration

File naming conventions live in `utils/FileConfig.py`. The orchestrator and
`gen_prog.py` use it; the individual stage scripts still build some names
inline.

```python
from utils.FileConfig import FileNamingConfig

config = FileNamingConfig()

# Get file names using configuration
merged_file = config.merged_ir('program')            # 'program_merged.ll'
cfg_file = config.cfg_graph('program')               # 'program_cfg.dot'
# The consumed matrix is _am_inv.txt, paired with _node_list.txt
am_file = config.adjacency_matrix_inv('program_cfg') # 'program_cfg_am_inv.txt'
# cfg_loop appends '_loop.txt', so pass the name including '_cfg'
loop_file = config.cfg_loop('program_cfg')           # 'program_cfg_loop.txt'
agu_file = config.agu_program('output', 'arr')       # 'output_arr_agu.ll'
```

### Benefits

1. **No hardcoded strings** - All filenames generated programmatically
2. **Easy to change conventions** - Modify once in `FileConfig.py`
3. **Consistent across stages** - No mismatches between producer/consumer
4. **Self-documenting** - Method names clearly indicate file purpose

### Updating Your Code

**Before (hardcoded):**
```python
output_file = f"{name}_cfg_loop.txt"  # Easy to make mistakes
```

**After (centralized):**
```python
from utils.FileConfig import FileNamingConfig
config = FileNamingConfig()
output_file = config.cfg_loop(f'{name}_cfg')  # Consistent
```

---

## Pipeline Stages

### Stage 1: CFG Node Merging
**Purpose:** Remove unnecessary nodes in LLVM IR control-flow graph
- **Input:** LLVM IR (.ll)
- **Output:** Merged LLVM IR
- **Optional:** Can be skipped with `--skip-merge`

### Stage 2: Graph Generation
**Purpose:** Generate control-flow and data-flow graphs
- **Input:** LLVM IR
- **Output:** GraphViz (.dot) files, parsed program (.txt)
- **Modes:** CFG, DFG, or both (CDFG)

### Stage 3: Adjacency Matrix Generation
**Purpose:** Convert graphs to adjacency matrix representation
- **Input:** GraphViz (.dot) files
- **Output:** Adjacency matrix (.txt), node lists (.txt)

### Stage 4: Path Extraction
**Purpose:** Extract data-flow paths for basic blocks
- **Input:** Adjacency matrices
- **Output:** Path information files (.txt): `ld_ld`, `ld_leaf`, and with
  `--branch-leaf-paths` the exponential `branch_leaf` enumeration

### Stage 5: Loop Detection
**Purpose:** Find the natural loops of the directed control-flow graph
- **Input:** CFG adjacency matrix and node list
- **Output:** Loop node list (.txt), innermost loop first, each loop
  header first and latch last

### Stage 6: Code Generation

**Purpose:** Generate AGU and/or datapath programs

- **Input:** All previous stage outputs
- **Output:** LLVM IR (.ll) for AGU/datapath

#### AGU/DataPath Register Naming Convention

Both AGU and DataPath generators use synchronized register naming to ensure consistency:

| Register Type | Naming Pattern | Example |
|--------------|----------------|---------|
| Load result | `%load_{array}_{block}_{stream}` | `%load_a_22_0` |
| GEP pointer | `%gep_{array}_{block}_{stream}` | `%gep_a_22_0` |
| Sign extend | `%sext_{dim}_{array}_{block}_{stream}` | `%sext_0_a_22_0` |
| Index offset | `%off{n}_{level}_{array}_{block}_{stream}` | `%off1_3_a_22_1` |
| Negative offset | `%offm{n}_{level}_{array}_{block}_{stream}` | `%offm1_3_a_22_1` |
| Index expression | `%idx{n}_{array}_{block}_{stream}` | `%idx0_b_22_0` |
| Cast in a subscript | `%cast{n}_{array}_{block}_{stream}` | `%cast0_a_5_0` |
| Counter for its compare | `%cmp_i{level}` (`%cmp{n}_i{level}` for a chain) | `%cmp_i3` |
| Advanced counter | `%i{level}_next` (`%i{level}_next_{block}` for a secondary latch) | `%i3_next` |
| Counter reloaded on entry | `%i{level}_at_{block}` (a block entered before and after the update, or by skipping the loop and by leaving it) | `%i2_at_25` |
| Counter slot | `%i{level}_ptr` (an alloca in every address program; loops in sequence over one variable share the first one's) | `%i3_ptr` |
| Loop condition | `%cond_i{level}` | `%cond_i3` |
| Repeated load in a block | `%load_{object}_{block}_{stream}_{n}` (a scalar read, written and read again) | `%load_s5_11_0_1` |
| Hoisted constant address | `%cgep{n}` (in the normalised IR; never a name the source uses) | `%cgep0` |

`stream` numbers the distinct addresses a block computes for an array, from 0
in source order, so an unrolled body gets one stream per access. A
read-modify-write of the same element is one stream. Subscripts are listed
outermost dimension first, matching the getelementptr chain.

**Example AGU output (`result_a_agu.ll`):**

```llvm
22:
  %sext_0_a_22_0 = sext i32 %i1 to i64
  %sext_1_a_22_0 = sext i32 %i3 to i64
  %gep_a_22_0 = getelementptr inbounds [32 x [32 x i32]], ... @a, i64 0, i64 %sext_0_a_22_0, i64 %sext_1_a_22_0
  %load_a_22_0 = load i32, i32* %gep_a_22_0, align 4
```

**A 2x unrolled body (`test_unroll/`) gets a second stream:**

```llvm
  %sext_0_a_22_1 = sext i32 %i1 to i64
  %off1_3_a_22_1 = add i32 %i3, 1
  %sext_1_a_22_1 = sext i32 %off1_3_a_22_1 to i64
  %gep_a_22_1 = getelementptr inbounds [32 x [32 x i32]], ... @a, i64 0, i64 %sext_0_a_22_1, i64 %sext_1_a_22_1
  %load_a_22_1 = load i32, i32* %gep_a_22_1, align 4
```

**Matching DataPath output (`result_datapath.ll`):**

The file is a flat instruction list, so a `; block <id>` comment names the
basic block each group belongs to. Scalar slots the datapath owns are declared
in a preamble before the first block comment.

Operands are in source order, so a `sub` or `sdiv` comes out the way the
source wrote it; loads are listed in the order the arithmetic first uses
them. Only arithmetic whose result reaches a store, or the AGU, is emitted:
address arithmetic (`k + 1` feeding a getelementptr) and a latch's counter
update are the AGU's, and are left out. What the AGU takes from the
datapath is the condition of an `if` inside a loop body (emitted as an
`icmp`), the selector of a `switch`, and a subscript, bound, start or step
the datapath computes; the AGU programs then branch on, switch on,
compare against or store that register by name. A bound or start the
source merely loads from a variable is not the datapath's: that variable
is a memory object with an AGU program of its own, and the other AGU
programs read its `%load_` register directly. Types follow
the IR: an array of `double` is loaded and combined with `fmul`/`fadd`,
compared with `fcmp`, and casts (`sitofp i32 %i3 to double`), `select`
and calls to intrinsics (`call i32 @llvm.smax.i32(...)`) are emitted as
the source wrote them. A scalar parameter of the function is read from an
external global named after it (`%n = load i32, i32* @arg_n`), and a
counter read after its latch update is the AGU's `%i<L>_next` -- in the
latch, in the body blocks the latch goes on to, and after a loop that
leaves from its latch; a block entered both before and after the update
reads `%i<L>_at_<block>`, which the AGU loads from the slot on entry. A
stream that uses the advanced value (`k++; d[k] = k;`) is emitted after
the update. The block that returns ends its datapath group with the
source's `ret`, `ret void` included, so the verifier sees where the
program ends. A datapath
store through an AGU address (`store i32 %45, i32* %gep_c_22_0`) hands
the value to the AGU program that performs the store; the datapath
writes memory only for the scalars it owns (the verifier fails a
datapath that loads or stores through an address it computed itself).
Counters are typed by their
slot: a `long` counter is an `i64` from its alloca to its compare, and
a subscript that the source computed at `i64` is computed at `i64`. A
`zext` or `trunc` in a subscript is emitted as such (`%cast0_a_5_0 =
zext i8 %load_idx_5_0 to i64`); a `sext` is implicit, the address unit
widens with it where a wider operand is needed. Within a block the
address unit keeps the source's order: each stream's address at its
first access, each load and store where the source has it, and the
counter's initialisation and latch update where their stores are.

```llvm
; block 22
%load_a_22_0 = load i32, i32* %gep_a_22_0, align 4
%load_b_22_0 = load i32, i32* %gep_b_22_0, align 4
%load_c_22_0 = load i32, i32* %gep_c_22_0, align 4
%37 = mul i32 %load_a_22_0, %load_b_22_0
%45 = add i32 %load_c_22_0, %37
store i32 %45, i32* %gep_c_22_0, align 4
```

With the inner loop unrolled twice, each multiply takes its own pair of streams:

```llvm
%37 = mul i32 %load_a_22_0, %load_b_22_0
%52 = mul i32 %load_a_22_1, %load_b_22_1
%53 = add i32 %37, %52
%61 = add i32 %load_c_22_0, %53
store i32 %61, i32* %gep_c_22_0, align 4
```

This naming convention enables:

- **Register coordination** between AGU and DataPath
- **Dynamic naming** based on analysis (not hardcoded)
- **Multi-object support** with unique identifiers per object, block and stream

---

## Troubleshooting

### Pipeline fails at graph generation
**Problem:** `gen_graph.py` cannot find source file

**Solution:**
```bash
# Check file exists
ls -l my_program.ll

# Use absolute paths
python pipeline.py --src program.ll \
  --src-path /absolute/path/to/source \
  --output-path /absolute/path/to/output
```

### Missing required files
**Problem:** `gen_prog.py` cannot find `*_cfg_loop.txt`

**Solution:**
Ensure all previous stages completed successfully:
```bash
# Run with --keep-intermediates to inspect
python pipeline.py --src program.ll --output code --keep-intermediates

# Check which files were generated
ls -l *.txt *.dot
```

### Out of memory during adjacency matrix generation
**Problem:** Large graphs cause memory issues

**Solution:**
```bash
# Process blocks individually instead of using orchestrator
# See manual execution steps above
```

### Want to see detailed error messages
**Problem:** Error messages too brief

**Solution:**
```bash
# Add --debug flag (for gen_prog.py); --src_name carries the _cfg suffix
python gen_prog.py --src_name=program_merged_cfg --w_name=out --debug

# Or check Python traceback in pipeline output
```

---

## Advanced Usage

### Custom Pipeline Scripts

Create custom pipeline scripts using the file configuration:

```python
from utils.FileConfig import FileNamingConfig, FileCleanup
import subprocess
import sys

config = FileNamingConfig()
cleanup = FileCleanup()

base_name = "my_program"
generated_files = []

try:
    # Stage 1
    # sys.executable, not 'python3': on Windows there is usually no
    # 'python3' on PATH, and inside a virtualenv it would not be this
    # interpreter.
    cmd = [sys.executable, 'gen_graph.py',
           '--src_name', f'{base_name}.ll',
           '--gen_type', 'cfg']
    subprocess.run(cmd, check=True)

    expected_file = config.cfg_graph(base_name)
    generated_files.append(expected_file)

    # More stages...

except subprocess.CalledProcessError:
    # Clean up on error
    cleanup.cleanup_files(generated_files, '.')
    raise
```

### Integration with Build Systems

**Makefile example:**
```makefile
SRC = program.ll
OUT = agu_code

all: $(OUT)_agu.ll

$(OUT)_agu.ll: $(SRC)
	python pipeline.py --src $(SRC) --output $(OUT) --gen agu

clean:
	rm -f *_merged.ll *_cfg*.* *_dfg*.* *_am*.* *_node_list*.* \
	      *_bpath*.* *_loop.txt *_agu.ll *_datapath.ll

.PHONY: all clean
```

**CMake example:**
```cmake
add_custom_command(
    OUTPUT ${PROJECT_BINARY_DIR}/agu_code_agu.ll
    COMMAND python ${CMAKE_SOURCE_DIR}/compiler/llvm/pipeline.py
            --src program.ll
            --output agu_code
            --gen agu
            --output-path ${PROJECT_BINARY_DIR}
    DEPENDS program.ll
    COMMENT "Generating AGU code"
)
```

---

## API Reference

### FileNamingConfig Class

```python
class FileNamingConfig:
    # Stage outputs
    @staticmethod
    def merged_ir(base_name: str) -> str
    @staticmethod
    def cfg_graph(base_name: str) -> str
    @staticmethod
    def adjacency_matrix(base_name: str) -> str
    @staticmethod
    def cfg_loop(base_name: str) -> str
    @staticmethod
    def agu_program(output_name: str, array_name: str) -> str
    @staticmethod
    def datapath_program(output_name: str) -> str
    # ... and one method per intermediate file: parsed_prog, cfg_graph_refined,
    # dfg_graph, bblock_dfg, adjacency_matrix_inv, node_list,
    # node_list_inv, bblock_am, bblock_am_inv, bblock_node_list,
    # bblock_node_list_inv, bblock_path_ld_ld, bblock_path_ld_leaf,
    # bblock_path_branch_leaf (see utils/FileConfig.py).
```

### FileCleanup Class

```python
class FileCleanup:
    @staticmethod
    def cleanup_files(
        file_paths: List[str],
        base_path: str = "."
    ) -> Dict[str, bool]
```

`cleanup_files` removes the named files and reports, per file, whether
it existed; the pipeline builds the list from `FileNamingConfig`.

---

## Migration from Old Scripts

### Updating Existing Scripts

**Step 1:** Import the new modules
```python
from utils.FileConfig import FileNamingConfig
config = FileNamingConfig()
```

**Step 2:** Replace hardcoded filenames
```python
# Old
output = f"{name}_cfg_loop.txt"

# New
output = config.cfg_loop(name)
```

**Step 3:** Add error recovery
```python
from utils.FileConfig import FileCleanup
cleanup = FileCleanup()

try:
    # Your code here
    pass
except Exception:
    cleanup.cleanup_files(generated_files, output_path)
    raise
```

### Backward Compatibility

Old scripts continue to work unchanged; the stage scripts are what the
orchestrator itself calls.

---

## Performance Considerations

- **Pipeline orchestrator** adds the cost of one Python start-up per stage
- **Manual execution** is slightly faster but requires tracking files manually
- **Intermediate file cleanup** removes the per-block graph, matrix and path
  files, which for a large block are most of the output

---

## Support

For issues, questions, or contributions:
- Check existing issues: https://github.com/IAMAl/ElectronNest/issues
- Report bugs with full error output and pipeline stage
- Include LLVM IR sample if possible

---

## License

GNU AFFERO GENERAL PUBLIC LICENSE version 3.0

Copyright (C) 2024 Shigeyuki TAKANO
