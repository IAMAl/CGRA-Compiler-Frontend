
# CGRA Compiler Frontend


<div align="center">
  <img src="https://github.com/IAMAl/CGRA-Compiler-Frontend/blob/main/workflow_cgra.png"
       alt="HTML image alt text"
       title="Workflow for Generating Address Generation Program"
       width="550px"
  />
</div>

- input: LLVM IR file
- output: LLVM IR files (address generation programs and a datapath program)

The backend splits one program in two. An **AGU program** walks the loop nest
and produces the addresses for one memory object; a **datapath program** does
the arithmetic, reading the values the AGU programs load and handing back the
values they store. Neither half runs on its own, and together they compute
what the source program computed -- `verify_semantics.py` checks exactly that.

The compilation also carries path and control-flow information that scheduling
can use.


#### 1. Merging Nodes in Control-Flow Graph

Remove branch-only basic blocks (a block whose only instruction is
`br label %X`) and redirect every branch to them. The entry block and any
block a phi node names are kept. Predecessor comments are not reproduced in
the output; the reader ignores them anyway.

- python mer_cfgnode.py --src_name=program
- input: LLVM IR (.ll) file
- output: merged LLVM IR file (`{src_name}_merged.ll`)

`--src_name` accepts either the base name (`program`) or the filename with extension (`program.ll`); the script normalises before reading.

##### Options

- src_path: source file path, default: "."
- w_path: result file path, default: "."


#### 2. Generating Control-Flow and Data-Flow Graphs

- python gen_graph.py --src_name=program_merged.ll --gen_type=cfg|dfg|cdfg
- input: LLVM IR (.ll) file (pass the filename including the `.ll` extension)
- output: Graphviz format (`.dot`) plus the parsed program text (`{base}.txt`)

For multi-block analysis run separate `--gen_type=cfg` and `--gen_type=dfg --block=yes` invocations (the orchestrator and pipeline guide do exactly this); `cdfg` generates both at once.

- gen_type
    - cfg: control-flow graph
    - dfg: data-flow graph
    - cdfg: both control- and data-flow graphs


##### Options

- src_path: LLVM IR source file path, default: "."
- parse=[yes/no]: parsing LLVM IR file, default: "yes"
- nm_mode=[yes/no]: data-flow graph node representation takes mnemonic (in case of "yes"), otherwise instruction is taken, default: "yes"
- unique_id=[yes/no]: assign unique ID-number to graph nod, default: "yes"
- block=[yes/no]: extract data-flow graph for each basic block (in case of "yes"), otherwise entire data-flow graph is extracted, default: "yes"
- w_name: result file name, take same source file name when not specified, default: "None"
- w_path: result file path, default: "."


#### 3. Generating Adjacency Matrix

- python gen_am.py --src_name=program_merged --gen_type=cfg|dfg
- input: `.dot` files from gen_graph.py (CFG: `{src_name}_cfg.dot`; DFG: per-block `{src_name}_bblock_*_dfg.dot`)
- output: adjacency matrix and node-list text files

Two index conventions are emitted and each has its own node list:
`{name}_am_inv.txt` pairs with `{name}_node_list.txt` (this is the pair every
later stage reads), and `{name}_am.txt`, whose rows are reversed, pairs with
`{name}_node_list_inv.txt`. Zero-row removal drops the matching node entries
so the pairs stay aligned.

Each node list line is `<id> <opcode>_<node> <dst> <src1> <src2>...`, the
operands in source order (node 0 is the block's last instruction, so the
list runs backwards through the block). For the CFG the sources are the
block's predecessors, however many there are.

The per-block data-flow matrices are symmetric. The CFG matrix is directed:
`am[i][j] = 1` means block i branches to block j, which is what loop
detection needs (symmetric, a two-block `while` loop is a single edge and
no cycle at all).

Pass the **base name without `_cfg`** — `gen_am.py` appends `_cfg` itself in CFG mode, and iterates over every basic block listed in `{src_name}.txt` for DFG mode.

##### Options

- src_path: source file path, default: "."
- gen_type[cfg/dfg]: generate control-flow graph when "cfg" is specified, otherwise data-flow graph, default: "dfg"
- zero_rm=[yes/no]: remove zero-only rows/columns from the matrix, default: "yes"
- dst_append=[yes/no]: append destination column to node info, default: "yes"
- w_path: result file path, default: "."


#### 4. Generating Data-Flow Path Info for Basic Blocks

- python gen_path.py --src_name=program_merged
- input: per-block adjacency matrices and node lists from `gen_am.py --gen_type=dfg`
- output: per-block path info files (`{src_name}_bblock_*_bpath_*.txt`)

Two path kinds are written per block: `ld_ld` (load to load) and `ld_leaf`
(load to leaf operand). A third, `branch_leaf` (every path from a branch
instruction to a leaf operand), is written only with `--branch_leaf`
(`pipeline.py --branch-leaf-paths`): it enumerates every path, and a
block that fans out and joins repeatedly has exponentially many. They
describe the block's data flow for scheduling; the code generator reads
the IR directly and does not consume them.

Pass the **base name** (no `_cfg`); the script reads `{src_name}.txt` to enumerate blocks and processes each one.

##### Options

- src_path: source file path, default "."
- w_path: result file path, default: "."


#### 5. Loop Detection in Control-Flow Graph

- python det_loop.py --src_name=program_merged_cfg --w_name=program_merged_cfg
- input: CFG adjacency matrix `{src_name}_am_inv.txt` and node list generated by `gen_am.py --gen_type=cfg` (so `--src_name` here must include the `_cfg` suffix)
- output: loop node list (`{w_name}_loop.txt`)

Loops are the natural loops of the directed CFG: for every back edge
`u -> h` (h dominates u), h plus every block that reaches u without passing
h. Each loop is written as its block names, header first, body in control
flow order, latches last, and the loops are listed innermost first. Loops
side by side, nested loops and two-block `while` loops are all found. A
back edge whose target does not dominate its source (an irreducible
cycle) is noted and skipped: its blocks are no loop, and the code
generator treats them as straight-line control flow inside a cycle.

##### Options

- src_path: source file path, default: "."
- w_path: result file path, default: "."
- w_name: output file name prefix (required); writes `{w_name}_loop.txt`


#### 6. Generating Programs

  - python gen_prog.py --src_name=program_merged_cfg --w_name=program --gen_path=both
  - input: CFG adjacency matrix and node list, loop file from det_loop.py, per-block AM/node-list/path-info files from gen_am.py and gen_path.py
  - `--src_name` must include the `_cfg` suffix; `Analyzer` strips it to find the per-block files prefixed with the base name (e.g. `program_merged_bblock_*`).

- AGU Program Generation
  - output: LLVM IR (.ll) file (text file)
  - generates one file per memory object: `{w_name}_{object}_agu.ll`,
    where the object is an array name, or `s<slot>` for a scalar the
    loop touches -- see [What Gets an AGU Program](#what-gets-an-agu-program)

- Datapath Generation
  - output: LLVM IR (.ll) file (text file)
  - generates: `{w_name}_datapath.ll`

##### Options
- src_path: source file path, default: "."
- w_path: result file path, default "."
- w_name: output file name prefix (required)
- gen_path=[both/datapath/agu]: generating type, default "agu"
- cleanup_on_error / no-cleanup_on_error: remove partial outputs if generation fails, default: enabled
- debug: print the full traceback when generation fails

##### Generality

Nothing in the backend is specialised to the example program. Array names,
the number of dimensions, each dimension's size, the element type, and for
every loop its initial value, its compare predicate, its bound and the
instruction each latch advances the counter with are all read from the
input IR. Every AGU program reproduces the source's control flow graph
block for block: a loop header ends in the source's compare, a latch
advances its counter, each counter is initialised in the block the source
initialises it in, and every other block ends the way the source block
does. A conditional branch or a switch inside a loop body decides on a
value the datapath computes, so the datapath emits the compare (or the
selector arithmetic) and the AGU programs branch on it; a loop whose
header tests a loaded value rather than its counter (`while (a[i][k] !=
0)`) works the same way. A subscript is evaluated from its expression:
a counter plus a constant gets a register of its own, anything else
(`b[(k + j) % n][j]`, `b[idx[k]][j]`, `a[i * n + k]`) is computed step by
step by the AGU from counters, literals and values other programs
provide. So loop nests of any depth, several nests one after the other
(even when they reuse the same counter variables), `while` loops whose
body is also the latch, `do ... while` loops of a single block (testing
before or after the update), loops with a `continue` (two latches),
irreducible cycles (no natural loop; their counter is an ordinary
scalar), `if` and `switch` inside the body, bounds, initial values and
steps held in variables (a global, or a local the loop reads), local
arrays (an alloca of array type, an object of its own named `l<slot>`)
and arrays passed in by pointer (`ptr_<param>`, declared without an
extent as `[0 x i32]`) all come out as written. Labels may be numbered or
named, and pointers typed or opaque. `run_regression.py` enforces this.

A scalar parameter (`i32 %n`) is an input the caller supplies, so it
becomes a global the datapath reads once at entry (`@arg_n`), and the
loops bound by it compare against that value. The element and value
types come from the IR, so arrays of `double` are loaded, multiplied
(`fmul`, `fadd`) and compared (`fcmp`) as doubles; casts (`sitofp`,
`sext`, ...), `select` and calls to intrinsics (`@llvm.smax.i32`) are
carried by the datapath as written. A subscript clang folded into a
constant expression (`a[0][3]` inside a load, `a[2][i]` as a
getelementptr base) is hoisted into a getelementptr of its own before
anything parses it, and a `constant` global is a memory object like a
`global` one. A loop whose header decides nothing
about leaving (`for (;;)` with a `break` in its latch, or a header that
branches between two of its own blocks) gets the source terminator, and
a counter read after its latch update is the advanced value `%i<L>_next`
(a store of it in the latch is emitted after the update) -- in the latch,
in a body block the latch goes on to (`k++; if (a[k] > 0) continue;
c[k] = 1;`) and in the block after a loop that leaves from its latch
(`for (;;) { ...; k++; if (k >= n) break; } use(k)`). A block the loop
can enter both before and after the update (`if (a[k]) break; k++; if
(k >= n) break;`) reads the slot again on entry, as `%i<L>_at_<block>`;
the address unit keeps the slot current, so the reload is right either
way. A latch's update adds to the value its block was entered with
(`%i<L>_next_<other latch>` or a reload), not always to the header's
load; a block reached both by skipping a loop and by leaving it
(`i = 0; if (c) { for (; i < n; i++) ... } d[k] = i;`) reloads the slot
too. A store to a counter that every path to its initialisation passes
first (`int k = 0;` at the declaration, `k = 0;` before the loop) is
dead and allowed. Loop detection starts from the function's first
block whatever its label. Loops in sequence over one variable share one
slot in the address units, as they share one variable in the source,
so a block reached from either of them (a `goto` out of the first past
the second) reloads the slot and reads whichever value the path left. A
hoisted constant address (`%cgep<n>`)
never takes a name the source already uses. A block labelled `ret`, a second block named
`entry` (the unlabelled first block is called that), an object and
block whose names would give two streams one register (`a` in block
`loop_retry` and `a_loop` in block `retry`), and an element loaded or
stored as a type other than its own (`*(int *)&a64[i]`) are refused by
name. Parameter
attributes (`i32 noundef %n`, `ptr noundef %a`) are skipped when the
type is read, `int (*a)[N]` is a pointer parameter to rows (its spill
is not an aggregate store), quoted labels (`"for.cond":`) are written
bare (a label that needs its quotes is refused), and `*p` through a
pointer parameter, with no
getelementptr at all, is element 0 of that pointer's object. The first
index of a getelementptr on an address is pointer arithmetic on whatever
the address points at: a row pointer plus i is row i further on, so
`*(*(m + i) + j)` is `m[i][j]`, and only a literal 0 adds nothing (it
used to be dropped whatever it was). On an array itself the leading
index counts whole arrays and must be 0; a step in a type the address
does not point at, and more subscripts than the array has dimensions,
are refused by name.

A loop counter belongs to the address unit from the store that
initialises it to the latches that advance it, so an assignment to it
anywhere else (`i = i * 2` after the loop) is refused rather than
dropped; reading it after its initialisation but before the loop
gives the initial value, and reading it before any initialisation is
refused, since the address unit holds no value for it yet. A
loop that advances its counter in the header rather than a latch
(`do { ...; j++; } while (j < n)`) streams that variable as a scalar,
correctly, and says so in a note; so does a loop whose body assigns
the counter as well (`if (...) i = i + 1;`) or advances it only in a
block that is not a latch, and a global used as a counter,
since a register of one address unit would leave the global stale. A
second loop that continues from the first loop's counter without
initialising it (`for (i = 0; ...) ...; for (; i < n; i++) ...`) is
refused: initialise it explicitly. Two source variables that would get
one object name (`%n.addr` and `%n_addr` both sanitise to `sn_addr`) are
refused too. The datapath emits every operation at the type the IR
wrote on it, so a `long` computed from an `int` counter's initial value
is an `i64` add. What `clang -g` adds -- `!dbg` tails and
`llvm.dbg.declare` calls -- is dropped before anything parses, with
`--skip-merge` as with the merge. A `constant` array's initialiser,
including a string (`c"..."`), is the value the verifier uses for it;
a stage's `Note:` lines (a loop not carried as a counter, an
irreducible cycle) are echoed by the pipeline. A latch that advances the counter
twice (`k++; ...; k++;`) cannot be a single step, so that slot is an
ordinary streamed scalar.
A counter is computed at its slot's type (`long k` gives `i64`
counters, loads, compares and updates, and no widening before the
getelementptr), a header that compares the counter through a cast
(`icmp slt i64 %sext, %n`) widens it the same way, and subscript
arithmetic is done at the source's type, so `i64` products of a
widened counter stay `i64` in the datapath too. A `zext` or `trunc` in
a subscript is kept as written (an `unsigned char` index is `zext`,
never `sext`), and the casts a header applies to its counter before
comparing are repeated in the same order. A cast of a counter is a
value of its own, computed by the datapath, so a store of `(long)i`
stores the datapath's `i64`. The address unit emits a block's streams,
counter initialisations and latch updates in the source's order, so a
value derived from the advanced counter is stored after the update and
a step loaded from memory is loaded before it; a counter read in its
own initialising block, before the header has loaded it, is the
initial value. Fast-math flags on
`fcmp` and `disjoint`/`nneg`/`samesign` on integer operations are
skipped like `nsw`. When no compare names the counter, the slot that
drives an address is taken; an accumulator is never mistaken for one.

What is left is the model's boundary rather than a missing case: one AGU
program per statically named memory object, one function per module. A
pointer that does not resolve to a named object (`int **`, a pointer
loaded from memory, a parameter re-assigned with `a = a + 1` or copied
into a local `int *q = a`), a second function in the module, a call
whose result is unused (side effects the datapath cannot carry; an
aggregate initialiser becomes such a `memcpy`),
`phi` nodes (the pipeline takes clang's `-O0` shape, where values live in
allocas), a block ending in `unreachable`, vector types, a select
between addresses, an aggregate loaded or stored whole, a pointer to a
structure, a call to anything but an LLVM intrinsic, a counter
initialised in two places or only by a latch of another loop that can
be left before it, a local named like a generated counter (`%i1`), and two
objects whose names differ only in case are refused with an error, and
nothing is written for a program that raises.

##### What Gets an AGU Program

An AGU program is generated for each memory object the program loads from
or stores to inside a loop. That includes scalars: a scalar the nest reads
or writes is streamed memory, so it becomes an object of its own (`@s<slot>`
for a local, `@n` for a global `@n`) with its own AGU program. A scalar only
touched outside every loop stays with the datapath, which declares a local
and references a global, and carries its loads and stores. A program whose
loop touches no array at all therefore still gets one AGU program, for its
scalar. A local array (`%t = alloca [24 x i32]`) is an array like any
other, named `@l<slot>` (`@lt`).

`test_noloop/` covers all four ways of mixing arrays and scalars inside and
outside the nest:

| | non-loop uses arrays | non-loop uses scalars |
|---|---|---|
| **loop uses arrays** | `wrapped`, `program` | `scalar_ends` |
| **loop uses scalars** | `array_out_scalar_in` | `scalar_only` |

##### Datapath Block Comments

The datapath file is a flat instruction list. Each block's group is preceded
by a `; block <id>` comment naming the basic block it belongs to, so a group
can be placed against the AGU's control flow even when it references no
address stream at all -- a block that works only on scalar locals.

Scalars the loop never touches have no address stream, so the datapath
declares them itself, in a preamble before the first block comment, and
carries their loads and stores. The preamble also lists the loop counters
the address units own, one `; counter <slot> = %i<level>` line each:
the verifier reads them to check that every scalar of the source is
accounted for, and that each claimed counter really has an address
program keeping it. The block that returns the function's result ends
its group with the `ret`; the datapath is what returns it, once, from
that block.

A global array used bare as an address, as clang writes `a[0]` with
opaque pointers (`load i32, ptr @a`), is normalised to a getelementptr
of its first element like the other folded subscripts. `gen_prog.py`
writes every program to a temporary name and renames them together
once all are complete, so a failure or an interruption during code
generation leaves the previous run's programs untouched. It also
writes `<output>_outputs.txt`, the list of the programs it produced
under that name. On its next run under the same
name it removes the ones it does not write again (only of the kinds it
generates: `--gen datapath` leaves earlier address programs alone), so
a directory never holds a mixed set; a run that fails before writing
leaves the previous outputs in place. A directory sitting where a
program would be written is refused before anything is written, and a
rename that fails halfway leaves a manifest of what is actually there.

##### Register Naming Convention

AGU and Datapath generators use synchronized register naming for memory operations.
Names are keyed by the *address stream*: one stream per distinct getelementptr a
basic block computes for an array, numbered from 0 in source order.

- GEP pointers: `%gep_{array}_{block}_{stream}` (e.g. `%gep_a_22_0`)
- Load registers: `%load_{array}_{block}_{stream}` (e.g. `%load_a_22_0`)
- Sext registers: `%sext_{dim}_{array}_{block}_{stream}` (e.g. `%sext_0_a_22_0`)
- Index offsets: `%off{n}_{level}_{array}_{block}_{stream}` for a subscript
  that adds a constant, as an unrolled `a[i][k+1]` does, and
  `%offm{n}_...` for one that subtracts it, as `a[i][k-1]` does
- Index expressions: `%idx{n}_{array}_{block}_{stream}` for each step of
  any other subscript, evaluated in `i32` before the `sext`
- Casts in a subscript: `%cast{n}_{array}_{block}_{stream}`; a counter
  cast for its compare: `%cmp_i{level}`
- Counters: `%i{level}` (the header's load), `%i{level}_next` (after the
  latch's update; `%i{level}_next_{block}` for a secondary latch),
  `%i{level}_at_{block}` (reloaded on entry to a block the loop reaches
  with different values), `%i{level}_ptr` (the slot), `%cond_i{level}`
- A stream loaded more than once in a block (a scalar read, written and
  read again) numbers its later loads: `%load_{object}_{block}_{stream}_{n}`

A value the datapath computes keeps its source register name; a value an
AGU program stores is named the same way on both sides, so a copy
`b[k][j] = a[i][k]` stores `%load_a_...` in the `b` program.

The stream number is what makes an unrolled loop body work: a block that reads
`a[i][k]` and `a[i][k+1]` computes two addresses and two loads, numbered 0 and 1,
and the datapath feeds each multiply the matching pair. A read-modify-write of one
element is a single stream, so its load and store share an address.

Subscripts appear outermost dimension first, matching the getelementptr chain in
the source, so `a[i][k]` maps dimension 0 to i and dimension 1 to k.

This ensures consistency between AGU programs and the datapath, enabling proper register coordination.


#### 7. Full Pipeline Orchestrator

Runs stages 1–6 end-to-end with error recovery and optional intermediate cleanup.

- python pipeline.py --src=your_source.ll --output=output_prefix
- input: LLVM IR (.ll) file
- output: AGU and/or datapath LLVM IR files (plus intermediates unless cleaned up)

##### Options

- src: source LLVM IR file (required); accepts `program` or `program.ll`.
  A directory component (`test_mmm/mmm.ll`) is taken as part of src-path,
  so the intermediates are named after the file alone.
- output: output file base name (required); a name, not a path (a
  directory goes in output-path)
- src-path: source file directory, default: "."
- output-path: output directory, default: "."
- gen=[agu/datapath/both]: generation type, default: "both"
- skip-merge: skip stage 1 (CFG node merging). Every later stage reads
  from output-path, so the source is copied there (normalised) when the
  two directories differ, and refused when they are the same or when a
  file of the source's name is already there; the copy is an
  intermediate and is cleaned up.
- keep-intermediates: keep intermediate files after success. The
  cleanup removes only files this run wrote (created or rewritten): a
  graph rendered from an earlier run's kept intermediates, though its
  name matches an intermediate's pattern, is left alone.
- branch-leaf-paths: also enumerate every branch-to-leaf path per block in stage 4 (exponential in a graph that fans out and joins; off by default)
- no-cleanup: do not clean up on error

#### Regression Checks

```bash
python run_regression.py
```

Run it after changing anything in `funcs/` or `utils/`. It compiles every
program under `test_mmm/`, `test_unroll/` and `test_noloop/`, plus two copies
of the example generated on the fly -- one with the arrays renamed, one at
16x16 with `i64` elements -- and checks:

- **Reference** the example still produces the outputs committed under `test_mmm/`.
- **Determinism** two runs under different `PYTHONHASHSEED` values agree byte for byte.
- **Generality** no array name, dimension, trip count or element type is assumed.
- **Unrolling** each unrolled copy gets its own address stream, its own offset,
  and its own multiply; odd and even factors both.
- **Products** two matrix products in one nest keep separate streams and stores.
- **Shape** setup and teardown around a nest are generated, and the nest exits
  into the teardown; a program with no loops at all is generated too.
- **Mixing** all four ways of using arrays and scalars inside and outside the nest.
- **Bounds** `c[16][8] = a[16][32] * b[32][8]`: each loop's bound is its own
  trip count and each array keeps its own shape.
- **Start/test** counters that start at 1 and loops tested with `sle`.
- **Negative** an unrolled body reading `a[i][k-1]`, `a[i][k-2]`.
- **While** a two-block inner loop whose body advances the counter itself.
- **Sequential** two nests one after the other, sharing counter variables.
- **Names** named labels and named allocas with an explicit `entry:`.
- **Opaque** the opaque-pointer spelling generates exactly what the typed
  one does.
- **Copy** a body that copies one array into another with no arithmetic.
- **If** / **Switch** a conditional branch, and a switch, inside the body
  on values the datapath computes.
- **Continue** a while loop with two latches. **Do-while** a single-block
  loop that works, advances and then tests.
- **Variables** bounds read from a global and starts read from a local.
- **Local** an array staged through a local array.
- **Expr** / **Indirect** subscripts computed from two counters, and
  loaded from another array.
- **Pointers** arrays passed in as pointer parameters, indexed flat.
- **Step** an inner loop advancing by a global variable.
- **Sentinel** a loop whose header tests a loaded value.
- **Do-pre** a single-block loop comparing before it advances.
- **Irreducible** an inner cycle with two entries and no natural loop.
- **Float** arrays of doubles: `fmul`, `fadd`, an `fcmp` and a `sitofp` of
  the counter. **Parameter** bounds from an integer parameter read from
  `@arg_n`. **Call** / **Select** each product clamped by
  `@llvm.smax.i32`, and by a `select`. **Break** a `for (;;)` inner loop
  whose latch decides on the advanced counter.
- **Linkage** every register the datapath reads is declared by an AGU program
  or the datapath, every register an AGU program reads is declared by some
  AGU program or the datapath, and no file declares a register twice.
- **Semantics** interpreting the AGU programs together with the datapath
  reproduces, element for element, what interpreting the source produces.
  Each AGU program runs in its own register file, and all of them must
  branch to the same block after every block. Only the AGU programs write
  memory (the datapath's stores hand a value over), every value carries
  its declared type and an operand used at another type is an error, and
  integer arithmetic wraps at its width, so a dropped store, a `mul` in
  place of an `fmul` or an unsigned compare of values whose signs differ
  is caught. Every datapath store through an AGU address is matched to
  the AGU program's store of the same value through the same address,
  so a hand-off that is missing, duplicated or misdirected fails, and
  the scalars the datapath carries itself are compared with the
  source's. The datapath owns no memory: a load or store through an
  address it computed itself is an error, the address programs run to
  the `ret void` of their final block, and an element only one side
  wrote is compared against the value the other side's array was filled
  with. An address program streams the one object it is named after,
  through `%gep_`/`%load_` registers of that object in the block they
  name, and stores only what the datapath sent, a counter, a literal or
  its own load; a slot holds nothing until it is stored, nothing follows
  a terminator, a `%load_` register shared between programs must be a
  load, every counter a program keeps has a `; counter` line, every
  program has an object of the source's, and the datapath returns --
  `ret void` too -- from the block the programs end from. The input
  arrays are filled from a hash of the array's name and the subscripts,
  so no two arrays and no shifted view of one hold the same values, and
  a seed (`verify_semantics.py SOURCE OUT PREFIX SEED`) varies the fill
  so data-dependent branches are taken both ways across runs; a seed
  starting with `wide` fills -50..50 so compares against larger literals
  go both ways too. A `%load_` or `%i` register an address program
  stores or the datapath sends must be a real load or counter, a load
  is consumed only in the block that loaded it, the datapath touches no
  scalar an address program streams, a pointer's array is read only
  within what the source touched, and an `extern` scalar gets a fill
  value. A source that itself runs past an array under a fill (a
  sentinel the fill did not plant) is reported as such, with exit code
  3, not as a verdict. The suite checks this by breaking the mmm output
  on purpose and asserting the reason the verifier gives.
- **Valid IR** every test input is accepted by `llvm-as`, so the front
  end only ever sees files clang could have written (skipped, with a
  note, when no `llvm-as` is installed).
- **Types** an all-`i64` copy of the example (counters included) and a
  header comparing its counter through `sext` compile and verify; the
  verifier also refuses an access outside an array's declared extent,
  compares named scalar slots (`%sum`) as well as numbered ones, and
  `phi`, atomic accesses and `unreachable` are refused
  with a message rather than mis-parsed.
- **Scale** a block of 1500 chained operations and a straight line of
  1500 blocks compile within the suite's per-stage timeout (300 s): the path search, the
  adjacency matrices and the block ordering are linear or quadratic
  where they used to be cubic or recursive.
- **Rounds two to ten** the cases the later reviews added: cast kinds
  kept (`zext`/`trunc`), source-order emission in a latch, hand-off
  matching, constant-expression addresses, pointer arithmetic (element
  and row pointers), counters read after a latch exit and reloaded where
  the path decides, latches that add to the value they were entered
  with, loops skipped by a branch, dead stores before an initialisation,
  loops found from a first block not named `entry`, external scalars,
  verifier oracle mutations (wrong array, leading
  subscript, dropped scalar, dropped initialisation, return value,
  counter claims, one owner, the datapath's own addresses, another
  program's object, non-stream addresses, computed store values, the
  final block, instructions past a terminator, fill values, a void
  datapath that does not return), narrow
  counters, reads before a loop, `switch` on i1, initialised arrays,
  operations typed from the IR, global counters, `!dbg` and `#dbg_`
  records, the datapath's own `ret`, refusals by name (addresses as
  values, calls returning addresses, empty loops, flattened matrices, a
  parameter stored into another's slot, globals holding addresses,
  quoted function names), bare and decayed global arrays, objects named
  `@LEAFS` or `%LEAF`, output names with glob metacharacters, the
  output manifest and the rename sweep, and `--skip-merge`.
- **Attributes / Ownership / Deref / Late use** the cases above:
  attributed parameters, a counter assigned outside its loop, a counter
  updated twice per latch, `*p` on a pointer parameter, and a store of
  the advanced counter in the latch.

The variants are generated, so other shapes are easy to add:

```bash
python test_unroll/gen_mmm.py --size 24 --factor 1 --out test_unroll/mmm24_unroll1.ll
python test_unroll/gen_mmm.py --size 24 --factor 3 --out test_unroll/mmm24_unroll3.ll
python test_unroll/gen_mmm.py --size 24 --factor 4 --out test_unroll/mmm24_unroll4.ll
python test_unroll/gen_mmm.py --size 24 --products 2 --out test_unroll/mmm24_two.ll
python test_unroll/gen_mmm.py --size 24 --between --out test_unroll/mmm24_between.ll
python test_unroll/gen_mmm.py --size 24 --products 2 --between --factor 2 \
       --out test_unroll/mmm24_mixed.ll
python test_unroll/gen_mmm.py --shape 16,8,32 --out test_unroll/mmm_shape.ll
python test_unroll/gen_mmm.py --size 24 --start 1 --le --out test_unroll/mmm24_start.ll
python test_unroll/gen_mmm.py --size 24 --factor 3 --minus --out test_unroll/mmm24_minus3.ll
python test_unroll/gen_mmm.py --size 24 --while --out test_unroll/mmm24_while.ll
python test_unroll/gen_mmm.py --size 24 --sequential --out test_unroll/mmm24_seq.ll
python test_unroll/gen_mmm.py --size 24 --names --out test_unroll/mmm24_names.ll
python test_unroll/gen_mmm.py --size 24 --opaque --out test_unroll/mmm24_opaque.ll
python test_unroll/gen_mmm.py --size 24 --copy --out test_unroll/mmm24_copy.ll
python test_unroll/gen_mmm.py --size 24 --if --out test_unroll/mmm24_if.ll
python test_unroll/gen_mmm.py --size 24 --switch --out test_unroll/mmm24_switch.ll
python test_unroll/gen_mmm.py --size 24 --continue --out test_unroll/mmm24_continue.ll
python test_unroll/gen_mmm.py --size 24 --do --out test_unroll/mmm24_do.ll
python test_unroll/gen_mmm.py --size 24 --variables --out test_unroll/mmm24_variables.ll
python test_unroll/gen_mmm.py --size 24 --local --out test_unroll/mmm24_local.ll
python test_unroll/gen_mmm.py --size 24 --expr --out test_unroll/mmm24_expr.ll
python test_unroll/gen_mmm.py --size 24 --indirect --out test_unroll/mmm24_indirect.ll
python test_unroll/gen_mmm.py --size 24 --ptr --out test_unroll/mmm24_ptr.ll
python test_unroll/gen_mmm.py --size 24 --vstep --out test_unroll/mmm24_vstep.ll
python test_unroll/gen_mmm.py --size 24 --sentinel --out test_unroll/mmm24_sentinel.ll
python test_unroll/gen_mmm.py --size 24 --dopre --out test_unroll/mmm24_dopre.ll
python test_unroll/gen_mmm.py --size 24 --irreducible --out test_unroll/mmm24_irreducible.ll
python test_unroll/gen_mmm.py --size 24 --float --if --out test_unroll/mmm24_float.ll
python test_unroll/gen_mmm.py --size 24 --param --out test_unroll/mmm24_param.ll
python test_unroll/gen_mmm.py --size 24 --call --out test_unroll/mmm24_call.ll
python test_unroll/gen_mmm.py --size 24 --select --out test_unroll/mmm24_select.ll
python test_unroll/gen_mmm.py --size 24 --break --out test_unroll/mmm24_break.ll
```

To compare one program against its generated code on its own:

```bash
python verify_semantics.py test_mmm/mmm.ll OUTPUT_DIR mmm
python verify_semantics.py test_mmm/mmm.ll OUTPUT_DIR mmm second   # another fill of the inputs
```

#### Example / Test Data

`test_mmm/` contains a 32×32 integer matrix-multiply (`mmm.ll`) plus the full
set of pipeline outputs as a regression reference. Every input is valid
LLVM IR: `test_unroll/renumber.py` puts unnamed values in textual order
the way `llvm-as` demands, the generator applies it to its output, and
it can be run on a hand-edited file.

`test_unroll/` varies the loop nest, all 24×24 so an odd and an even unroll
factor both divide evenly:

| file | shape |
|---|---|
| `mmm24_unroll1/3/4.ll` | inner loop unrolled 1x, 3x, 4x |
| `mmm24_between.ll` | a value computed between two nesting levels, read by the innermost |
| `mmm24_two.ll` | two matrix products in one nest |
| `mmm24_mixed.ll` | all three at once |
| `mmm_shape.ll` | `c[16][8] = a[16][32] * b[32][8]`: three trip counts, three shapes |
| `mmm24_start.ll` | counters start at 1, loops test `sle 23` |
| `mmm24_minus3.ll` | inner loop unrolled 3x reading `k`, `k-1`, `k-2`, k from 2 |
| `mmm24_while.ll` | inner loop as a two-block `while`, the body advancing k |
| `mmm24_seq.ll` | two nests in sequence, `c = a*b` then `f = d*e`, sharing i, j, k |
| `mmm24_names.ll` | `entry:`, `for.cond.i:` and friends, `%i` `%j` `%k` allocas |
| `mmm24_opaque.ll` | the unrolled-1x program with `ptr` instead of `i32*` |
| `mmm24_copy.ll` | the body copies `a[i][k]` into `c[i][j]`, no arithmetic |
| `mmm24_if.ll` | the product is accumulated only when `a[i][k] > 0` |
| `mmm24_switch.ll` | `k % 3` selects add, subtract or nothing |
| `mmm24_continue.ll` | a `while` inner loop skipping odd k with `k++; continue;` |
| `mmm24_do.ll` | a single-block `do ... while` inner loop |
| `mmm24_variables.ll` | bounds from global `@n`, starts from a local |
| `mmm24_local.ll` | `a[i][k]` staged through a local array `t[k]` |
| `mmm24_expr.ll` | `b[(k + j) % 24][j]` |
| `mmm24_indirect.ll` | `b[idx[k]][j]` with `idx[k] = (5 k) % 24` written just before |
| `mmm24_ptr.ll` | `kernel(i32* a, i32* b, i32* c)` indexing `a[i * 24 + k]` |
| `mmm24_vstep.ll` | the inner loop steps by global `@step` (2) |
| `mmm24_sentinel.ll` | inner loop `while (a[i][k] != 0)` |
| `mmm24_dopre.ll` | `do { ... } while (k++ < 23)`: compare before update |
| `mmm24_irreducible.ll` | two alternating inner blocks, entered at either by `j % 2` |
| `mmm24_float.ll` | `double` arrays, `if (a[i][k] > 0.0) c += a * b + (double)k` |
| `mmm24_param.ll` | `kernel(i32 %n)` with every loop bounded by `n` |
| `mmm24_call.ll` | each product clamped with `@llvm.smax.i32(p, 0)` |
| `mmm24_select.ll` | each product clamped with `select i1 (p > 0), p, 0` |
| `mmm24_break.ll` | `for (;;) { if (a[i][k] > 0) ...; if (++k >= 24) break; }` |

`test_noloop/` varies the shape around the nest. Five of its inputs are
generated (`straight.ll` is clang's output for a program with no loop):

```bash
python test_unroll/gen_mmm.py --size 24 --straight --out test_noloop/wrapped.ll
python test_unroll/gen_mmm.py --size 24 --scalar --out test_noloop/scalar_ends.ll
python test_unroll/gen_mmm.py --size 24 --scalar --loop-scalar --out test_noloop/scalar_only.ll
python test_unroll/gen_mmm.py --size 24 --straight --loop-scalar \
       --out test_noloop/array_out_scalar_in.ll
python test_unroll/gen_mmm.py --size 24 --straight --products 2 --between --factor 2 \
       --out test_noloop/program.ll
```

| file | shape |
|---|---|
| `straight.ll` | no loops at all, literal subscripts |
| `wrapped.ll` | straight-line setup, nest, teardown, joined through an array |
| `program.ll` | the same at size: 3 levels, 2x unrolled, two products, an inter-level value, 8 arrays |
| `scalar_ends.ll` | setup and teardown use only a scalar local |
| `array_out_scalar_in.ll` | arrays outside the nest, scalars inside |
| `scalar_only.ll` | scalars everywhere, no array in the program |

To reproduce the committed reference outputs:

```bash
python pipeline.py --src=mmm.ll --output=mmm \
                   --src-path=test_mmm --output-path=/tmp/out \
                   --keep-intermediates
```

The four final outputs are `mmm_a_agu.ll`, `mmm_b_agu.ll`, `mmm_c_agu.ll`, and `mmm_datapath.ll`. The synthetic register names in the datapath file (`%load_<object>_<block>_<stream>`, `%gep_<object>_<block>_<stream>`) are declared in the corresponding AGU files — see [Register Naming Convention](#register-naming-convention).

For deeper detail (per-stage breakdown, error recovery, custom-script integration), see [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md).
