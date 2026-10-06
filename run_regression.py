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
Regression checks for the CGRA compiler frontend.

Run from this directory:

    python run_regression.py

These properties are checked, each of which has been broken before:

  A. Reference   the mmm example still produces the outputs committed
                 under test_mmm/.
  B. Determinism two runs under different PYTHONHASHSEED values produce
                 byte-identical output. Set iteration order used to leak
                 into the emitted instruction order.
  C. Names       the same program with the arrays renamed produces the
                 same code modulo the names. Array-name matching used to
                 be hard-coded to a/b/c, which silently emptied the
                 datapath for every other program.
  D. Shape/type  a 16x16 i64 version of the same program produces i64
                 instructions and a bound of 16. Dimensions, trip counts
                 and element types used to default to mmm's 32 / i32.
  E. Unrolling   inner loops unrolled 1x, 3x and 4x yield one address
                 stream per copy, offsets 1..factor-1, an index that
                 advances by the factor, and one multiply per copy on its
                 own pair of loads. Odd and even factors are both covered
                 because an odd one leaves an odd number of products to
                 reduce. Naming a stream by (array, block) alone made the
                 unrolled copies collapse onto one register.
  F. Linkage     every register the datapath reads is defined either in
                 the datapath itself or in one of the AGU programs, every
                 register an AGU program reads is defined in some AGU
                 program or in the datapath, and no file defines a
                 register twice.
                 The AGU side used to go unchecked, so a copy `b = a`
                 whose store named the source register passed.
  G. Semantics   interpreting the AGU programs together with the datapath
                 reproduces, element for element, what interpreting the
                 source produces, with every AGU program branching to the
                 same block after every block. Missing loop back edges
                 once made the generated code run each loop body exactly
                 once; and with all AGU programs sharing one register
                 file, a wrong bound in any but the last file went
                 unnoticed.
  H. Inter-nest  a value computed between two nesting levels and consumed
                 by the innermost one is generated and connected. The
                 producing instruction used to be dropped because its
                 immediate operand was discarded, leaving the store that
                 used it referring to nothing.
  I. Products    two matrix products in one nest keep their own address
                 streams and their own store. The datapath used to pair
                 every store with the last computation in the block, so
                 one accumulator was written with the other's result and
                 the second store was lost.
  J. No loops    a straight-line program still gets an AGU program per
                 array and a datapath. Blocks were enumerated from the
                 loop file alone, so a program without loops was analysed
                 as if it were empty and produced no output at all.
  K. Whole shape a program shaped like an ordinary one -- straight-line
                 setup, a loop nest, straight-line teardown, joined by
                 data dependencies -- keeps all three parts. Only loop
                 members were emitted, so both ends were dropped and the
                 outermost loop branched straight to ret.
  L. Scalar ends the same shape with no array outside the nest at all:
                 the setup and teardown work on a scalar local, which the
                 nest reads. A block with no array access was left out of
                 the AGU's control flow, and its scalar loads and stores
                 had nowhere to be emitted.
  M. Mixing      arrays and scalars in and out of the loop nest, all four
                 ways round. What decides whether an AGU program exists is
                 whether the loop loads and stores, scalars included: a
                 scalar the nest touches is streamed memory and gets its
                 own AGU program, and a program with no array at all still
                 gets one for its scalar.
  N. Shape       c[16][8] = a[16][32] * b[32][8]: each loop's bound is its
                 own trip count and each array is declared with its own
                 shape. Bounds used to be taken from the array dimension
                 mapped to the level, and that mapping was reversed, so
                 every non-square program addressed out of bounds.
  O. Start/test  counters that start at 1 and loops that test `sle`. The
                 initial value and the predicate used to be hard-coded to
                 0 and `slt`, so such a loop ran the wrong iterations.
  P. Negative    an unrolled body reading a[i][k-1], a[i][k-2]. A `sub`
                 in a subscript used to be dropped silently, emitting a
                 getelementptr one index short of the array's rank.
  Q. While       an inner loop of two blocks, the body advancing the
                 counter and branching back to the compare. Loop
                 detection ran on a symmetric adjacency matrix, so a
                 two-block cycle was a single edge and not a loop.
  R. Sequential  two loop nests one after the other sharing their counter
                 variables. The analyzer stacked every loop into one
                 nest, and a counter slot could belong to one loop only.
  S. Names       named labels and named allocas, with an explicit
                 `entry:` label. The reader took any line containing
                 `entry` for a function definition.
  T. Opaque      the same program written with opaque pointers (`ptr`)
                 generates exactly what the typed-pointer program does.
                 getelementptr was parsed by counting tokens, so `ptr`
                 shifted every operand.
  U. Copy        a body that copies a[i][k] into c[i][j] with no
                 arithmetic. The AGU stored the source register verbatim,
                 and the path walker indexed an empty list.
  V. If          a conditional branch inside the body on a loaded value:
                 the datapath computes the compare and the AGU programs
                 branch on it.
  W. Switch      a switch inside the body on a computed value, with a
                 fall-through default and an empty join block.
  X. Continue    a while loop with two latches, only one of which does
                 the loop's work; both advance the counter.
  Y. Do-while    a single-block loop that works, advances and then tests.
  Z. Variables   loop bounds read from a global and starts read from a
                 local, neither a literal.
  AA. Local      a[i][k] staged through a local array t[k]: a
                 getelementptr on an alloca, a memory object of its own.
  AB. Expr       b[(k + j) % K][j]: a subscript computed from two counters
                 and a literal, evaluated by the AGU.
  AC. Indirect   b[idx[k]][j]: a subscript loaded from another array.
  AD. Pointers   the arrays are pointer parameters indexed flat; an
                 object of unknown extent, declared [0 x i32].
  AE. Step       the innermost loop advances by a global variable.
  AF. Sentinel   `while (a[i][k] != 0)`: a loop whose header decides on
                 a loaded value; the datapath computes the compare.
  AG. Do-pre     a single-block loop comparing the counter before it is
                 advanced.
  AH. Irreducible an inner cycle of two alternating blocks with two
                 entries: no natural loop, its counter a plain scalar.
  AI. Float      arrays of doubles: fmul/fadd, an fcmp, and a sitofp of
                 the counter, all typed from the IR.
  AJ. Parameter  the bounds come from an integer parameter, read from
                 the input global @arg_n.
  AK. Call       each product clamped by @llvm.smax.i32, a call the
                 datapath carries and the verifier evaluates.
  AL. Select     each product clamped by a select.
  AM. Break      a for(;;) inner loop: its header branches between two
                 of its own blocks and the latch decides on the advanced
                 counter, %i3_next, which the datapath compares.
  AN. Valid IR   every test input is accepted by llvm-as. The generated
                 inputs numbered their values out of order, so the front
                 end had never seen a file clang could have written.
                 Skipped, with a note, when no llvm-as is installed.
  AO. Attributes a parameter list with clang's attributes (`i32 noundef
                 %n`, `ptr noundef %a`) is read as the same program.
  AP. Ownership  a counter assigned outside its initialisation and its
                 latches is refused rather than dropped; two updates in
                 one latch make the slot a plain scalar.
  AQ. Deref      `*p` through a pointer parameter, with no getelementptr,
                 is element 0 of that object.
  AR. Late use   a store of the advanced counter in the latch comes out
                 after the update that defines %i3_next.
  AS. Verifier   the semantic check fails when the AGU's store, or the
                 datapath's, is deleted, and when an operation's type is
                 changed.
  AT. i64        the example with every i32 made i64, counters included:
                 the AGU keeps the counters at i64 and needs no sext.
  AU. Cast cmp   a header comparing its counter through a sext: the
                 counter is still the counter, widened for the compare.
  AV. Refusals   phi, an atomic access and unreachable are refused with
                 a message naming them.
  AW. Extent     the verifier refuses an access outside an array's
                 declared extent instead of reading a zero (listed under
                 AS, as every verifier mutation is).
  AX. Named      a named scalar slot (%sum) is compared like a numbered
                 one; it used to be taken for an empty array.
  AY. Generator  option combinations that produced invalid or
                 out-of-range programs are refused; --ptr honours the
                 unroll offsets, and --sentinel follows --float's type.
  AZ. Scale      a block of 1500 chained operations and a straight line
                 of 1500 blocks compile and verify.
  BA. Casts      a zext index (unsigned char) and a zext of an i1 are
                 zext in the AGU, not sext; a sext of a counter stored
                 as i64 is the datapath's, at i64.
  BB. Order      a latch's streams come out in source order: a store of
                 a value derived from the advanced counter follows the
                 update, a step read from memory precedes it (--vstep),
                 a counter read in its own init block is the init value,
                 and a[k+1][k+1] defines its offset once.
  BC. Pointers   a re-assigned pointer parameter, a pointer copied into
                 a local, a second function and a value used outside
                 the block defining it are refused by name.
  BD. Hand-off   the verifier fails when the datapath's store is
                 deleted, sent through the wrong address, or when a
                 datapath-owned scalar is changed (listed under AS).
  BE. Constants  a literal subscript folded into a constant expression
                 (`a[0][3]` in a load, `a[2][i]` as a getelementptr base)
                 and a `constant` global compile and verify.
  BF. Pointers   pointer arithmetic chained on a parameter, `(p + 2)[i]`,
                 addresses element i + 2; a function-pointer parameter
                 does not hide the parameters after it.
  BG. Verifier   more mutations the verifier must notice: a datapath
                 group for a block no AGU program has, an AGU load of
                 the wrong type, a literal spelled for the wrong type
                 (listed under AS).
  BH. Paths      the branch-to-leaf enumeration is off by default and
                 written when gen_path.py is given --branch_leaf.
  BI. Oracle     the verifier notices a load from the wrong array of
                 the same shape, a leading subscript that steps past the
                 array, a dropped datapath scalar and a missing return
                 value (listed under AS).
  BJ. Edges      a narrow counter widened before an offset is added
                 (`signed char i; a[i + 100]`), a counter read before
                 its loop (refused by name), a counter re-assigned in
                 its init block, and an unreachable block after a return.
  BK. Model      a `switch` on an i1, a `constant` array with an
                 initialiser (its values, not the pattern, are used), a
                 local array's extent (a mutation outside it fails), and
                 a `do { j++ } while (j < n)` loop whose counter is
                 streamed as a scalar with a note saying so.
  BL. Types      the datapath emits each operation at the type the IR
                 wrote on it (`long t = i + 3` is an i64 add; an i64
                 parameter multiplies at i64), an initial value loaded
                 from an array reaches the datapath under the AGU's name,
                 a global used as a loop counter is streamed and written
                 back, metadata tails (`, !annotation !6`) are dropped,
                 and `--skip-merge` normalises the IR like the merge does.
  BM. Refusals   a second loop starting from the first loop's final
                 counter without initialising it, two source slots
                 that would share one object name, and a call passing
                 an address are refused by name.
  BN. Details    a `while (*p < 10) *p += 1` loop (a store through a
                 pointer is no counter update), a `notail call`, a
                 string-initialised `constant` array, the return value
                 computed in the returning block (a mutation moving it
                 fails), `--sentinel --factor 4` refused, the pipeline
                 echoing a stage's notes, `--skip-merge` leaving a
                 stale merged file alone, and an undeclared global
                 scalar refused.
  BO. Results    the function's result is returned by the datapath:
                 `return i * 2`, `return (int)t` and `return c[3]` are
                 computed in the returning block; a datapath that returns
                 something else, or claims a counter no address program
                 keeps, or writes a scalar an address program streams, or
                 that the source names `@.str`, fails the verifier.
  BP. Refusals   an address compared as a value, `ptrtoint`, a select
                 between addresses and a global named like a parameter's
                 input are refused by name.
  BQ. Round five  a three-dimensional initialiser with zero rows inside
                 non-zero ones, a call's result type read from unusual
                 call heads, LLVM 19 `#dbg_` records dropped, an earlier
                 run's address programs removed before code generation,
                 and `--sentinel` refused when `--start` or the factor
                 would let the probe run past the array.
  BR. Round six  an address returned by a call or by the function is
                 refused; the verifier fails when the datapath returns
                 from another block, returns where the source is void,
                 declares a scalar an address program streams, or claims
                 a counter for a slot the source has not; gen_prog keeps
                 a manifest so `--gen datapath` after `--gen agu` keeps
                 the address programs, a failing run keeps the previous
                 outputs, and `--skip-merge` will not overwrite a file.
  BS. fneg       `a[i] = -a[i]` on doubles: the datapath carries the
                 negation as `fneg`, and the datapath file holds no empty
                 block groups.
  BT. Round seven a global array used bare as an address (opaque
                 pointers: `load i32, ptr @a` for `a[0]`) is element 0;
                 arrays and locals named `@brick` or `%payload` do not
                 look like branches or loads; a failing code generation
                 leaves the previous outputs and no temporary files; the
                 verifier fails when the datapath reads memory under a
                 name other than the address unit's, when an address
                 program borrows another's counter, and when the
                 datapath declares a counter.
  BU. Round seven, continued
                 `*(a + i)` on a global with the decay folded away is
                 element i; a flattened matrix is refused by name; an
                 empty loop of one or two blocks is refused; a `--sentinel`
                 probe that would run past the array (`--minus` at factor
                 3 on 20, or a `--start` past it) is refused; a deleted
                 output drops out of the manifest.
  BV. Round eight `*(*(m + i) + j)`, a row pointer stepped by i, is
                 m[i][j] (the leading index used to be dropped whatever
                 it was); a leading index past the array, a row pointer
                 stepped as another type and too many subscripts are
                 refused by name; objects named `@LEAFS` and `%LEAF` are
                 not leaves; an output name with a glob metacharacter
                 keeps its outputs; the verifier fails when the datapath
                 stores through an address of its own, when the address
                 programs' final block stores, when a store of 0 into a
                 pointer's array is dropped from both sides, and when a
                 counter's slot is an object another program streams;
                 `*p += 1` through the parameter register itself is an
                 element access; a parameter stored into another's slot,
                 a global holding an address and a quoted function name
                 are refused by name; code generation refuses a directory
                 where a program goes before writing, and a rename that
                 fails halfway leaves a manifest of what is there.
  BW. Round nine  a counter read after the loop leaves from its latch
                 (`k++; if (k >= n) break;`), or in a body block after
                 the update, is the advanced value, and a block entered
                 both before and after the update reads the slot again;
                 an ambiguous stream register name, a block labelled
                 `ret` or a second `entry`, and an element accessed as
                 another type are refused by name; a hoisted address
                 never takes a name in use; `*p` then `p[1]` on one
                 pointer compiles; the D copy is verified; the verifier
                 fails when an address program touches another object,
                 stores through a non-stream address, stores what it
                 computed, moves a store to another block, reads a slot
                 nobody stored, runs past a terminator, launders a counter
                 through a %load_ name, keeps an unclaimed counter, has
                 no object, or when the datapath of a void function does
                 not return where the programs end; the if variant
                 verifies under a second fill; every integer and
                 floating-point operation is verified end to end; a
                 select between addresses, a vector type, an aggregate
                 access, a structure pointer, a counter initialised in
                 two places and a local named `%i1` are refused by name.
  BX. Round ten   a latch entered after another latch's update, or with
                 the counter reloaded, adds to that value; a block
                 reached by skipping a loop reloads the counter; a dead
                 store before the initialisation is allowed; loops are
                 found from the function's first block whatever its
                 label; an external scalar is streamed; loops in
                 sequence over one variable share a slot, so a block
                 reached from either (a goto past the second) reloads
                 it; a counter initialised only by a bypassable latch
                 and a call to a non-intrinsic are refused by name; the verifier fails when an address
                 program stores what it computed under a %load_ name,
                 when a load is read outside its block, when the
                 datapath touches a streamed scalar, and when a
                 pointer's array is read past the source's footprint;
                 the if variant verifies under a wide fill; a sentinel
                 source out of range under a fill is reported as such.
"""
import ast
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'test_unroll'))
from renumber import renumber  # noqa: E402
TEST_DIR = os.path.join(HERE, 'test_mmm')
UNROLL_DIR = os.path.join(HERE, 'test_unroll')
NOLOOP_DIR = os.path.join(HERE, 'test_noloop')
FINAL_OUTPUTS = ['mmm_a_agu.ll', 'mmm_b_agu.ll', 'mmm_c_agu.ll', 'mmm_datapath.ll']


# A stage or a verification that runs longer than this has regressed in
# complexity, whatever it would eventually print.
STAGE_TIMEOUT = 300


def run_verifier(source, out_dir, prefix, seed=None):
    """(returncode, output) of verify_semantics.py, a timeout counting as a failure."""
    try:
        result = subprocess.run([sys.executable, os.path.join(HERE, 'verify_semantics.py'),
                                 source, out_dir, prefix] + ([seed] if seed else []), capture_output=True, text=True,
                                cwd=HERE, timeout=STAGE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return 1, f'verification did not finish within {STAGE_TIMEOUT} s'
    return result.returncode, result.stdout + result.stderr


def run_pipeline(out_dir, src_dir, base, out_name, seed='0'):
    """Run the whole pipeline; return True on success."""
    ok, text = run_stages(out_dir, src_dir, base, out_name, seed)
    if not ok:
        print(text)
    return ok


def run_stages(out_dir, src_dir, base, out_name, seed='0'):
    """Run the whole pipeline; return (ok, the failing stage's output)."""
    os.makedirs(out_dir, exist_ok=True)
    env = dict(os.environ, PYTHONHASHSEED=seed)
    stages = [
        ('mer_cfgnode.py', ['--src_path', src_dir, '--src_name', f'{base}.ll',
                            '--w_path', out_dir]),
        ('gen_graph.py', ['--src_path', out_dir, '--src_name', f'{base}_merged.ll',
                          '--w_path', out_dir, '--gen_type', 'cfg']),
        ('gen_graph.py', ['--src_path', out_dir, '--src_name', f'{base}_merged.ll',
                          '--w_path', out_dir, '--gen_type', 'dfg', '--block', 'yes']),
        ('gen_am.py', ['--src_path', out_dir, '--src_name', f'{base}_merged',
                       '--w_path', out_dir, '--gen_type', 'cfg']),
        ('gen_am.py', ['--src_path', out_dir, '--src_name', f'{base}_merged',
                       '--w_path', out_dir, '--gen_type', 'dfg']),
        ('gen_path.py', ['--src_path', out_dir, '--src_name', f'{base}_merged',
                         '--w_path', out_dir]),
        ('det_loop.py', ['--src_path', out_dir, '--src_name', f'{base}_merged_cfg',
                         '--w_path', out_dir, '--w_name', f'{base}_merged_cfg']),
        ('gen_prog.py', ['--src_path', out_dir, '--src_name', f'{base}_merged_cfg',
                         '--w_path', out_dir, '--w_name', out_name,
                         '--gen_path', 'both']),
    ]
    logs = []
    for script, args in stages:
        try:
            result = subprocess.run([sys.executable, os.path.join(HERE, script)] + args,
                                    capture_output=True, text=True, env=env, cwd=HERE,
                                    timeout=STAGE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return False, f"    stage {script} did not finish within {STAGE_TIMEOUT} s"
        if result.returncode != 0:
            # A crash prints its traceback to stderr; showing stdout alone
            # left the reason for the failure invisible.
            return False, f"    stage {script} failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
        logs.append(result.stdout)
    # On success the stages' output is returned too, for the notes a
    # check may look for.
    return True, '\n'.join(logs)


def read(path):
    """File contents with line endings normalised."""
    with open(path, 'r') as f:
        return f.read().replace('\r\n', '\n')


def instructions(path):
    """Just the instructions: comments and blank lines dropped."""
    return chr(10).join(line for line in read(path).splitlines()
                        if line.strip() and not line.lstrip().startswith(';'))


def definitions_and_uses(path):
    """(defined registers, duplicated definitions, used registers) of one file."""
    defined, duplicated, used = set(), set(), []
    for line in read(path).splitlines():
        code = line.split(';')[0]
        match = re.match(r'\s*(%[-\w.$]+)\s*=', code)
        if match:
            if match.group(1) in defined:
                duplicated.add(match.group(1))
            defined.add(match.group(1))
        operands = code.split('=', 1)[-1] if '=' in code else code
        # Branch targets are labels, not registers.
        operands = re.sub(r'label\s+%[-\w.$]+', '', operands)
        used += re.findall(r'%[-\w.$]+', operands)
    return defined, duplicated, list(dict.fromkeys(used))


def check_linkage(out_dir, prefix, label, failures):
    """
    The AGU programs and the datapath share a register namespace: the AGU
    declares %gep_/%load_ names the datapath consumes, and the datapath
    computes values the AGU stores. Verify that every name resolves in
    both directions and that no file defines a register twice. Each AGU
    program carries its own %i<level> registers, so a name may be
    defined once per file.
    """
    datapath = os.path.join(out_dir, f'{prefix}_datapath.ll')
    if not os.path.exists(datapath):
        check(f'F linkage     {label}: no datapath', False, failures)
        return

    agu = {os.path.basename(path): definitions_and_uses(path)
           for path in sorted(glob.glob(os.path.join(out_dir, f'{prefix}_*_agu.ll')))}
    dp_defined, dp_duplicated, dp_used = definitions_and_uses(datapath)
    agu_defined = set().union(*(defined for defined, _, _ in agu.values()))

    duplicated = set(dp_duplicated)
    for _, dups, _ in agu.values():
        duplicated |= dups
    undefined = [r for r in dp_used if r not in agu_defined and r not in dp_defined]
    # An AGU program may read another AGU program's load (a bound held
    # in a scalar the loop touches) as well as the datapath's values --
    # but not another program's counters or addresses.
    for name, (defined, _, used) in agu.items():
        undefined += [f'{name}:{r}' for r in used
                      if r not in defined and r not in dp_defined
                      and not (r.startswith('%load_') and r in agu_defined)]

    check(f'F linkage     {label}: no duplicate definitions',
          not duplicated, failures)
    check(f'F linkage     {label}: every register defined',
          not undefined, failures)
    if duplicated or undefined:
        print(f"      duplicated={sorted(duplicated)} undefined={undefined}")


def assembler():
    """An llvm-as on PATH, any version, or None."""
    candidates = ['llvm-as'] + [f'llvm-as-{v}' for v in range(20, 10, -1)]
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    return None


def assembles(tool, path):
    """(ok, first error line) of running llvm-as on one file."""
    # LLVM 14 reads opaque pointers only when asked; later versions
    # reject the flag, so it is a retry rather than the default.
    plain = None
    for flags in ([], ['-opaque-pointers']):
        result = subprocess.run([tool] + flags + ['-o', os.devnull, path],
                                capture_output=True, text=True)
        if result.returncode == 0:
            return True, ''
        plain = plain or result.stderr
    # The retry's own complaint (an unknown flag on a newer llvm-as)
    # would hide the real error.
    first = next((l for l in plain.splitlines() if 'error' in l), plain.strip())
    return False, first


def verifier_fails(source, out_dir, prefix, mutate, failures, label, expect):
    """
    Copy a generated program, change one thing, and expect the verifier
    to fail for the stated reason -- not for any reason: a crash, or an
    unrelated mismatch, would otherwise stand in for the check.
    """
    copy = out_dir + '_' + label.replace(' ', '_')
    shutil.copytree(out_dir, copy, dirs_exist_ok=True)
    mutate(copy)
    returncode, text = run_verifier(source, copy, prefix)
    check(f'AS verifier   {label}', returncode != 0 and expect in text, failures)
    if returncode == 0 or expect not in text:
        print(f'        expected {expect!r}; got: {text.strip().splitlines()[-1][:120] if text.strip() else "(nothing)"}')


def edit(path, old, new):
    text = read(path)
    if old not in text:
        raise RuntimeError(f"{os.path.basename(path)} has no {old!r}")
    with open(path, 'w') as f:
        f.write(text.replace(old, new, 1))


DEREF_SOURCE = '''; ModuleID = 'deref.c'
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"

@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel(i32* noundef %out) #0 {
entry:
  %out.addr = alloca i32*, align 8
  %i = alloca i32, align 4
  store i32* %out, i32** %out.addr, align 8
  store i32 0, i32* %i, align 4
  br label %for.cond

for.cond:
  %0 = load i32, i32* %i, align 4
  %cmp = icmp slt i32 %0, 8
  br i1 %cmp, label %for.body, label %for.end

for.body:
  %1 = load i32, i32* %i, align 4
  %idxprom = sext i32 %1 to i64
  %arrayidx = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %idxprom
  %2 = load i32, i32* %arrayidx, align 4
  %3 = load i32*, i32** %out.addr, align 8
  %4 = load i32, i32* %3, align 4
  %add = add nsw i32 %4, %2
  store i32 %add, i32* %3, align 4
  br label %for.inc

for.inc:
  %5 = load i32, i32* %i, align 4
  %inc = add nsw i32 %5, 1
  store i32 %inc, i32* %i, align 4
  br label %for.cond

for.end:
  ret void
}

attributes #0 = { nounwind }
'''


def retype_elements(text, old_type, new_type, element):
    """
    The program with array `old_type` declared as `new_type`, and every
    access to its elements -- the loads, the arithmetic on what was
    loaded, the stores -- at `element` instead of the old element type.
    Counters and the rest keep their types.
    """
    old_element = re.search(r'x (\w+)\]', old_type).group(1)
    rows = re.sub(r'^\[\d+ x ', '', old_type)[:-1]
    new_rows = re.sub(r'^\[\d+ x ', '', new_type)[:-1]
    text = text.replace(old_type, new_type).replace(rows, new_rows)
    wide = set()
    lines = []
    for line in text.split('\n'):
        m = re.match(r'\s*(%[\w.]+) = getelementptr inbounds (\[.*?\]\*?),', line)
        if m and m.group(2).endswith('%s]' % element) or (m and new_rows in line):
            wide.add(m.group(1))
        m = re.match(r'\s*(%[\w.]+) = load ' + old_element + r', ' + old_element + r'\* (%[\w.]+)', line)
        if m and m.group(2) in wide:
            line = line.replace(f'load {old_element}, {old_element}*', f'load {element}, {element}*')
            wide.add(m.group(1))
        m = re.match(r'\s*(%[\w.]+) = (\w+)(?: nsw| nuw)* ' + old_element + r' (%[\w.]+), (%[\w.]+)', line)
        if m and (m.group(3) in wide or m.group(4) in wide):
            line = line.replace(f' {old_element} ', f' {element} ', 1)
            wide.add(m.group(1))
        m = re.match(r'\s*store ' + old_element + r' (%[\w.]+|-?\d+), ' + old_element + r'\* (%[\w.]+)', line)
        if m and m.group(2) in wide:
            line = line.replace(f'store {old_element} ', f'store {element} ', 1).replace(f', {old_element}* ', f', {element}* ', 1)
        lines.append(line)
    return '\n'.join(lines)


def widen_program(text):
    """The program with every i32 made i64; a `sext i64 to i64` is folded away."""
    text = text.replace('i32', 'i64').replace('align 4', 'align 8')
    alias = {}
    lines = []
    for line in text.split('\n'):
        m = re.match(r'\s*%(\d+) = sext i64 %(\d+) to i64', line)
        if m:
            alias[m.group(1)] = m.group(2)
            continue
        lines.append(line)
    def resolve(reg):
        while reg in alias:
            reg = alias[reg]
        return reg
    text = re.sub(r'%(\d+)\b', lambda m: '%' + resolve(m.group(1)), '\n'.join(lines))
    return renumber(text)


def chain_program(n):
    """One block: a[1] = a[0] * 3 ** n, as n chained multiplies."""
    lines = ['@a = dso_local global [4 x i32] zeroinitializer, align 16',
             'define dso_local i32 @main() #0 {',
             '  %1 = getelementptr inbounds [4 x i32], [4 x i32]* @a, i64 0, i64 0',
             '  %2 = load i32, i32* %1, align 4']
    prev = 2
    for _ in range(n):
        lines.append(f'  %{prev + 1} = mul nsw i32 %{prev}, 3')
        prev += 1
    lines += [f'  %{prev + 1} = getelementptr inbounds [4 x i32], [4 x i32]* @a, i64 0, i64 1',
              f'  store i32 %{prev}, i32* %{prev + 1}, align 4', f'  ret i32 %{prev}', '}']
    return '\n'.join(lines) + '\n'


def blocks_program(m):
    """m blocks in a straight line, each counting and storing a[k]."""
    lines = ['@a = dso_local global [2000 x i32] zeroinitializer, align 16',
             'define dso_local i32 @main() #0 {', '  %1 = alloca i32, align 4',
             '  store i32 0, i32* %1, align 4', '  br label %2']
    reg = 2
    for k in range(m):
        lines += [f'', f'{reg}:', f'  %{reg + 1} = load i32, i32* %1, align 4',
                  f'  %{reg + 2} = add nsw i32 %{reg + 1}, 1',
                  f'  %{reg + 3} = getelementptr inbounds [2000 x i32], [2000 x i32]* @a, i64 0, i64 {k}',
                  f'  store i32 %{reg + 2}, i32* %{reg + 3}, align 4',
                  f'  store i32 %{reg + 2}, i32* %1, align 4']
        if k < m - 1:
            lines.append(f'  br label %{reg + 4}')
            reg += 4
        else:
            lines.append(f'  ret i32 %{reg + 2}')
    lines.append('}')
    return '\n'.join(lines) + '\n'


ZEXT_INDEX_SOURCE = '''@a = dso_local global [256 x i32] zeroinitializer, align 16
@idx = dso_local global [16 x i8] zeroinitializer, align 16
@c = dso_local global [16 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 16
  br i1 %4, label %5, label %17

5:
  %6 = load i32, i32* %1, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [16 x i8], [16 x i8]* @idx, i64 0, i64 %7
  %9 = load i8, i8* %8, align 1
  %10 = zext i8 %9 to i64
  %11 = getelementptr inbounds [256 x i32], [256 x i32]* @a, i64 0, i64 %10
  %12 = load i32, i32* %11, align 4
  %13 = load i32, i32* %1, align 4
  %14 = sext i32 %13 to i64
  %15 = getelementptr inbounds [16 x i32], [16 x i32]* @c, i64 0, i64 %14
  store i32 %12, i32* %15, align 4
  br label %16

16:
  %18 = load i32, i32* %1, align 4
  %19 = add nsw i32 %18, 1
  store i32 %19, i32* %1, align 4
  br label %2

17:
  ret void
}
'''

ZEXT_BIT_SOURCE = '''@a = dso_local global [16 x i32] zeroinitializer, align 16
@c = dso_local global [17 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 16
  br i1 %4, label %5, label %19

5:
  %6 = load i32, i32* %1, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [16 x i32], [16 x i32]* @a, i64 0, i64 %7
  %9 = load i32, i32* %8, align 4
  %10 = icmp sgt i32 %9, 0
  %11 = zext i1 %10 to i32
  %12 = load i32, i32* %1, align 4
  %13 = add nsw i32 %12, %11
  %14 = sext i32 %13 to i64
  %15 = getelementptr inbounds [17 x i32], [17 x i32]* @c, i64 0, i64 %14
  store i32 %9, i32* %15, align 4
  br label %16

16:
  %17 = load i32, i32* %1, align 4
  %18 = add nsw i32 %17, 1
  store i32 %18, i32* %1, align 4
  br label %2

19:
  ret void
}
'''

SEXT_STORE_SOURCE = '''@c = dso_local global [16 x i64] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 16
  br i1 %4, label %5, label %14

5:
  %6 = load i32, i32* %1, align 4
  %7 = sext i32 %6 to i64
  %8 = load i32, i32* %1, align 4
  %9 = sext i32 %8 to i64
  %10 = getelementptr inbounds [16 x i64], [16 x i64]* @c, i64 0, i64 %9
  store i64 %7, i64* %10, align 8
  br label %11

11:
  %12 = load i32, i32* %1, align 4
  %13 = add nsw i32 %12, 1
  store i32 %13, i32* %1, align 4
  br label %2

14:
  ret void
}
'''

DERIVED_LATCH_SOURCE = '''@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %3

3:
  %4 = load i32, i32* %1, align 4
  %5 = icmp slt i32 %4, 8
  br i1 %5, label %6, label %24

6:
  store i32 0, i32* %2, align 4
  br label %7

7:
  %8 = load i32, i32* %2, align 4
  %9 = icmp slt i32 %8, 24
  br i1 %9, label %10, label %21

10:
  %11 = load i32, i32* %2, align 4
  %12 = add nsw i32 %11, 1
  store i32 %12, i32* %2, align 4
  %13 = load i32, i32* %1, align 4
  %14 = sext i32 %13 to i64
  %15 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %14
  %16 = load i32, i32* %15, align 4
  %17 = load i32, i32* %2, align 4
  %18 = mul nsw i32 %17, 2
  %19 = add nsw i32 %16, %18
  store i32 %19, i32* %15, align 4
  br label %7

21:
  %22 = load i32, i32* %1, align 4
  %23 = add nsw i32 %22, 1
  store i32 %23, i32* %1, align 4
  br label %3

24:
  ret void
}
'''

INIT_USE_SOURCE = '''@c = dso_local global [24 x [8 x i32]] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %3

3:
  %4 = load i32, i32* %1, align 4
  %5 = icmp slt i32 %4, 8
  br i1 %5, label %6, label %28

6:
  store i32 0, i32* %2, align 4
  %7 = load i32, i32* %2, align 4
  %8 = sext i32 %7 to i64
  %9 = getelementptr inbounds [24 x [8 x i32]], [24 x [8 x i32]]* @c, i64 0, i64 %8
  %10 = load i32, i32* %1, align 4
  %11 = sext i32 %10 to i64
  %12 = getelementptr inbounds [8 x i32], [8 x i32]* %9, i64 0, i64 %11
  store i32 7, i32* %12, align 4
  br label %13

13:
  %14 = load i32, i32* %2, align 4
  %15 = icmp slt i32 %14, 24
  br i1 %15, label %16, label %25

16:
  %17 = load i32, i32* %2, align 4
  %18 = sext i32 %17 to i64
  %19 = getelementptr inbounds [24 x [8 x i32]], [24 x [8 x i32]]* @c, i64 0, i64 %18
  %20 = load i32, i32* %1, align 4
  %21 = sext i32 %20 to i64
  %22 = getelementptr inbounds [8 x i32], [8 x i32]* %19, i64 0, i64 %21
  %23 = load i32, i32* %22, align 4
  %24 = add nsw i32 %23, 1
  store i32 %24, i32* %22, align 4
  br label %29

29:
  %30 = load i32, i32* %2, align 4
  %31 = add nsw i32 %30, 1
  store i32 %31, i32* %2, align 4
  br label %13

25:
  %26 = load i32, i32* %1, align 4
  %27 = add nsw i32 %26, 1
  store i32 %27, i32* %1, align 4
  br label %3

28:
  ret void
}
'''

DUP_OFFSET_SOURCE = '''@a = dso_local global [17 x [17 x i32]] zeroinitializer, align 16
@c = dso_local global [16 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 16
  br i1 %4, label %5, label %21

5:
  %6 = load i32, i32* %1, align 4
  %7 = add nsw i32 %6, 1
  %8 = sext i32 %7 to i64
  %9 = getelementptr inbounds [17 x [17 x i32]], [17 x [17 x i32]]* @a, i64 0, i64 %8
  %10 = load i32, i32* %1, align 4
  %11 = add nsw i32 %10, 1
  %12 = sext i32 %11 to i64
  %13 = getelementptr inbounds [17 x i32], [17 x i32]* %9, i64 0, i64 %12
  %14 = load i32, i32* %13, align 4
  %15 = load i32, i32* %1, align 4
  %16 = sext i32 %15 to i64
  %17 = getelementptr inbounds [16 x i32], [16 x i32]* @c, i64 0, i64 %16
  store i32 %14, i32* %17, align 4
  br label %18

18:
  %19 = load i32, i32* %1, align 4
  %20 = add nsw i32 %19, 1
  store i32 %20, i32* %1, align 4
  br label %2

21:
  ret void
}
'''

PTR_REASSIGN_SOURCE = '''define dso_local void @kernel(i32* noundef %a) #0 {
entry:
  %a.addr = alloca i32*, align 8
  store i32* %a, i32** %a.addr, align 8
  %0 = load i32*, i32** %a.addr, align 8
  %add.ptr = getelementptr inbounds i32, i32* %0, i64 1
  store i32* %add.ptr, i32** %a.addr, align 8
  %1 = load i32*, i32** %a.addr, align 8
  store i32 5, i32* %1, align 4
  ret void
}
'''

PTR_COPY_SOURCE = '''define dso_local void @kernel(i32* noundef %a) #0 {
entry:
  %a.addr = alloca i32*, align 8
  %q = alloca i32*, align 8
  store i32* %a, i32** %a.addr, align 8
  %0 = load i32*, i32** %a.addr, align 8
  store i32* %0, i32** %q, align 8
  %1 = load i32*, i32** %q, align 8
  store i32 5, i32* %1, align 4
  ret void
}
'''

CONST_LOAD_SOURCE = '''@a = dso_local global [4 x [8 x i32]] zeroinitializer, align 16
@r = dso_local global i32 0, align 4

define dso_local void @kernel() #0 {
  %1 = load i32, i32* getelementptr inbounds ([4 x [8 x i32]], [4 x [8 x i32]]* @a, i64 0, i64 0, i64 3), align 4
  %2 = mul nsw i32 %1, 3
  store i32 %2, i32* getelementptr inbounds ([4 x [8 x i32]], [4 x [8 x i32]]* @a, i64 0, i64 1, i64 0), align 4
  store i32 %2, i32* @r, align 4
  ret void
}
'''

CONST_BASE_SOURCE = '''@a = dso_local global [4 x [8 x i32]] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 8
  br i1 %4, label %5, label %16

5:
  %6 = load i32, i32* %1, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [8 x i32], [8 x i32]* getelementptr inbounds ([4 x [8 x i32]], [4 x [8 x i32]]* @a, i64 0, i64 2), i64 0, i64 %7
  %9 = load i32, i32* %8, align 4
  %10 = load i32, i32* %1, align 4
  %11 = sext i32 %10 to i64
  %12 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %11
  store i32 %9, i32* %12, align 4
  br label %13

13:
  %14 = load i32, i32* %1, align 4
  %15 = add nsw i32 %14, 1
  store i32 %15, i32* %1, align 4
  br label %2

16:
  ret void
}
'''

CONST_GLOBAL_SOURCE = '''@k = dso_local constant i32 3, align 4
@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 8
  br i1 %4, label %5, label %15

5:
  %6 = load i32, i32* @k, align 4
  %7 = load i32, i32* %1, align 4
  %8 = mul nsw i32 %6, %7
  %9 = load i32, i32* %1, align 4
  %10 = sext i32 %9 to i64
  %11 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %10
  store i32 %8, i32* %11, align 4
  br label %12

12:
  %13 = load i32, i32* %1, align 4
  %14 = add nsw i32 %13, 1
  store i32 %14, i32* %1, align 4
  br label %2

15:
  ret void
}
'''

PTR_ARITH_SOURCE = '''define dso_local void @kernel(i32* noundef %p) #0 {
  %2 = alloca i32*, align 8
  %3 = alloca i32, align 4
  store i32* %p, i32** %2, align 8
  store i32 0, i32* %3, align 4
  br label %4

4:
  %5 = load i32, i32* %3, align 4
  %6 = icmp slt i32 %5, 6
  br i1 %6, label %7, label %18

7:
  %8 = load i32*, i32** %2, align 8
  %9 = getelementptr inbounds i32, i32* %8, i64 2
  %10 = load i32, i32* %3, align 4
  %11 = sext i32 %10 to i64
  %12 = getelementptr inbounds i32, i32* %9, i64 %11
  %13 = load i32, i32* %12, align 4
  %14 = add nsw i32 %13, 1
  store i32 %14, i32* %12, align 4
  br label %15

15:
  %16 = load i32, i32* %3, align 4
  %17 = add nsw i32 %16, 1
  store i32 %17, i32* %3, align 4
  br label %4

18:
  ret void
}
'''

FNPTR_SOURCE = '''@c = dso_local global [32 x i32] zeroinitializer, align 16

define dso_local void @kernel(void (i32, i32)* noundef %fp, i32 noundef %n) #0 {
  %3 = alloca void (i32, i32)*, align 8
  %4 = alloca i32, align 4
  %5 = alloca i32, align 4
  store void (i32, i32)* %fp, void (i32, i32)** %3, align 8
  store i32 %n, i32* %4, align 4
  store i32 0, i32* %5, align 4
  br label %6

6:
  %7 = load i32, i32* %5, align 4
  %8 = load i32, i32* %4, align 4
  %9 = icmp slt i32 %7, %8
  br i1 %9, label %10, label %18

10:
  %11 = load i32, i32* %5, align 4
  %12 = load i32, i32* %5, align 4
  %13 = sext i32 %12 to i64
  %14 = getelementptr inbounds [32 x i32], [32 x i32]* @c, i64 0, i64 %13
  store i32 %11, i32* %14, align 4
  br label %15

15:
  %16 = load i32, i32* %5, align 4
  %17 = add nsw i32 %16, 1
  store i32 %17, i32* %5, align 4
  br label %6

18:
  ret void
}
'''

NARROW_COUNTER_SOURCE = '''@a = dso_local global [256 x i32] zeroinitializer, align 16
@b = dso_local global [100 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i8, align 1
  store i8 0, i8* %1, align 1
  br label %2

2:
  %3 = load i8, i8* %1, align 1
  %4 = sext i8 %3 to i32
  %5 = icmp slt i32 %4, 100
  br i1 %5, label %6, label %19

6:
  %7 = load i8, i8* %1, align 1
  %8 = sext i8 %7 to i32
  %9 = sext i32 %8 to i64
  %10 = getelementptr inbounds [100 x i32], [100 x i32]* @b, i64 0, i64 %9
  %11 = load i32, i32* %10, align 4
  %12 = load i8, i8* %1, align 1
  %13 = sext i8 %12 to i32
  %14 = add nsw i32 %13, 100
  %15 = sext i32 %14 to i64
  %16 = getelementptr inbounds [256 x i32], [256 x i32]* @a, i64 0, i64 %15
  store i32 %11, i32* %16, align 4
  br label %17

17:
  %18 = load i8, i8* %1, align 1
  %20 = add i8 %18, 1
  store i8 %20, i8* %1, align 1
  br label %2

19:
  ret void
}
'''

INIT_REASSIGN_SOURCE = '''@a = dso_local global [16 x i32] zeroinitializer, align 16
@b = dso_local global [16 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 3, i32* %1, align 4
  %2 = load i32, i32* %1, align 4
  %3 = sext i32 %2 to i64
  %4 = getelementptr inbounds [16 x i32], [16 x i32]* @a, i64 0, i64 %3
  %5 = load i32, i32* %4, align 4
  store i32 %5, i32* getelementptr inbounds ([16 x i32], [16 x i32]* @b, i64 0, i64 0), align 4
  %6 = load i32, i32* %1, align 4
  %7 = sub nsw i32 %6, 2
  store i32 %7, i32* %1, align 4
  %8 = load i32, i32* %1, align 4
  %9 = sext i32 %8 to i64
  %10 = getelementptr inbounds [16 x i32], [16 x i32]* @a, i64 0, i64 %9
  %11 = load i32, i32* %10, align 4
  store i32 %11, i32* getelementptr inbounds ([16 x i32], [16 x i32]* @b, i64 0, i64 1), align 4
  store i32 0, i32* %1, align 4
  br label %12

12:
  %13 = load i32, i32* %1, align 4
  %14 = icmp slt i32 %13, 16
  br i1 %14, label %15, label %24

15:
  %16 = load i32, i32* %1, align 4
  %17 = sext i32 %16 to i64
  %18 = getelementptr inbounds [16 x i32], [16 x i32]* @a, i64 0, i64 %17
  %19 = load i32, i32* %18, align 4
  %20 = add nsw i32 %19, 1
  store i32 %20, i32* %18, align 4
  br label %21

21:
  %22 = load i32, i32* %1, align 4
  %23 = add nsw i32 %22, 1
  store i32 %23, i32* %1, align 4
  br label %12

24:
  ret void
}
'''

DEAD_BLOCK_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@b = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
entry:
  %i = alloca i32, align 4
  store i32 0, i32* %i, align 4
  br label %for.cond

for.cond:
  %0 = load i32, i32* %i, align 4
  %cmp = icmp slt i32 %0, 8
  br i1 %cmp, label %for.body, label %for.end

for.body:
  %1 = load i32, i32* %i, align 4
  %idxprom = sext i32 %1 to i64
  %arrayidx = getelementptr inbounds [8 x i32], [8 x i32]* @b, i64 0, i64 %idxprom
  %2 = load i32, i32* %arrayidx, align 4
  %3 = load i32, i32* %i, align 4
  %idxprom1 = sext i32 %3 to i64
  %arrayidx2 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %idxprom1
  store i32 %2, i32* %arrayidx2, align 4
  br label %for.end

for.inc:
  %4 = load i32, i32* %i, align 4
  %inc = add nsw i32 %4, 1
  store i32 %inc, i32* %i, align 4
  br label %for.cond

for.end:
  ret void
}
'''

READ_BEFORE_LOOP_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@b = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
entry:
  %i = alloca i32, align 4
  store i32 0, i32* %i, align 4
  %0 = load i32, i32* getelementptr inbounds ([8 x i32], [8 x i32]* @a, i64 0, i64 0), align 4
  %cmp = icmp slt i32 %0, 100
  br i1 %cmp, label %if.then, label %if.end

if.then:
  %1 = load i32, i32* %i, align 4
  store i32 %1, i32* getelementptr inbounds ([8 x i32], [8 x i32]* @b, i64 0, i64 0), align 4
  br label %if.end

if.end:
  br label %while.cond

while.cond:
  %2 = load i32, i32* %i, align 4
  %cmp1 = icmp slt i32 %2, 8
  br i1 %cmp1, label %while.body, label %while.end

while.body:
  %3 = load i32, i32* %i, align 4
  %4 = load i32, i32* %i, align 4
  %idxprom = sext i32 %4 to i64
  %arrayidx = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %idxprom
  store i32 %3, i32* %arrayidx, align 4
  %5 = load i32, i32* %i, align 4
  %inc = add nsw i32 %5, 1
  store i32 %inc, i32* %i, align 4
  br label %while.cond

while.end:
  ret void
}
'''

SWITCH_I1_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 8
  br i1 %4, label %5, label %23

5:
  %6 = load i32, i32* %1, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %7
  %9 = load i32, i32* %8, align 4
  %10 = icmp sgt i32 %9, 0
  switch i1 %10, label %14 [
    i1 true, label %11
  ]

11:
  %12 = load i32, i32* %1, align 4
  %13 = sext i32 %12 to i64
  %15 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %13
  %17 = load i32, i32* %1, align 4
  %18 = sext i32 %17 to i64
  %19 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %18
  %24 = load i32, i32* %19, align 4
  store i32 %24, i32* %15, align 4
  br label %14

14:
  br label %20

20:
  %21 = load i32, i32* %1, align 4
  %22 = add nsw i32 %21, 1
  store i32 %22, i32* %1, align 4
  br label %2

23:
  ret void
}
'''

INIT_ARRAY_SOURCE = '''@k = dso_local constant [4 x i32] [i32 5, i32 6, i32 7, i32 8], align 16
@c = dso_local global [4 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 4
  br i1 %4, label %5, label %17

5:
  %6 = load i32, i32* %1, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [4 x i32], [4 x i32]* @k, i64 0, i64 %7
  %9 = load i32, i32* %8, align 4
  %10 = mul nsw i32 %9, 2
  %11 = load i32, i32* %1, align 4
  %12 = sext i32 %11 to i64
  %13 = getelementptr inbounds [4 x i32], [4 x i32]* @c, i64 0, i64 %12
  store i32 %10, i32* %13, align 4
  br label %14

14:
  %15 = load i32, i32* %1, align 4
  %16 = add nsw i32 %15, 1
  store i32 %16, i32* %1, align 4
  br label %2

17:
  ret void
}
'''

HEADER_STEP_SOURCE = '''@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
entry:
  %j = alloca i32, align 4
  store i32 0, i32* %j, align 4
  br label %do.body

do.body:
  %0 = load i32, i32* %j, align 4
  %idxprom = sext i32 %0 to i64
  %arrayidx = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %idxprom
  store i32 %0, i32* %arrayidx, align 4
  %1 = load i32, i32* %j, align 4
  %inc = add nsw i32 %1, 1
  store i32 %inc, i32* %j, align 4
  br label %do.cond

do.cond:
  %2 = load i32, i32* %j, align 4
  %cmp = icmp slt i32 %2, 8
  br i1 %cmp, label %do.body, label %do.end

do.end:
  ret void
}
'''

CROSS_BLOCK_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
entry:
  %0 = load i32, i32* getelementptr inbounds ([8 x i32], [8 x i32]* @a, i64 0, i64 1), align 4
  %cmp = icmp sgt i32 %0, 0
  br i1 %cmp, label %if.then, label %if.end

if.then:
  store i32 %0, i32* getelementptr inbounds ([8 x i32], [8 x i32]* @c, i64 0, i64 0), align 4
  br label %if.end

if.end:
  ret void
}
'''

LONG_LITERAL_SOURCE = '''@c = dso_local global [8 x i64] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i64, align 8
  %2 = alloca i64, align 8
  store i64 0, i64* %1, align 8
  %3 = load i64, i64* %1, align 8
  %4 = add nsw i64 %3, 3
  store i64 %4, i64* %2, align 8
  br label %5

5:
  %6 = load i64, i64* %1, align 8
  %7 = icmp slt i64 %6, 8
  br i1 %7, label %8, label %15

8:
  %9 = load i64, i64* %2, align 8
  %10 = load i64, i64* %1, align 8
  %11 = getelementptr inbounds [8 x i64], [8 x i64]* @c, i64 0, i64 %10
  store i64 %9, i64* %11, align 8
  br label %12

12:
  %13 = load i64, i64* %1, align 8
  %14 = add nsw i64 %13, 1
  store i64 %14, i64* %1, align 8
  br label %5

15:
  ret void
}
'''

I64_PARAM_SOURCE = '''@c = dso_local global [8 x i64] zeroinitializer, align 16

define dso_local void @kernel(i64 noundef %n) #0 {
  %2 = alloca i64, align 8
  %3 = alloca i32, align 4
  store i64 %n, i64* %2, align 8
  store i32 0, i32* %3, align 4
  br label %4

4:
  %5 = load i32, i32* %3, align 4
  %6 = icmp slt i32 %5, 8
  br i1 %6, label %7, label %16

7:
  %8 = load i64, i64* %2, align 8
  %9 = mul nsw i64 %8, 2
  %10 = load i32, i32* %3, align 4
  %11 = sext i32 %10 to i64
  %12 = getelementptr inbounds [8 x i64], [8 x i64]* @c, i64 0, i64 %11
  store i64 %9, i64* %12, align 8
  br label %13

13:
  %14 = load i32, i32* %3, align 4
  %15 = add nsw i32 %14, 1
  store i32 %15, i32* %3, align 4
  br label %4

16:
  ret void
}
'''

INIT_LOAD_SOURCE = '''@idx = dso_local global [4 x i32] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  %3 = load i32, i32* getelementptr inbounds ([4 x i32], [4 x i32]* @idx, i64 0, i64 1), align 4
  %4 = srem i32 %3, 4
  store i32 %4, i32* %1, align 4
  %5 = load i32, i32* %1, align 4
  %6 = mul nsw i32 %5, 2
  store i32 %6, i32* %2, align 4
  br label %7

7:
  %8 = load i32, i32* %1, align 4
  %9 = icmp slt i32 %8, 8
  br i1 %9, label %10, label %18

10:
  %11 = load i32, i32* %2, align 4
  %12 = load i32, i32* %1, align 4
  %13 = sext i32 %12 to i64
  %14 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %13
  store i32 %11, i32* %14, align 4
  br label %15

15:
  %16 = load i32, i32* %1, align 4
  %17 = add nsw i32 %16, 1
  store i32 %17, i32* %1, align 4
  br label %7

18:
  ret void
}
'''

GLOBAL_COUNTER_SOURCE = '''@n = dso_local global i32 0, align 4
@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  store i32 0, i32* @n, align 4
  br label %1

1:
  %2 = load i32, i32* @n, align 4
  %3 = icmp slt i32 %2, 8
  br i1 %3, label %4, label %11

4:
  %5 = load i32, i32* @n, align 4
  %6 = load i32, i32* @n, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %7
  store i32 %5, i32* %8, align 4
  br label %9

9:
  %10 = load i32, i32* @n, align 4
  %12 = add nsw i32 %10, 1
  store i32 %12, i32* @n, align 4
  br label %1

11:
  ret void
}
'''

ANNOTATED_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4, !annotation !6
  store i32 0, i32* %1, align 4, !annotation !6
  br label %2, !annotation !6

2:
  %3 = load i32, i32* %1, align 4, !annotation !6
  %4 = icmp slt i32 %3, 8, !annotation !6
  br i1 %4, label %5, label %16, !annotation !6

5:
  %6 = load i32, i32* %1, align 4
  %7 = sext i32 %6 to i64, !annotation !6
  %8 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %7, !annotation !6
  %9 = load i32, i32* %8, align 4, !annotation !6
  %10 = load i32, i32* %1, align 4
  %11 = sext i32 %10 to i64
  %12 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %11
  store i32 %9, i32* %12, align 4, !annotation !6
  br label %13

13:
  %14 = load i32, i32* %1, align 4
  %15 = add nsw i32 %14, 1, !annotation !6
  store i32 %15, i32* %1, align 4
  br label %2, !llvm.loop !7, !annotation !6

16:
  ret void, !annotation !6
}

!6 = !{!"reviewed"}
!7 = distinct !{!7, !8}
!8 = !{!"llvm.loop.mustprogress"}
'''

SEQ_NO_INIT_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 4
  br i1 %4, label %5, label %13

5:
  %6 = load i32, i32* %1, align 4
  %7 = load i32, i32* %1, align 4
  %8 = sext i32 %7 to i64
  %9 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %8
  store i32 %6, i32* %9, align 4
  br label %10

10:
  %11 = load i32, i32* %1, align 4
  %12 = add nsw i32 %11, 1
  store i32 %12, i32* %1, align 4
  br label %2

13:
  br label %14

14:
  %15 = load i32, i32* %1, align 4
  %16 = icmp slt i32 %15, 8
  br i1 %16, label %17, label %26

17:
  %18 = load i32, i32* %1, align 4
  %19 = mul nsw i32 %18, 2
  %20 = load i32, i32* %1, align 4
  %21 = sext i32 %20 to i64
  %22 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %21
  store i32 %19, i32* %22, align 4
  br label %23

23:
  %24 = load i32, i32* %1, align 4
  %25 = add nsw i32 %24, 1
  store i32 %25, i32* %1, align 4
  br label %14

26:
  ret void
}
'''

NAME_COLLISION_SOURCE = '''@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel(i32 noundef %n) #0 {
entry:
  %n.addr = alloca i32, align 4
  %n_addr = alloca i32, align 4
  store i32 %n, i32* %n.addr, align 4
  store i32 5, i32* %n_addr, align 4
  %0 = load i32, i32* %n.addr, align 4
  %1 = load i32, i32* %n_addr, align 4
  %add = add nsw i32 %0, %1
  store i32 %add, i32* getelementptr inbounds ([8 x i32], [8 x i32]* @c, i64 0, i64 0), align 4
  ret void
}
'''

POINTER_ARG_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@r = dso_local global i32 0, align 4

declare i32 @f(i32*)

define dso_local void @kernel() #0 {
entry:
  %call = call i32 @f(i32* getelementptr inbounds ([8 x i32], [8 x i32]* @a, i64 0, i64 3))
  store i32 %call, i32* @r, align 4
  ret void
}
'''

DEREF_LOOP_SOURCE = '''define dso_local void @kernel(i32* noundef %p) #0 {
entry:
  %p.addr = alloca i32*, align 8
  store i32* %p, i32** %p.addr, align 8
  br label %while.cond

while.cond:
  %0 = load i32*, i32** %p.addr, align 8
  %1 = load i32, i32* %0, align 4
  %cmp = icmp slt i32 %1, 10
  br i1 %cmp, label %while.body, label %while.end

while.body:
  %2 = load i32*, i32** %p.addr, align 8
  %3 = load i32, i32* %2, align 4
  %add = add nsw i32 %3, 1
  store i32 %add, i32* %2, align 4
  br label %while.cond

while.end:
  ret void
}
'''

NOTAIL_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16

declare i32 @llvm.smax.i32(i32, i32)

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 8
  br i1 %4, label %5, label %17

5:
  %6 = load i32, i32* %1, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %7
  %9 = load i32, i32* %8, align 4
  %10 = notail call i32 @llvm.smax.i32(i32 %9, i32 0)
  %11 = load i32, i32* %1, align 4
  %12 = sext i32 %11 to i64
  %13 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %12
  store i32 %10, i32* %13, align 4
  br label %14

14:
  %15 = load i32, i32* %1, align 4
  %16 = add nsw i32 %15, 1
  store i32 %16, i32* %1, align 4
  br label %2

17:
  ret void
}
'''

STRING_CONST_SOURCE = '''@s = dso_local constant [4 x i8] c"\\05\\06\\07\\08", align 1
@c = dso_local global [4 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 4
  br i1 %4, label %5, label %18

5:
  %6 = load i32, i32* %1, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [4 x i8], [4 x i8]* @s, i64 0, i64 %7
  %9 = load i8, i8* %8, align 1
  %10 = sext i8 %9 to i32
  %11 = mul nsw i32 %10, 3
  %12 = load i32, i32* %1, align 4
  %13 = sext i32 %12 to i64
  %14 = getelementptr inbounds [4 x i32], [4 x i32]* @c, i64 0, i64 %13
  store i32 %11, i32* %14, align 4
  br label %15

15:
  %16 = load i32, i32* %1, align 4
  %17 = add nsw i32 %16, 1
  store i32 %17, i32* %1, align 4
  br label %2

18:
  ret void
}
'''

RET_MUL_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local i32 @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 8
  br i1 %4, label %5, label %13

5:
  %6 = load i32, i32* %1, align 4
  %7 = load i32, i32* %1, align 4
  %8 = sext i32 %7 to i64
  %9 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %8
  store i32 %6, i32* %9, align 4
  br label %10

10:
  %11 = load i32, i32* %1, align 4
  %12 = add nsw i32 %11, 1
  store i32 %12, i32* %1, align 4
  br label %2

13:
  %14 = load i32, i32* %1, align 4
  %15 = mul nsw i32 %14, 2
  ret i32 %15
}
'''

RET_TRUNC_SOURCE = '''@a = dso_local global [8 x i64] zeroinitializer, align 16

define dso_local i32 @kernel() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i64, align 8
  store i32 0, i32* %1, align 4
  store i64 0, i64* %2, align 8
  br label %3

3:
  %4 = load i32, i32* %1, align 4
  %5 = icmp slt i32 %4, 8
  br i1 %5, label %6, label %18

6:
  %7 = load i32, i32* %1, align 4
  %8 = sext i32 %7 to i64
  %9 = getelementptr inbounds [8 x i64], [8 x i64]* @a, i64 0, i64 %8
  %10 = load i64, i64* %9, align 8
  %11 = load i64, i64* %2, align 8
  %12 = add nsw i64 %11, %10
  store i64 %12, i64* %2, align 8
  br label %13

13:
  %14 = load i32, i32* %1, align 4
  %15 = add nsw i32 %14, 1
  store i32 %15, i32* %1, align 4
  br label %3

18:
  %19 = load i64, i64* %2, align 8
  %20 = trunc i64 %19 to i32
  ret i32 %20
}
'''

RET_ELEMENT_SOURCE = '''@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local i32 @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 8
  br i1 %4, label %5, label %14

5:
  %6 = load i32, i32* %1, align 4
  %7 = mul nsw i32 %6, 3
  %8 = load i32, i32* %1, align 4
  %9 = sext i32 %8 to i64
  %10 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %9
  store i32 %7, i32* %10, align 4
  br label %11

11:
  %12 = load i32, i32* %1, align 4
  %13 = add nsw i32 %12, 1
  store i32 %13, i32* %1, align 4
  br label %2

14:
  %15 = load i32, i32* getelementptr inbounds ([8 x i32], [8 x i32]* @c, i64 0, i64 3), align 4
  ret i32 %15
}
'''

DOT_NAME_SOURCE = '''@.str = private unnamed_addr constant [4 x i8] c"\\05\\06\\07\\08", align 1
@c = dso_local global [4 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 4
  br i1 %4, label %5, label %18

5:
  %6 = load i32, i32* %1, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [4 x i8], [4 x i8]* @.str, i64 0, i64 %7
  %9 = load i8, i8* %8, align 1
  %10 = sext i8 %9 to i32
  %11 = mul nsw i32 %10, 3
  %12 = load i32, i32* %1, align 4
  %13 = sext i32 %12 to i64
  %14 = getelementptr inbounds [4 x i32], [4 x i32]* @c, i64 0, i64 %13
  store i32 %11, i32* %14, align 4
  br label %15

15:
  %16 = load i32, i32* %1, align 4
  %17 = add nsw i32 %16, 1
  store i32 %17, i32* %1, align 4
  br label %2

18:
  ret void
}
'''

PTR_COMPARE_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel(i32* noundef %p) #0 {
entry:
  %p.addr = alloca i32*, align 8
  store i32* %p, i32** %p.addr, align 8
  %0 = load i32*, i32** %p.addr, align 8
  %cmp = icmp ne i32* %0, null
  br i1 %cmp, label %if.then, label %if.end

if.then:
  %1 = load i32*, i32** %p.addr, align 8
  store i32 1, i32* %1, align 4
  br label %if.end

if.end:
  ret void
}
'''

PTRTOINT_SOURCE = '''@r = dso_local global i64 0, align 8

define dso_local void @kernel(i32* noundef %p) #0 {
entry:
  %p.addr = alloca i32*, align 8
  store i32* %p, i32** %p.addr, align 8
  %0 = load i32*, i32** %p.addr, align 8
  %1 = ptrtoint i32* %0 to i64
  store i64 %1, i64* @r, align 8
  ret void
}
'''

ARG_GLOBAL_SOURCE = '''@arg_n = dso_local global i32 0, align 4
@a = dso_local global [4 x i32] zeroinitializer, align 16

define dso_local void @kernel(i32 noundef %n) #0 {
  %2 = alloca i32, align 4
  store i32 %n, i32* %2, align 4
  %3 = load i32, i32* @arg_n, align 4
  %4 = load i32, i32* %2, align 4
  %5 = add nsw i32 %3, %4
  store i32 %5, i32* getelementptr inbounds ([4 x i32], [4 x i32]* @a, i64 0, i64 0), align 4
  ret void
}
'''

PTR_CALL_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16

declare i32* @get()

define dso_local void @kernel() #0 {
entry:
  %call = call i32* @get()
  %0 = load i32, i32* %call, align 4
  store i32 %0, i32* getelementptr inbounds ([8 x i32], [8 x i32]* @a, i64 0, i64 1), align 4
  ret void
}
'''

RET_PTR_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local i32* @kernel() #0 {
entry:
  %0 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 2
  store i32 7, i32* %0, align 4
  ret i32* %0
}
'''

FNEG_SOURCE = '''@a = dso_local global [8 x double] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  br label %2

2:
  %3 = load i32, i32* %1, align 4
  %4 = icmp slt i32 %3, 8
  br i1 %4, label %5, label %13

5:
  %6 = load i32, i32* %1, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [8 x double], [8 x double]* @a, i64 0, i64 %7
  %9 = load double, double* %8, align 8
  %10 = fneg double %9
  store double %10, double* %8, align 8
  br label %11

11:
  %12 = load i32, i32* %1, align 4
  %14 = add nsw i32 %12, 1
  store i32 %14, i32* %1, align 4
  br label %2

13:
  ret void
}
'''

BARE_GLOBAL_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@b = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, ptr %1, align 4
  br label %2

2:
  %3 = load i32, ptr %1, align 4
  %4 = icmp slt i32 %3, 8
  br i1 %4, label %5, label %17

5:
  %6 = load i32, ptr %1, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [8 x i32], ptr @a, i64 0, i64 %7
  %9 = load i32, ptr %8, align 4
  %10 = load i32, ptr @a, align 4
  %11 = add nsw i32 %9, %10
  %12 = load i32, ptr %1, align 4
  %13 = sext i32 %12 to i64
  %14 = getelementptr inbounds [8 x i32], ptr @b, i64 0, i64 %13
  store i32 %11, ptr %14, align 4
  br label %15

15:
  %16 = load i32, ptr %1, align 4
  %18 = add nsw i32 %16, 1
  store i32 %18, ptr %1, align 4
  br label %2

17:
  ret void
}
'''

DECAY_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@b = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = alloca i32, align 4
  store i32 0, ptr %1, align 4
  br label %2

2:
  %3 = load i32, ptr %1, align 4
  %4 = icmp slt i32 %3, 8
  br i1 %4, label %5, label %15

5:
  %6 = load i32, ptr %1, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds i32, ptr @a, i64 %7
  %9 = load i32, ptr %8, align 4
  %10 = load i32, ptr %1, align 4
  %11 = sext i32 %10 to i64
  %12 = getelementptr inbounds [8 x i32], ptr @b, i64 0, i64 %11
  store i32 %9, ptr %12, align 4
  br label %13

13:
  %14 = load i32, ptr %1, align 4
  %16 = add nsw i32 %14, 1
  store i32 %16, ptr %1, align 4
  br label %2

15:
  ret void
}
'''

FLAT_MATRIX_SOURCE = '''@m = dso_local global [2 x [4 x i32]] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = getelementptr inbounds i32, ptr @m, i64 5
  store i32 1, ptr %1, align 4
  ret void
}
'''

SELF_LOOP_SOURCE = '''define dso_local void @kernel() #0 {
entry:
  br label %loop

loop:
  br label %loop
}
'''

TWO_BLOCK_EMPTY_LOOP_SOURCE = '''define dso_local void @kernel() #0 {
entry:
  br label %a

a:
  br label %b

b:
  br label %a
}
'''

ROW_POINTER_SOURCE = '''@m = dso_local global [2 x [3 x i32]] zeroinitializer, align 16
@t = dso_local global [2 x [3 x i32]] zeroinitializer, align 16
@s = dso_local global i32 0, align 4

define dso_local i32 @main() #0 {
entry:
  %retval = alloca i32, align 4
  %i = alloca i32, align 4
  %j = alloca i32, align 4
  store i32 0, i32* %retval, align 4
  store i32 0, i32* %i, align 4
  br label %for.cond

for.cond:
  %0 = load i32, i32* %i, align 4
  %cmp = icmp slt i32 %0, 2
  br i1 %cmp, label %for.body, label %for.end8

for.body:
  store i32 0, i32* %j, align 4
  br label %for.cond1

for.cond1:
  %1 = load i32, i32* %j, align 4
  %cmp2 = icmp slt i32 %1, 3
  br i1 %cmp2, label %for.body3, label %for.end

for.body3:
  %2 = load i32, i32* %i, align 4
  %mul = mul nsw i32 %2, 3
  %3 = load i32, i32* %j, align 4
  %add = add nsw i32 %mul, %3
  %4 = load i32, i32* %i, align 4
  %idx.ext = sext i32 %4 to i64
  %add.ptr = getelementptr inbounds [3 x i32], [3 x i32]* getelementptr inbounds ([2 x [3 x i32]], [2 x [3 x i32]]* @m, i64 0, i64 0), i64 %idx.ext
  %arraydecay = getelementptr inbounds [3 x i32], [3 x i32]* %add.ptr, i64 0, i64 0
  %5 = load i32, i32* %j, align 4
  %idx.ext4 = sext i32 %5 to i64
  %add.ptr5 = getelementptr inbounds i32, i32* %arraydecay, i64 %idx.ext4
  store i32 %add, i32* %add.ptr5, align 4
  br label %for.inc

for.inc:
  %6 = load i32, i32* %j, align 4
  %inc = add nsw i32 %6, 1
  store i32 %inc, i32* %j, align 4
  br label %for.cond1

for.end:
  br label %for.inc6

for.inc6:
  %7 = load i32, i32* %i, align 4
  %inc7 = add nsw i32 %7, 1
  store i32 %inc7, i32* %i, align 4
  br label %for.cond

for.end8:
  store i32 0, i32* %i, align 4
  br label %for.cond9

for.cond9:
  %8 = load i32, i32* %i, align 4
  %cmp10 = icmp slt i32 %8, 2
  br i1 %cmp10, label %for.body11, label %for.end28

for.body11:
  store i32 0, i32* %j, align 4
  br label %for.cond12

for.cond12:
  %9 = load i32, i32* %j, align 4
  %cmp13 = icmp slt i32 %9, 3
  br i1 %cmp13, label %for.body14, label %for.end25

for.body14:
  %10 = load i32, i32* %i, align 4
  %idxprom = sext i32 %10 to i64
  %arrayidx = getelementptr inbounds [2 x [3 x i32]], [2 x [3 x i32]]* @m, i64 0, i64 %idxprom
  %11 = load i32, i32* %j, align 4
  %idxprom15 = sext i32 %11 to i64
  %arrayidx16 = getelementptr inbounds [3 x i32], [3 x i32]* %arrayidx, i64 0, i64 %idxprom15
  %12 = load i32, i32* %arrayidx16, align 4
  %add17 = add nsw i32 %12, 1
  %13 = load i32, i32* %i, align 4
  %idx.ext18 = sext i32 %13 to i64
  %add.ptr19 = getelementptr inbounds [3 x i32], [3 x i32]* getelementptr inbounds ([2 x [3 x i32]], [2 x [3 x i32]]* @t, i64 0, i64 0), i64 %idx.ext18
  %arraydecay20 = getelementptr inbounds [3 x i32], [3 x i32]* %add.ptr19, i64 0, i64 0
  %14 = load i32, i32* %j, align 4
  %idx.ext21 = sext i32 %14 to i64
  %add.ptr22 = getelementptr inbounds i32, i32* %arraydecay20, i64 %idx.ext21
  store i32 %add17, i32* %add.ptr22, align 4
  br label %for.inc23

for.inc23:
  %15 = load i32, i32* %j, align 4
  %inc24 = add nsw i32 %15, 1
  store i32 %inc24, i32* %j, align 4
  br label %for.cond12

for.end25:
  br label %for.inc26

for.inc26:
  %16 = load i32, i32* %i, align 4
  %inc27 = add nsw i32 %16, 1
  store i32 %inc27, i32* %i, align 4
  br label %for.cond9

for.end28:
  %17 = load i32, i32* getelementptr inbounds ([2 x [3 x i32]], [2 x [3 x i32]]* @t, i64 0, i64 1, i64 2), align 4
  store i32 %17, i32* @s, align 4
  ret i32 0
}

attributes #0 = { nounwind }
'''

LEADING_ONE_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = getelementptr inbounds [8 x i32], ptr @a, i64 1, i64 2
  store i32 1, ptr %1, align 4
  ret void
}
'''

REINTERPRET_SOURCE = '''@m = dso_local global [2 x [4 x i32]] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = getelementptr inbounds [2 x [4 x i32]], ptr @m, i64 0, i64 1
  %2 = getelementptr inbounds [2 x i32], ptr %1, i64 0, i64 1
  store i32 1, ptr %2, align 4
  ret void
}
'''

TOO_DEEP_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = getelementptr inbounds [8 x i32], ptr @a, i64 0, i64 1, i64 2
  store i32 1, ptr %1, align 4
  ret void
}
'''

ZERO_STORE_SOURCE = '''define dso_local void @kernel(i32* noundef %p) #0 {
entry:
  %p.addr = alloca i32*, align 8
  %i = alloca i32, align 4
  store i32* %p, i32** %p.addr, align 8
  store i32 0, i32* %i, align 4
  br label %for.cond

for.cond:
  %0 = load i32, i32* %i, align 4
  %cmp = icmp slt i32 %0, 8
  br i1 %cmp, label %for.body, label %for.end

for.body:
  %1 = load i32*, i32** %p.addr, align 8
  %2 = load i32, i32* %i, align 4
  %idxprom = sext i32 %2 to i64
  %arrayidx = getelementptr inbounds i32, i32* %1, i64 %idxprom
  store i32 0, i32* %arrayidx, align 4
  br label %for.inc

for.inc:
  %3 = load i32, i32* %i, align 4
  %inc = add nsw i32 %3, 1
  store i32 %inc, i32* %i, align 4
  br label %for.cond

for.end:
  ret void
}

attributes #0 = { nounwind }
'''

DIRECT_PARAM_SOURCE = '''define dso_local void @kernel(i32* noundef %p) #0 {
entry:
  br label %while.cond

while.cond:
  %0 = load i32, i32* %p, align 4
  %cmp = icmp slt i32 %0, 10
  br i1 %cmp, label %while.body, label %while.end

while.body:
  %1 = load i32, i32* %p, align 4
  %add = add nsw i32 %1, 1
  store i32 %add, i32* %p, align 4
  br label %while.cond

while.end:
  ret void
}

attributes #0 = { nounwind }
'''

PARAM_SWAP_SOURCE = '''define dso_local void @kernel(i32* noundef %a, i32* noundef %b) #0 {
entry:
  %a.addr = alloca i32*, align 8
  %b.addr = alloca i32*, align 8
  store i32* %a, i32** %a.addr, align 8
  store i32* %a, i32** %b.addr, align 8
  %0 = load i32*, i32** %b.addr, align 8
  %1 = getelementptr inbounds i32, i32* %0, i64 1
  store i32 1, i32* %1, align 4
  ret void
}
'''

GLOBAL_POINTER_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@p = dso_local global [8 x i32]* @a, align 8

define dso_local void @kernel() #0 {
  %1 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 1
  store i32 1, i32* %1, align 4
  ret void
}
'''

QUOTED_NAME_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @"my kernel"() #0 {
  %1 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 1
  store i32 1, i32* %1, align 4
  ret void
}
'''

LATCH_READ_SOURCE = '''@a = dso_local global [24 x i32] zeroinitializer, align 16
@c = dso_local global [24 x i32] zeroinitializer, align 16

define dso_local i32 @main() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  store i32 0, i32* %2, align 4
  br label %3

3:
  %4 = load i32, i32* %2, align 4
  %5 = sext i32 %4 to i64
  %6 = getelementptr inbounds [24 x i32], [24 x i32]* @a, i64 0, i64 %5
  %7 = load i32, i32* %6, align 4
  %8 = load i32, i32* %2, align 4
  %9 = sext i32 %8 to i64
  %10 = getelementptr inbounds [24 x i32], [24 x i32]* @c, i64 0, i64 %9
  store i32 %7, i32* %10, align 4
  %11 = load i32, i32* %2, align 4
  %12 = add nsw i32 %11, 1
  store i32 %12, i32* %2, align 4
  %13 = load i32, i32* %2, align 4
  %14 = icmp sge i32 %13, 12
  br i1 %14, label %15, label %16

15:
  br label %17

16:
  br label %3

17:
  %18 = load i32, i32* %2, align 4
  store i32 %18, i32* getelementptr inbounds ([24 x i32], [24 x i32]* @c, i64 0, i64 0), align 16
  %19 = load i32, i32* %2, align 4
  ret i32 %19
}

attributes #0 = { nounwind }
'''

LATCH_BODY_SOURCE = '''@a = dso_local global [24 x i32] zeroinitializer, align 16
@c = dso_local global [24 x i32] zeroinitializer, align 16

define dso_local i32 @main() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  store i32 0, i32* %2, align 4
  br label %3

3:
  %4 = load i32, i32* %2, align 4
  %5 = add nsw i32 %4, 1
  store i32 %5, i32* %2, align 4
  %6 = load i32, i32* %2, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds [24 x i32], [24 x i32]* @a, i64 0, i64 %7
  %9 = load i32, i32* %8, align 4
  %10 = icmp sgt i32 %9, 0
  br i1 %10, label %11, label %12

11:
  br label %3

12:
  %13 = load i32, i32* %2, align 4
  %14 = sext i32 %13 to i64
  %15 = getelementptr inbounds [24 x i32], [24 x i32]* @c, i64 0, i64 %14
  store i32 1, i32* %15, align 4
  %16 = load i32, i32* %2, align 4
  %17 = icmp sge i32 %16, 22
  br i1 %17, label %18, label %19

18:
  br label %20

19:
  br label %3

20:
  %21 = load i32, i32* %2, align 4
  ret i32 %21
}

attributes #0 = { nounwind }
'''

COUNTER_RELOAD_SOURCE = '''@a = dso_local global [24 x [24 x i32]] zeroinitializer, align 16
@c = dso_local global [24 x i32] zeroinitializer, align 16

define dso_local i32 @main() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  store i32 0, i32* %2, align 4
  br label %4

4:
  %5 = load i32, i32* %2, align 4
  %6 = icmp slt i32 %5, 24
  br i1 %6, label %7, label %33

7:
  store i32 0, i32* %3, align 4
  br label %8

8:
  %9 = load i32, i32* %2, align 4
  %10 = sext i32 %9 to i64
  %11 = getelementptr inbounds [24 x [24 x i32]], [24 x [24 x i32]]* @a, i64 0, i64 %10
  %12 = load i32, i32* %3, align 4
  %13 = sext i32 %12 to i64
  %14 = getelementptr inbounds [24 x i32], [24 x i32]* %11, i64 0, i64 %13
  %15 = load i32, i32* %14, align 4
  %16 = icmp eq i32 %15, 2
  br i1 %16, label %17, label %18

17:
  br label %25

18:
  %19 = load i32, i32* %3, align 4
  %20 = add nsw i32 %19, 1
  store i32 %20, i32* %3, align 4
  %21 = load i32, i32* %3, align 4
  %22 = icmp sge i32 %21, 23
  br i1 %22, label %23, label %24

23:
  br label %25

24:
  br label %8

25:
  %26 = load i32, i32* %3, align 4
  %27 = load i32, i32* %2, align 4
  %28 = sext i32 %27 to i64
  %29 = getelementptr inbounds [24 x i32], [24 x i32]* @c, i64 0, i64 %28
  store i32 %26, i32* %29, align 4
  br label %30

30:
  %31 = load i32, i32* %2, align 4
  %32 = add nsw i32 %31, 1
  store i32 %32, i32* %2, align 4
  br label %4

33:
  ret i32 0
}

attributes #0 = { nounwind }
'''

STREAM_NAME_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@a_p = dso_local global [8 x i32] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16
@d = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local i32 @main() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  store i32 0, i32* %2, align 4
  br label %5

5:
  %6 = load i32, i32* %2, align 4
  %7 = icmp slt i32 %6, 8
  br i1 %7, label %q, label %55

q:
  %13 = load i32, i32* %2, align 4
  %14 = sext i32 %13 to i64
  %15 = getelementptr inbounds [8 x i32], [8 x i32]* @a_p, i64 0, i64 %14
  %16 = load i32, i32* %15, align 4
  %17 = mul nsw i32 %16, 3
  %18 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %14
  store i32 %17, i32* %18, align 4
  br label %p_q

p_q:
  %23 = load i32, i32* %2, align 4
  %24 = sext i32 %23 to i64
  %25 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %24
  %26 = load i32, i32* %25, align 4
  %27 = mul nsw i32 %26, 5
  %28 = getelementptr inbounds [8 x i32], [8 x i32]* @d, i64 0, i64 %24
  store i32 %27, i32* %28, align 4
  br label %52

52:
  %53 = load i32, i32* %2, align 4
  %54 = add nsw i32 %53, 1
  store i32 %54, i32* %2, align 4
  br label %5

55:
  %56 = load i32, i32* %1, align 4
  ret i32 %56
}

attributes #0 = { nounwind }
'''

CGEP_NAME_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@b = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local i32 @main() #0 {
entry:
  %retval = alloca i32, align 4
  %cgep0 = alloca i32, align 4
  %i = alloca i32, align 4
  store i32 0, i32* %retval, align 4
  %0 = load i32, i32* getelementptr inbounds ([8 x i32], [8 x i32]* @a, i64 0, i64 3), align 4
  %add = add nsw i32 %0, 1
  store i32 %add, i32* %cgep0, align 4
  store i32 0, i32* %i, align 4
  br label %for.cond

for.cond:
  %1 = load i32, i32* %i, align 4
  %cmp = icmp slt i32 %1, 8
  br i1 %cmp, label %for.body, label %for.end

for.body:
  %2 = load i32, i32* %i, align 4
  %idxprom = sext i32 %2 to i64
  %arrayidx = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %idxprom
  %3 = load i32, i32* %arrayidx, align 4
  %4 = load i32, i32* %cgep0, align 4
  %add1 = add nsw i32 %3, %4
  %5 = load i32, i32* %i, align 4
  %idxprom2 = sext i32 %5 to i64
  %arrayidx3 = getelementptr inbounds [8 x i32], [8 x i32]* @b, i64 0, i64 %idxprom2
  store i32 %add1, i32* %arrayidx3, align 4
  br label %for.inc

for.inc:
  %6 = load i32, i32* %i, align 4
  %inc = add nsw i32 %6, 1
  store i32 %inc, i32* %i, align 4
  br label %for.cond

for.end:
  ret i32 0
}

attributes #0 = { nounwind }
'''

RET_LABEL_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
entry:
  br label %ret

ret:
  %1 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 2
  store i32 1, i32* %1, align 4
  ret void
}
'''

ENTRY_LABEL_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  br label %entry

entry:
  %1 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 2
  store i32 1, i32* %1, align 4
  ret void
}
'''

ELEMENT_TYPE_SOURCE = '''@a = dso_local global [8 x i64] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = getelementptr inbounds [8 x i64], ptr @a, i64 0, i64 1
  %2 = load i32, ptr %1, align 4
  %3 = getelementptr inbounds [8 x i32], ptr @c, i64 0, i64 1
  store i32 %2, ptr %3, align 4
  ret void
}
'''

DEREF_GEP_SOURCE = '''define dso_local void @kernel(i32* noundef %p) #0 {
entry:
  %p.addr = alloca i32*, align 8
  store i32* %p, i32** %p.addr, align 8
  %0 = load i32*, i32** %p.addr, align 8
  %1 = load i32, i32* %0, align 4
  %2 = getelementptr inbounds i32, i32* %0, i64 1
  %add = add nsw i32 %1, 1
  store i32 %add, i32* %2, align 4
  ret void
}

attributes #0 = { nounwind }
'''

INT_OPS_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
entry:
  %i = alloca i32, align 4
  store i32 0, i32* %i, align 4
  br label %for.cond

for.cond:
  %0 = load i32, i32* %i, align 4
  %cmp = icmp ult i32 %0, 8
  br i1 %cmp, label %for.body, label %for.end

for.body:
  %1 = load i32, i32* %i, align 4
  %idxprom = zext i32 %1 to i64
  %arrayidx = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %idxprom
  %2 = load i32, i32* %arrayidx, align 4
  %d = sdiv i32 %2, 3
  %r = srem i32 %2, 3
  %ud = udiv i32 %2, 5
  %ur = urem i32 %2, 5
  %an = and i32 %2, 6
  %o = or i32 %d, %r
  %x = xor i32 %an, %o
  %sl = shl i32 %2, 2
  %as = ashr i32 %2, 1
  %ls = lshr i32 %2, 1
  %s1 = add i32 %ud, %ur
  %s2 = add i32 %x, %sl
  %s3 = sub i32 %as, %ls
  %s4 = add i32 %s1, %s2
  %s5 = add i32 %s4, %s3
  %ugt = icmp ugt i32 %2, 1
  %sel = select i1 %ugt, i32 %s5, i32 %ud
  %3 = load i32, i32* %i, align 4
  %idxprom2 = zext i32 %3 to i64
  %arrayidx2 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %idxprom2
  store i32 %sel, i32* %arrayidx2, align 4
  br label %for.inc

for.inc:
  %4 = load i32, i32* %i, align 4
  %inc = add i32 %4, 1
  store i32 %inc, i32* %i, align 4
  br label %for.cond

for.end:
  ret void
}

attributes #0 = { nounwind }
'''

FLOAT_OPS_SOURCE = '''@a = dso_local global [8 x double] zeroinitializer, align 16
@f = dso_local global [8 x float] zeroinitializer, align 16
@c = dso_local global [8 x double] zeroinitializer, align 16
@n = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
entry:
  %i = alloca i32, align 4
  store i32 0, i32* %i, align 4
  br label %for.cond

for.cond:
  %0 = load i32, i32* %i, align 4
  %cmp = icmp slt i32 %0, 8
  br i1 %cmp, label %for.body, label %for.end

for.body:
  %1 = load i32, i32* %i, align 4
  %idxprom = sext i32 %1 to i64
  %arrayidx = getelementptr inbounds [8 x double], [8 x double]* @a, i64 0, i64 %idxprom
  %2 = load double, double* %arrayidx, align 8
  %3 = load i32, i32* %i, align 4
  %idxprom1 = sext i32 %3 to i64
  %arrayidx2 = getelementptr inbounds [8 x float], [8 x float]* @f, i64 0, i64 %idxprom1
  %4 = load float, float* %arrayidx2, align 4
  %ext = fpext float %4 to double
  %sub = fsub double %2, %ext
  %div = fdiv double %sub, 2.000000e+00
  %rem = frem double %2, 3.000000e+00
  %ti = fptosi double %div to i32
  %tf = sitofp i32 %ti to double
  %5 = load i32, i32* %i, align 4
  %tu = uitofp i32 %5 to double
  %fu = fptoui double %tu to i32
  %sum = fadd double %rem, %tf
  %sum2 = fadd double %sum, %tu
  %tr = fptrunc double %sum2 to float
  %6 = load i32, i32* %i, align 4
  %idxprom3 = sext i32 %6 to i64
  %arrayidx4 = getelementptr inbounds [8 x float], [8 x float]* @f, i64 0, i64 %idxprom3
  store float %tr, float* %arrayidx4, align 4
  %sum3 = fadd double %sum2, 1.000000e+00
  %7 = load i32, i32* %i, align 4
  %idxprom5 = sext i32 %7 to i64
  %arrayidx6 = getelementptr inbounds [8 x double], [8 x double]* @c, i64 0, i64 %idxprom5
  store double %sum3, double* %arrayidx6, align 8
  %8 = load i32, i32* %i, align 4
  %idxprom7 = sext i32 %8 to i64
  %arrayidx8 = getelementptr inbounds [8 x i32], [8 x i32]* @n, i64 0, i64 %idxprom7
  store i32 %fu, i32* %arrayidx8, align 4
  br label %for.inc

for.inc:
  %9 = load i32, i32* %i, align 4
  %inc = add nsw i32 %9, 1
  store i32 %inc, i32* %i, align 4
  br label %for.cond

for.end:
  ret void
}

attributes #0 = { nounwind }
'''

SELECT_ADDR_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@b = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel(i32 noundef %n) #0 {
  %1 = icmp sgt i32 %n, 0
  %2 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 1
  %3 = getelementptr inbounds [8 x i32], [8 x i32]* @b, i64 0, i64 1
  %4 = select i1 %1, i32* %2, i32* %3
  store i32 1, i32* %4, align 4
  ret void
}
'''

VECTOR_SOURCE = '''@v = dso_local global <4 x i32> zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = load <4 x i32>, <4 x i32>* @v, align 16
  %2 = add <4 x i32> %1, %1
  store <4 x i32> %2, <4 x i32>* @v, align 16
  ret void
}
'''

AGGREGATE_SOURCE = '''@a = dso_local global [4 x i32] zeroinitializer, align 16
@b = dso_local global [4 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
  %1 = load [4 x i32], [4 x i32]* @a, align 16
  store [4 x i32] %1, [4 x i32]* @b, align 16
  ret void
}
'''

STRUCT_PTR_SOURCE = '''%struct.S = type { i32, i32 }

define dso_local void @kernel(%struct.S* noundef %s) #0 {
  %1 = getelementptr inbounds %struct.S, %struct.S* %s, i32 0, i32 1
  store i32 1, i32* %1, align 4
  ret void
}
'''

TWO_INITS_SOURCE = '''@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel(i32 noundef %n) #0 {
entry:
  %i = alloca i32, align 4
  %cmp = icmp sgt i32 %n, 0
  br i1 %cmp, label %from.zero, label %from.one

from.zero:
  store i32 0, i32* %i, align 4
  br label %for.cond

from.one:
  store i32 1, i32* %i, align 4
  br label %for.cond

for.cond:
  %0 = load i32, i32* %i, align 4
  %cmp1 = icmp slt i32 %0, 8
  br i1 %cmp1, label %for.body, label %for.end

for.body:
  %1 = load i32, i32* %i, align 4
  %idxprom = sext i32 %1 to i64
  %arrayidx = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %idxprom
  store i32 1, i32* %arrayidx, align 4
  br label %for.inc

for.inc:
  %2 = load i32, i32* %i, align 4
  %inc = add nsw i32 %2, 1
  store i32 %inc, i32* %i, align 4
  br label %for.cond

for.end:
  ret void
}
'''

LOCAL_I1_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local i32 @kernel() #0 {
  %i1 = alloca i32, align 4
  store i32 3, i32* %i1, align 4
  %1 = load i32, i32* %i1, align 4
  %2 = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 1
  store i32 %1, i32* %2, align 4
  ret i32 0
}
'''

LATCH_FROM_LATCH_SOURCE = '''@n = dso_local global i32 12, align 4
@a = dso_local global [32 x i32] zeroinitializer, align 16
@b = dso_local global [32 x i32] zeroinitializer, align 16
@c = dso_local global [32 x i32] zeroinitializer, align 16

define dso_local void @f() #0 {
entry:
  %k = alloca i32, align 4
  store i32 0, i32* %k, align 4
  br label %while.cond

while.cond:
  %0 = load i32, i32* %k, align 4
  %1 = load i32, i32* @n, align 4
  %cmp = icmp slt i32 %0, %1
  br i1 %cmp, label %while.body, label %while.end

while.body:
  %2 = load i32, i32* %k, align 4
  %idxprom = sext i32 %2 to i64
  %arrayidx = getelementptr inbounds [32 x i32], [32 x i32]* @a, i64 0, i64 %idxprom
  %3 = load i32, i32* %arrayidx, align 4
  %cmp1 = icmp sgt i32 %3, 0
  br i1 %cmp1, label %if.then, label %if.end6

if.then:
  %4 = load i32, i32* %k, align 4
  %add = add nsw i32 %4, 1
  store i32 %add, i32* %k, align 4
  %5 = load i32, i32* %k, align 4
  %idxprom2 = sext i32 %5 to i64
  %arrayidx3 = getelementptr inbounds [32 x i32], [32 x i32]* @b, i64 0, i64 %idxprom2
  %6 = load i32, i32* %arrayidx3, align 4
  %cmp4 = icmp sgt i32 %6, 0
  br i1 %cmp4, label %if.then5, label %if.end

if.then5:
  br label %while.cond

if.end:
  br label %if.end6

if.end6:
  %7 = load i32, i32* %k, align 4
  %add7 = add nsw i32 %7, 1
  store i32 %add7, i32* %k, align 4
  %8 = load i32, i32* %k, align 4
  %idxprom8 = sext i32 %8 to i64
  %arrayidx9 = getelementptr inbounds [32 x i32], [32 x i32]* @c, i64 0, i64 %idxprom8
  store i32 1, i32* %arrayidx9, align 4
  br label %while.cond

while.end:
  ret void
}

attributes #0 = { nounwind }
'''

BYPASS_SOURCE = '''@a = dso_local global [32 x i32] zeroinitializer, align 16
@c = dso_local global [64 x i32] zeroinitializer, align 16
@d = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local i32 @main() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  store i32 0, i32* %3, align 4
  br label %4

4:
  %5 = load i32, i32* %3, align 4
  %6 = icmp slt i32 %5, 4
  br i1 %6, label %7, label %40

7:
  store i32 0, i32* %2, align 4
  %8 = load i32, i32* %3, align 4
  %9 = sext i32 %8 to i64
  %10 = getelementptr inbounds [32 x i32], [32 x i32]* @a, i64 0, i64 %9
  %11 = load i32, i32* %10, align 4
  %12 = icmp sgt i32 %11, 0
  br i1 %12, label %13, label %32

13:
  br label %14

14:
  %15 = load i32, i32* %2, align 4
  %16 = icmp slt i32 %15, 5
  br i1 %16, label %17, label %31

17:
  %18 = load i32, i32* %2, align 4
  %19 = sext i32 %18 to i64
  %20 = getelementptr inbounds [32 x i32], [32 x i32]* @a, i64 0, i64 %19
  %21 = load i32, i32* %20, align 4
  %22 = load i32, i32* %3, align 4
  %23 = mul nsw i32 %22, 8
  %24 = load i32, i32* %2, align 4
  %25 = add nsw i32 %23, %24
  %26 = sext i32 %25 to i64
  %27 = getelementptr inbounds [64 x i32], [64 x i32]* @c, i64 0, i64 %26
  store i32 %21, i32* %27, align 4
  br label %28

28:
  %29 = load i32, i32* %2, align 4
  %30 = add nsw i32 %29, 1
  store i32 %30, i32* %2, align 4
  br label %14

31:
  br label %32

32:
  %33 = load i32, i32* %2, align 4
  %34 = load i32, i32* %3, align 4
  %35 = sext i32 %34 to i64
  %36 = getelementptr inbounds [8 x i32], [8 x i32]* @d, i64 0, i64 %35
  store i32 %33, i32* %36, align 4
  br label %37

37:
  %38 = load i32, i32* %3, align 4
  %39 = add nsw i32 %38, 1
  store i32 %39, i32* %3, align 4
  br label %4

40:
  %41 = load i32, i32* %3, align 4
  ret i32 %41
}

attributes #0 = { nounwind }
'''

DECL_INIT_SOURCE = '''@a = dso_local global [8 x [8 x i32]] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local i32 @main() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  store i32 0, i32* %3, align 4
  store i32 0, i32* %2, align 4
  br label %4

4:
  %5 = load i32, i32* %2, align 4
  %6 = icmp slt i32 %5, 8
  br i1 %6, label %7, label %35

7:
  store i32 0, i32* %3, align 4
  br label %8

8:
  %9 = load i32, i32* %2, align 4
  %10 = sext i32 %9 to i64
  %11 = getelementptr inbounds [8 x [8 x i32]], [8 x [8 x i32]]* @a, i64 0, i64 %10
  %12 = load i32, i32* %3, align 4
  %13 = sext i32 %12 to i64
  %14 = getelementptr inbounds [8 x i32], [8 x i32]* %11, i64 0, i64 %13
  %15 = load i32, i32* %14, align 4
  %16 = icmp eq i32 %15, 1
  br i1 %16, label %17, label %18

17:
  br label %25

18:
  %19 = load i32, i32* %3, align 4
  %20 = add nsw i32 %19, 1
  store i32 %20, i32* %3, align 4
  %21 = load i32, i32* %3, align 4
  %22 = icmp sge i32 %21, 7
  br i1 %22, label %23, label %24

23:
  br label %25

24:
  br label %8

25:
  %26 = load i32, i32* %3, align 4
  %27 = load i32, i32* %2, align 4
  %28 = add nsw i32 %26, %27
  %29 = load i32, i32* %2, align 4
  %30 = sext i32 %29 to i64
  %31 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %30
  store i32 %28, i32* %31, align 4
  br label %32

32:
  %33 = load i32, i32* %2, align 4
  %34 = add nsw i32 %33, 1
  store i32 %34, i32* %2, align 4
  br label %4

35:
  %36 = load i32, i32* %3, align 4
  ret i32 %36
}

attributes #0 = { nounwind }
'''

ENTRY_LATER_SOURCE = '''@a = dso_local global [8 x i32] zeroinitializer, align 16
@c = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local void @kernel() #0 {
start:
  %i = alloca i32, align 4
  store i32 0, i32* %i, align 4
  br label %for.cond

for.cond:
  %0 = load i32, i32* %i, align 4
  %cmp = icmp slt i32 %0, 8
  br i1 %cmp, label %entry, label %for.end

entry:
  %1 = load i32, i32* %i, align 4
  %idxprom = sext i32 %1 to i64
  %arrayidx = getelementptr inbounds [8 x i32], [8 x i32]* @a, i64 0, i64 %idxprom
  %2 = load i32, i32* %arrayidx, align 4
  %3 = load i32, i32* %i, align 4
  %idxprom2 = sext i32 %3 to i64
  %arrayidx3 = getelementptr inbounds [8 x i32], [8 x i32]* @c, i64 0, i64 %idxprom2
  store i32 %2, i32* %arrayidx3, align 4
  br label %for.inc

for.inc:
  %4 = load i32, i32* %i, align 4
  %inc = add nsw i32 %4, 1
  store i32 %inc, i32* %i, align 4
  br label %for.cond

for.end:
  ret void
}

attributes #0 = { nounwind }
'''

EXTERN_SCALAR_SOURCE = '''@a = dso_local global [16 x i32] zeroinitializer, align 16
@K = external constant i32, align 4
@b = dso_local global [16 x i32] zeroinitializer, align 16

define dso_local void @f() #0 {
entry:
  %i = alloca i32, align 4
  store i32 0, i32* %i, align 4
  br label %for.cond

for.cond:
  %0 = load i32, i32* %i, align 4
  %cmp = icmp slt i32 %0, 16
  br i1 %cmp, label %for.body, label %for.end

for.body:
  %1 = load i32, i32* %i, align 4
  %idxprom = sext i32 %1 to i64
  %arrayidx = getelementptr inbounds [16 x i32], [16 x i32]* @a, i64 0, i64 %idxprom
  %2 = load i32, i32* %arrayidx, align 4
  %3 = load i32, i32* @K, align 4
  %add = add nsw i32 %2, %3
  %4 = load i32, i32* %i, align 4
  %idxprom1 = sext i32 %4 to i64
  %arrayidx2 = getelementptr inbounds [16 x i32], [16 x i32]* @b, i64 0, i64 %idxprom1
  store i32 %add, i32* %arrayidx2, align 4
  br label %for.inc

for.inc:
  %5 = load i32, i32* %i, align 4
  %inc = add nsw i32 %5, 1
  store i32 %inc, i32* %i, align 4
  br label %for.cond

for.end:
  ret void
}

attributes #0 = { nounwind }
'''

BYPASSABLE_LATCH_INIT_SOURCE = '''@n = dso_local global i32 12, align 4
@m = dso_local global i32 6, align 4
@a = dso_local global [16 x i32] zeroinitializer, align 16
@c = dso_local global [16 x i32] zeroinitializer, align 16

define dso_local void @f() #0 {
entry:
  %k = alloca i32, align 4
  store i32 0, i32* %k, align 4
  br label %for.cond

for.cond:
  %0 = load i32, i32* %k, align 4
  %idxprom = sext i32 %0 to i64
  %arrayidx = getelementptr inbounds [16 x i32], [16 x i32]* @a, i64 0, i64 %idxprom
  %1 = load i32, i32* %arrayidx, align 4
  %cmp = icmp sge i32 %1, -5
  br i1 %cmp, label %if.then, label %if.end

if.then:
  br label %for.end

if.end:
  %2 = load i32, i32* %k, align 4
  %add = add nsw i32 %2, 1
  store i32 %add, i32* %k, align 4
  %3 = load i32, i32* %k, align 4
  %4 = load i32, i32* @m, align 4
  %cmp1 = icmp sge i32 %3, %4
  br i1 %cmp1, label %if.then2, label %if.end3

if.then2:
  br label %for.end

if.end3:
  br label %for.cond

for.end:
  br label %while.cond

while.cond:
  %5 = load i32, i32* %k, align 4
  %6 = load i32, i32* @n, align 4
  %cmp4 = icmp slt i32 %5, %6
  br i1 %cmp4, label %while.body, label %while.end

while.body:
  %7 = load i32, i32* %k, align 4
  %idxprom5 = sext i32 %7 to i64
  %arrayidx6 = getelementptr inbounds [16 x i32], [16 x i32]* @c, i64 0, i64 %idxprom5
  store i32 1, i32* %arrayidx6, align 4
  %8 = load i32, i32* %k, align 4
  %add7 = add nsw i32 %8, 1
  store i32 %add7, i32* %k, align 4
  br label %while.cond

while.end:
  ret void
}
'''

CROSS_LOOP_JOIN_SOURCE = '''@a = dso_local global [32 x i32] zeroinitializer, align 16
@c = dso_local global [32 x i32] zeroinitializer, align 16
@d = dso_local global [8 x i32] zeroinitializer, align 16

define dso_local i32 @main() #0 {
  %1 = alloca i32, align 4
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  store i32 0, i32* %1, align 4
  store i32 0, i32* %3, align 4
  br label %4

4:
  %5 = load i32, i32* %3, align 4
  %6 = icmp slt i32 %5, 3
  br i1 %6, label %7, label %55

7:
  store i32 0, i32* %2, align 4
  br label %8

8:
  %9 = load i32, i32* %2, align 4
  %10 = icmp slt i32 %9, 32
  br i1 %10, label %11, label %33

11:
  %12 = load i32, i32* %2, align 4
  %13 = sext i32 %12 to i64
  %14 = getelementptr inbounds [32 x i32], [32 x i32]* @a, i64 0, i64 %13
  %15 = load i32, i32* %14, align 4
  %16 = load i32, i32* %3, align 4
  %17 = add nsw i32 %15, %16
  %18 = icmp eq i32 %17, 5
  br i1 %18, label %19, label %20

19:
  br label %47

20:
  %21 = load i32, i32* %2, align 4
  %22 = sext i32 %21 to i64
  %23 = getelementptr inbounds [32 x i32], [32 x i32]* @a, i64 0, i64 %22
  %24 = load i32, i32* %23, align 4
  %25 = load i32, i32* %3, align 4
  %26 = add nsw i32 %24, %25
  %27 = load i32, i32* %2, align 4
  %28 = sext i32 %27 to i64
  %29 = getelementptr inbounds [32 x i32], [32 x i32]* @c, i64 0, i64 %28
  store i32 %26, i32* %29, align 4
  br label %30

30:
  %31 = load i32, i32* %2, align 4
  %32 = add nsw i32 %31, 1
  store i32 %32, i32* %2, align 4
  br label %8

33:
  store i32 0, i32* %2, align 4
  br label %34

34:
  %35 = load i32, i32* %2, align 4
  %36 = icmp slt i32 %35, 16
  br i1 %36, label %37, label %46

37:
  %38 = load i32, i32* %2, align 4
  %39 = sext i32 %38 to i64
  %40 = getelementptr inbounds [32 x i32], [32 x i32]* @c, i64 0, i64 %39
  %41 = load i32, i32* %40, align 4
  %42 = add nsw i32 %41, 1
  store i32 %42, i32* %40, align 4
  br label %43

43:
  %44 = load i32, i32* %2, align 4
  %45 = add nsw i32 %44, 1
  store i32 %45, i32* %2, align 4
  br label %34

46:
  br label %47

47:
  %48 = load i32, i32* %2, align 4
  %49 = load i32, i32* %3, align 4
  %50 = sext i32 %49 to i64
  %51 = getelementptr inbounds [8 x i32], [8 x i32]* @d, i64 0, i64 %50
  store i32 %48, i32* %51, align 4
  br label %52

52:
  %53 = load i32, i32* %3, align 4
  %54 = add nsw i32 %53, 1
  store i32 %54, i32* %3, align 4
  br label %4

55:
  %56 = load i32, i32* %3, align 4
  ret i32 %56
}
'''

EXTERNAL_CALL_SOURCE = '''@a = dso_local global [16 x i32] zeroinitializer, align 16
@c = dso_local global [16 x i32] zeroinitializer, align 16

define dso_local void @f() #0 {
entry:
  %i = alloca i32, align 4
  store i32 0, i32* %i, align 4
  br label %for.cond

for.cond:
  %0 = load i32, i32* %i, align 4
  %cmp = icmp slt i32 %0, 8
  br i1 %cmp, label %for.body, label %for.end

for.body:
  %1 = load i32, i32* %i, align 4
  %idxprom = sext i32 %1 to i64
  %arrayidx = getelementptr inbounds [16 x i32], [16 x i32]* @a, i64 0, i64 %idxprom
  %2 = load i32, i32* %arrayidx, align 4
  %call = call i32 @g(i32 noundef %2)
  %3 = load i32, i32* %i, align 4
  %idxprom1 = sext i32 %3 to i64
  %arrayidx2 = getelementptr inbounds [16 x i32], [16 x i32]* @c, i64 0, i64 %idxprom1
  store i32 %call, i32* %arrayidx2, align 4
  br label %for.inc

for.inc:
  %4 = load i32, i32* %i, align 4
  %inc = add nsw i32 %4, 1
  store i32 %inc, i32* %i, align 4
  br label %for.cond

for.end:
  ret void
}

declare i32 @g(i32 noundef) #1
'''

SECOND_FUNCTION = '''
define dso_local void @other(i32* noundef %out) #0 {
entry:
  store i32 1, i32* %out, align 4
  ret void
}
'''


class Generated(dict):
    """
    {case key: (source, out_dir, prefix)} of every generated program the
    semantic check G runs. The key is a case name or a prefix; two cases
    under one key hid the first from G, so a repeat is an error. Two
    cases may still share a prefix as long as their output directories
    differ.
    """

    def __setitem__(self, key, value):
        if key in self:
            raise RuntimeError(f"output prefix {key!r} is used by two cases: {self[key][0]} and {value[0]}")
        super().__setitem__(key, value)

    def __missing__(self, key):
        raise RuntimeError(f"case {key!r} produced no programs (its pipeline failed above), "
                           f"so the checks that build on it cannot run")


def check(label, ok, failures):
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok:
        failures.append(label)


def main():
    if any(arg in ('-h', '--help') for arg in sys.argv[1:]):
        print(__doc__)
        return 0
    root = tempfile.mkdtemp(prefix='cgra_regress_')
    failures = []
    generated = Generated()
    try:
        # --- AN: every input is valid LLVM IR ---------------------------
        tool = assembler()
        if tool is None:
            print('  note  AN valid IR    skipped: no llvm-as on PATH')
        else:
            for directory in (TEST_DIR, UNROLL_DIR, NOLOOP_DIR):
                for path in sorted(glob.glob(os.path.join(directory, '*.ll'))):
                    # The generated programs are not modules of their own:
                    # they name registers the other programs define.
                    if re.search(r'_(agu|datapath|merged)\.ll$', path):
                        continue
                    ok, error = assembles(tool, path)
                    check(f'AN valid IR    {os.path.relpath(path, HERE)}', ok, failures)
                    if not ok:
                        print(f'        {error}')

        # --- A / B: mmm under two different hash seeds -----------------
        runs = {}
        for seed in ('1', '999'):
            out = os.path.join(root, f'seed{seed}')
            if not run_pipeline(out, TEST_DIR, 'mmm', 'mmm', seed):
                check(f'A pipeline (seed {seed})', False, failures)
                return 1
            runs[seed] = out

        for name in FINAL_OUTPUTS:
            produced = os.path.join(runs['1'], name)
            check(f'A reference   {name}',
                  os.path.exists(produced)
                  and read(produced) == read(os.path.join(TEST_DIR, name)),
                  failures)
            check(f'B determinism {name}',
                  os.path.exists(produced)
                  and read(produced) == read(os.path.join(runs['999'], name)),
                  failures)

        # --- C: the same program with the arrays renamed ---------------
        ren = os.path.join(root, 'renamed')
        os.makedirs(ren, exist_ok=True)
        source = read(os.path.join(TEST_DIR, 'mmm.ll'))
        renamed = {'a': 'mat1', 'b': 'mat2', 'c': 'mat3'}
        for old, new in renamed.items():
            source = re.sub(rf'@{old}\b', f'@{new}', source)
        with open(os.path.join(ren, 'ren.ll'), 'w') as f:
            f.write(source)
        if run_pipeline(ren, ren, 'ren', 'ren', '1'):
            for old, new in renamed.items():
                produced = os.path.join(ren, f'ren_{new}_agu.ll')
                expected = os.path.join(runs['1'], f'mmm_{old}_agu.ll')
                check(f'C names       ren_{new}_agu.ll',
                      os.path.exists(produced)
                      and read(produced).replace(new, old) == read(expected),
                      failures)
            produced = os.path.join(ren, 'ren_datapath.ll')
            text = read(produced) if os.path.exists(produced) else ''
            for new, old in (('mat1', 'a'), ('mat2', 'b'), ('mat3', 'c')):
                text = text.replace(new, old)
            check('C names       ren_datapath.ll',
                  text == read(os.path.join(runs['1'], 'mmm_datapath.ll')), failures)
        else:
            check('C pipeline (renamed arrays)', False, failures)

        # --- D: different dimensions and element type ------------------
        d16 = os.path.join(root, 'd16')
        os.makedirs(d16, exist_ok=True)
        source = read(os.path.join(TEST_DIR, 'mmm.ll'))
        # The arrays become 16x16 of i64 while the counters stay i32: the
        # element loads, the arithmetic on them and the stores follow the
        # element type, so the file is what clang writes for `long` arrays
        # (a `mul i32` of i64 loads was accepted by nobody but this suite).
        source = retype_elements(source, '[32 x [32 x i32]]', '[16 x [16 x i64]]', 'i64')
        source = re.sub(r'icmp slt i32 (%\d+), 32', r'icmp slt i32 \1, 16', source)
        with open(os.path.join(d16, 'd16.ll'), 'w') as f:
            f.write(source)
        if run_pipeline(d16, d16, 'd16', 'd16', '1'):
            generated['d16'] = (os.path.join(d16, 'd16.ll'), d16, 'd16')
            agu = os.path.join(d16, 'd16_a_agu.ll')
            text = read(agu) if os.path.exists(agu) else ''
            check('D shape/type  AGU declares [16 x [16 x i64]]',
                  '@a = external global [16 x [16 x i64]]' in text, failures)
            check('D shape/type  AGU bound follows the loop',
                  'icmp slt i32 %i1, 16' in text, failures)
            check('D shape/type  AGU loads the element type',
                  'load i64, i64*' in text, failures)
            check('D shape/type  no 32 left in the AGU',
                  not re.search(r'\[32 x|slt i32 %i\d+, 32', text), failures)
            dp = os.path.join(d16, 'd16_datapath.ll')
            # Comments name the block, so read instructions only. The
            # scalar return slot keeps the i32 the source declared, so only
            # the array traffic is checked here.
            text = instructions(dp) if os.path.exists(dp) else ''
            array_lines = [line for line in text.splitlines() if 'gep_' in line]
            check('D shape/type  datapath uses i64',
                  'load i64, i64*' in text
                  and all(' i32 ' not in line for line in array_lines), failures)
        else:
            check('D pipeline (16x16 i64)', False, failures)

        # --- E: unrolled inner loops, odd and even factors ------------
        # 24 is divisible by 1, 3 and 4, so the same array size covers an
        # odd and an even factor with no remainder iteration. An odd factor
        # leaves an odd number of products to reduce, an even one pairs up.
        for factor in (1, 3, 4):
            source = os.path.join(UNROLL_DIR, f'mmm24_unroll{factor}.ll')
            out = os.path.join(root, f'unroll{factor}')
            if not run_pipeline(out, UNROLL_DIR, f'mmm24_unroll{factor}',
                                f'u{factor}', '1'):
                check(f'E unrolling   factor {factor}: pipeline', False, failures)
                continue
            generated[factor] = (source, out, f'u{factor}')

            for array in ('a', 'b'):
                agu = read(os.path.join(out, f'u{factor}_{array}_agu.ll'))
                streams = len(re.findall(r'= getelementptr', agu))
                plural = 'stream' if factor == 1 else 'streams'
                check(f'E unrolling   factor {factor}: {array} has {factor} {plural}',
                      streams == factor, failures)

            # Copy n reads the element n further along.
            agu_a = read(os.path.join(out, f'u{factor}_a_agu.ll'))
            offsets = sorted(int(n) for n in
                             re.findall(r'%off(\d+)_\d+_a_\d+_\d+ = add', agu_a))
            wanted = list(range(1, factor))
            check(f'E unrolling   factor {factor}: offsets are '
                  + (', '.join(f'+{n}' for n in wanted) if wanted else 'none'),
                  offsets == wanted, failures)

            # The index advances by the unroll factor, not by one.
            check(f'E unrolling   factor {factor}: index advances by {factor}',
                  re.search(rf'%i3_next = add i32 %i3, {factor}\b', agu_a)
                  is not None, failures)

            # One multiply per copy, each on its own pair of loads.
            datapath = read(os.path.join(out, f'u{factor}_datapath.ll'))
            muls = re.findall(r'= mul \S+ (%\S+), (%\S+)', datapath)
            operands = [reg for pair in muls for reg in pair]
            check(f'E unrolling   factor {factor}: {factor} multiplies on '
                  f'{2 * factor} distinct loads',
                  len(muls) == factor and len(set(operands)) == 2 * factor,
                  failures)

            # A read-modify-write is one stream, addressed once.
            agu_c = read(os.path.join(out, f'u{factor}_c_agu.ll'))
            if '\n22:' not in agu_c:
                raise RuntimeError('the inner body of the unrolled example is no longer block 22')
            body_c = agu_c.split('\n22:', 1)[-1].split('\n\n', 1)[0]
            check(f'E unrolling   factor {factor}: c is one accumulator stream',
                  body_c.count('= getelementptr') == 1
                  and '= load' in body_c and 'store ' in body_c, failures)

            check_linkage(out, f'u{factor}', f'unroll {factor}', failures)

        # --- H / I: inter-nest dependency, and several products -------
        for name in ('between', 'two', 'mixed'):
            source = os.path.join(UNROLL_DIR, f'mmm24_{name}.ll')
            out = os.path.join(root, name)
            if not run_pipeline(out, UNROLL_DIR, f'mmm24_{name}', name, '1'):
                check(f'H/I {name}: pipeline', False, failures)
                continue
            generated[name] = (source, out, name)
            check_linkage(out, name, name, failures)
            datapath = read(os.path.join(out, f'{name}_datapath.ll'))

            if name in ('between', 'mixed'):
                # v[i] is produced between the outer and middle loops...
                produced = re.search(r'(%\S+) = add \S+ %i\d+, \d+$', datapath, re.M)
                check(f'H inter-nest  {name}: v[i] is computed from the outer index',
                      produced is not None, failures)
                check(f'H inter-nest  {name}: and stored through the AGU address',
                      produced is not None
                      and re.search(rf'store \S+ {re.escape(produced.group(1))}, '
                                    r'\S+ %gep_v_\d+_\d+', datapath) is not None,
                      failures)
                # ...and consumed by the innermost block, as the right
                # operand: the source multiplies the product by v[i].
                check(f'H inter-nest  {name}: the inner product scales by v[i]',
                      re.search(r'= mul \S+ %\S+, %load_v_\S+', datapath) is not None,
                      failures)

            if name in ('two', 'mixed'):
                # Each accumulator keeps its own value and its own address.
                # Pairs, not a dict: keyed by value, two stores of the same
                # register collapsed into one and the check became a
                # tautology.
                pairs = re.findall(r'store \S+ (%\S+), \S+ (%gep_[a-z]+_\d+_\d+)', datapath)
                arrays = {ptr.split('_')[1] for _, ptr in pairs}
                values = [value for value, _ in pairs]
                check(f'I products    {name}: c and f are stored separately',
                      {'c', 'f'} <= arrays, failures)
                check(f'I products    {name}: each store has its own value',
                      len(set(values)) == len(values) and len(values) >= 2, failures)

        # --- J: a program with no loops ------------------------------
        noloop = os.path.join(root, 'noloop')
        if run_pipeline(noloop, NOLOOP_DIR, 'straight', 'st', '1'):
            generated['straight'] = (os.path.join(NOLOOP_DIR, 'straight.ll'), noloop, 'st')
            for array in ('a', 'b', 'c'):
                agu = os.path.join(noloop, f'st_{array}_agu.ll')
                check(f'J no loops    an AGU program exists for {array}',
                      os.path.exists(agu), failures)
            agu_a = read(os.path.join(noloop, 'st_a_agu.ll'))
            # Constant subscripts need no index register and no widening.
            check('J no loops    subscripts are literals',
                  re.search(r'getelementptr .*@a, i64 0, i64 \d+', agu_a) is not None
                  and 'alloca' not in agu_a and 'sext' not in agu_a, failures)
            datapath = instructions(os.path.join(noloop, 'st_datapath.ll'))
            array_stores = [line for line in datapath.splitlines()
                            if line.startswith('store') and 'gep_' in line]
            check('J no loops    the datapath computes and stores',
                  '= mul ' in datapath and '= add ' in datapath
                  and len(array_stores) == 2, failures)
            check_linkage(noloop, 'st', 'no loops', failures)
        else:
            check('J no loops    pipeline', False, failures)

        # --- K: setup, loop nest, teardown ---------------------------
        # 'wrapped' is the plain shape; 'program' is the same shape at a
        # size worth testing: three nesting levels, two products, a 2x
        # unrolled body and an inter-nest value, 8 arrays in all.
        # The four ways of mixing arrays and scalars inside and outside
        # the nest: array/array, scalar/array, array/scalar, scalar/scalar.
        for name, prefix in (('wrapped', 'wr'), ('program', 'pg'),
                             ('scalar_ends', 'sc'),
                             ('array_out_scalar_in', 'ai'),
                             ('scalar_only', 'so')):
            out = os.path.join(root, name)
            if not run_pipeline(out, NOLOOP_DIR, name, prefix, '1'):
                check(f'K whole shape {name}: pipeline', False, failures)
                continue
            generated[name] = (os.path.join(NOLOOP_DIR, f'{name}.ll'), out, prefix)

            if name in ('array_out_scalar_in', 'scalar_only'):
                # The nest touches no array, so no array gets an AGU from
                # it; the scalar it loads and stores does.
                slot_agu = glob.glob(os.path.join(out, f'{prefix}_s*_agu.ll'))
                check(f'M mixing      {name}: the nest scalar gets an AGU',
                      len(slot_agu) == 1, failures)
                array_agu = [p for p in glob.glob(os.path.join(out, f'{prefix}_*_agu.ll'))
                             if p not in slot_agu]
                expected_arrays = 0 if name == 'scalar_only' else 3
                check(f'M mixing      {name}: {expected_arrays} array AGU programs',
                      len(array_agu) == expected_arrays, failures)
                datapath = read(os.path.join(out, f'{prefix}_datapath.ll'))
                check(f'M mixing      {name}: the nest accumulates through the AGU',
                      re.search(r'= add \S+ %i\d+, %load_s\d+_', datapath) is not None
                      or re.search(r'= add \S+ %load_s\d+_\S+, %i\d+', datapath)
                      is not None, failures)
                check_linkage(out, prefix, name, failures)
                continue

            if name == 'scalar_ends':
                # Nothing outside the nest touches an array, so the AGU has
                # no stream there -- but the block must still exist so the
                # loop can branch to it, and the datapath must carry the
                # scalar work.
                agu_a = read(os.path.join(out, f'{prefix}_a_agu.ll'))
                outer_exit = re.search(
                    r'br i1 %cond_i1, label %\w+, label %(\w+)', agu_a)
                check(f'L scalar ends {name}: the nest exits into the epilogue',
                      outer_exit is not None and outer_exit.group(1) != 'ret',
                      failures)
                check(f'L scalar ends {name}: the epilogue block exists',
                      outer_exit is not None
                      and outer_exit.group(1) + ':' in agu_a, failures)
                # Keep the '; block' comments: they delimit the groups.
                datapath = read(os.path.join(out, f'{prefix}_datapath.ll'))
                # A scalar the loop loads and stores is streamed memory,
                # so the AGU owns it: it gets a program of its own, named
                # after the slot.
                slot_agu = glob.glob(os.path.join(out, f'{prefix}_s*_agu.ll'))
                check(f'L scalar ends {name}: the scalar gets its own AGU',
                      len(slot_agu) == 1, failures)
                if slot_agu:
                    text = read(slot_agu[0])
                    check(f'L scalar ends {name}: it is a scalar object',
                          re.search(r'@s\d+ = external global i32', text) is not None,
                          failures)
                    check(f'L scalar ends {name}: setup writes it',
                          re.search(r'store i32 3, i32\* %gep_s\d+_entry_0', text)
                          is not None, failures)
                # The nest reads it back and scales the product by it.
                datapath = read(os.path.join(out, f'{prefix}_datapath.ll'))
                scaled = False
                for group in datapath.split('; block ')[1:]:
                    if '%load_a_' not in group:
                        continue
                    for left, right in re.findall(r'= mul \S+ (\S+), (\S+)', group):
                        if 'load_s' in left or 'load_s' in right:
                            scaled = True
                check(f'L scalar ends {name}: the nest reads the scalar',
                      scaled, failures)
                check_linkage(out, prefix, name, failures)
                continue

            agu_p = read(os.path.join(out, f'{prefix}_p_agu.ll'))
            # The label is followed by a newline, so skip the empty first
            # element before taking lines up to the block's blank line.
            entry_block = []
            for line in agu_p.split('entry:', 1)[-1].splitlines():
                if not line.strip():
                    if entry_block:
                        break
                    continue
                entry_block.append(line)
            check(f'K whole shape {name}: the prologue is generated',
                  any('%gep_p_entry_0' in line for line in entry_block), failures)
            check(f'K whole shape {name}: the epilogue is generated',
                  re.search(r'%gep_p_\d+_1', agu_p) is not None, failures)
            # The outermost loop must leave to the epilogue, not to ret.
            agu_a = read(os.path.join(out, f'{prefix}_a_agu.ll'))
            outer_exit = re.search(r'br i1 %cond_i1, label %\w+, label %(\w+)', agu_a)
            check(f'K whole shape {name}: the nest exits into the epilogue',
                  outer_exit is not None and outer_exit.group(1) != 'ret', failures)
            # Both ends must appear in the datapath too.
            datapath = read(os.path.join(out, f'{prefix}_datapath.ll'))
            check(f'K whole shape {name}: the datapath covers both ends',
                  'gep_p_entry_0' in datapath
                  and re.search(r'store \S+ %\S+, \S+ %gep_p_\d+_1', datapath)
                  is not None, failures)
            check_linkage(out, prefix, name, failures)

        # --- N: non-square arrays, three different trip counts --------
        out = os.path.join(root, 'shape')
        if run_pipeline(out, UNROLL_DIR, 'mmm_shape', 'sh', '1'):
            generated['shape'] = (os.path.join(UNROLL_DIR, 'mmm_shape.ll'), out, 'sh')
            agu_a = read(os.path.join(out, 'sh_a_agu.ll'))
            for level, bound in (('1', 16), ('2', 8), ('3', 32)):
                check(f'N shape       level {level} runs to {bound}',
                      f'icmp slt i32 %i{level}, {bound}' in agu_a, failures)
            for array, shape in (('a', '[16 x [32 x i32]]'), ('b', '[32 x [8 x i32]]'),
                                 ('c', '[16 x [8 x i32]]')):
                text = read(os.path.join(out, f'sh_{array}_agu.ll'))
                check(f'N shape       {array} is declared {shape}',
                      f'@{array} = external global {shape}' in text, failures)
            check_linkage(out, 'sh', 'shape', failures)
        else:
            check('N shape       pipeline', False, failures)

        # --- O: counters from 1, loops tested with sle ----------------
        out = os.path.join(root, 'start')
        if run_pipeline(out, UNROLL_DIR, 'mmm24_start', 'sl', '1'):
            generated['start'] = (os.path.join(UNROLL_DIR, 'mmm24_start.ll'), out, 'sl')
            agu_a = read(os.path.join(out, 'sl_a_agu.ll'))
            check('O start/test  the outermost counter starts at 1',
                  re.search(r'entry:\n(?:[ \t].*\n)*?[ \t]+store i32 1, i32\* %i1_ptr', agu_a)
                  is not None, failures)
            check('O start/test  nested counters are reset to 1',
                  'store i32 1, i32* %i2_ptr' in agu_a
                  and 'store i32 1, i32* %i3_ptr' in agu_a, failures)
            check('O start/test  loops test sle 23',
                  all(f'icmp sle i32 %i{level}, 23' in agu_a for level in '123'),
                  failures)
            check('O start/test  no slt or 0 left',
                  'slt' not in agu_a and 'store i32 0,' not in agu_a, failures)
            check_linkage(out, 'sl', 'start', failures)
        else:
            check('O start/test  pipeline', False, failures)

        # --- P: negative subscript offsets ----------------------------
        out = os.path.join(root, 'minus')
        if run_pipeline(out, UNROLL_DIR, 'mmm24_minus3', 'mn', '1'):
            generated['minus'] = (os.path.join(UNROLL_DIR, 'mmm24_minus3.ll'), out, 'mn')
            agu_a = read(os.path.join(out, 'mn_a_agu.ll'))
            offsets = sorted(int(n) for n in re.findall(r'%offm(\d+)_3_a_\d+_\d+ = sub', agu_a))
            check('P negative    offsets are -1, -2',
                  offsets == [1, 2], failures)
            check('P negative    the inner counter starts at 2',
                  'store i32 2, i32* %i3_ptr' in agu_a, failures)
            check('P negative    every access keeps both subscripts',
                  all(line.count('i64 %sext_') == 2 for line in agu_a.splitlines()
                      if '= getelementptr' in line), failures)
            check_linkage(out, 'mn', 'minus', failures)
        else:
            check('P negative    pipeline', False, failures)

        # --- Q: a two-block while loop --------------------------------
        out = os.path.join(root, 'while')
        if run_pipeline(out, UNROLL_DIR, 'mmm24_while', 'wh', '1'):
            generated['while'] = (os.path.join(UNROLL_DIR, 'mmm24_while.ll'), out, 'wh')
            loops = ast.literal_eval(read(os.path.join(out, 'mmm24_while_merged_cfg_loop.txt')))
            check('Q while       three loops are detected', len(loops) == 3, failures)
            check('Q while       the inner loop has two blocks',
                  loops and len(loops[0]) == 2, failures)
            agu_a = read(os.path.join(out, 'wh_a_agu.ll'))
            if loops and len(loops[0]) == 2:
                body = agu_a.split(f'\n{loops[0][1]}:', 1)[-1].split('\n\n', 1)[0]
                check('Q while       the body addresses a and advances the counter',
                      '%gep_a_' in body and '%i3_next = add i32 %i3, 1' in body
                      and f'br label %{loops[0][0]}' in body, failures)
            check_linkage(out, 'wh', 'while', failures)
        else:
            check('Q while       pipeline', False, failures)

        # --- R: two nests in sequence ---------------------------------
        out = os.path.join(root, 'seq')
        if run_pipeline(out, UNROLL_DIR, 'mmm24_seq', 'sq', '1'):
            generated['seq'] = (os.path.join(UNROLL_DIR, 'mmm24_seq.ll'), out, 'sq')
            loops = ast.literal_eval(read(os.path.join(out, 'mmm24_seq_merged_cfg_loop.txt')))
            check('R sequential  six loops are detected', len(loops) == 6, failures)
            agus = sorted(os.path.basename(p)
                          for p in glob.glob(os.path.join(out, 'sq_*_agu.ll')))
            check('R sequential  every array gets an AGU program',
                  agus == [f'sq_{n}_agu.ll' for n in 'abcdef'], failures)
            agu_a = read(os.path.join(out, 'sq_a_agu.ll'))
            # Two nests over the same three variables: six loop levels, three
            # slots (one per variable, shared by the nests in sequence).
            check('R sequential  six index registers over three shared slots',
                  all(f'%i{n} = load' in agu_a for n in '123456')
                  and all(f'%i{n}_ptr = alloca' in agu_a for n in '123')
                  and not any(f'%i{n}_ptr' in agu_a for n in '456'), failures)
            check('R sequential  the second nest re-initialises its counter',
                  agu_a.count('store i32 0, i32* %i1_ptr') == 2
                  and '%i4 = load i32, i32* %i1_ptr' in agu_a, failures)
            check_linkage(out, 'sq', 'sequential', failures)
        else:
            check('R sequential  pipeline', False, failures)

        # --- S: named labels and allocas ------------------------------
        out = os.path.join(root, 'names')
        if run_pipeline(out, UNROLL_DIR, 'mmm24_names', 'nm', '1'):
            generated['names'] = (os.path.join(UNROLL_DIR, 'mmm24_names.ll'), out, 'nm')
            agu_a = read(os.path.join(out, 'nm_a_agu.ll'))
            check('S names       blocks keep their names',
                  'for.body.k:' in agu_a and 'for.inc.k:' in agu_a
                  and 'for.end.i:' in agu_a, failures)
            check('S names       streams are named after the block',
                  '%gep_a_for.body.k_0' in agu_a, failures)
            check_linkage(out, 'nm', 'names', failures)
        else:
            check('S names       pipeline', False, failures)

        # --- T: opaque pointers ---------------------------------------
        out = os.path.join(root, 'opaque')
        if run_pipeline(out, UNROLL_DIR, 'mmm24_opaque', 'op', '1'):
            generated['opaque'] = (os.path.join(UNROLL_DIR, 'mmm24_opaque.ll'), out, 'op')
            if 1 in generated:
                _, typed_out, _ = generated[1]
                for name in ('a_agu', 'b_agu', 'c_agu', 'datapath'):
                    check(f'T opaque      {name} matches the typed program',
                          read(os.path.join(out, f'op_{name}.ll'))
                          == read(os.path.join(typed_out, f'u1_{name}.ll')), failures)
            check_linkage(out, 'op', 'opaque', failures)
        else:
            check('T opaque      pipeline', False, failures)

        # --- U..AA: control flow and memory shapes inside the body ------
        shapes = [
            ('U copy       ', 'mmm24_copy', 'cp'),
            ('V if         ', 'mmm24_if', 'if'),
            ('W switch     ', 'mmm24_switch', 'sw'),
            ('X continue   ', 'mmm24_continue', 'ct'),
            ('Y do-while   ', 'mmm24_do', 'do'),
            ('Z variables  ', 'mmm24_variables', 'vb'),
            ('AA local     ', 'mmm24_local', 'lc'),
        ]
        for label, base, prefix in shapes:
            out = os.path.join(root, prefix)
            if not run_pipeline(out, UNROLL_DIR, base, prefix, '1'):
                check(f'{label}pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(UNROLL_DIR, f'{base}.ll'), out, prefix)
            agu_a = read(os.path.join(out, f'{prefix}_a_agu.ll'))
            agu_c = read(os.path.join(out, f'{prefix}_c_agu.ll'))
            datapath = instructions(os.path.join(out, f'{prefix}_datapath.ll'))
            loops = ast.literal_eval(read(os.path.join(out, f'{base}_merged_cfg_loop.txt')))

            if prefix == 'cp':
                check(f'{label}the datapath does no arithmetic',
                      '= mul' not in datapath and '= add' not in datapath, failures)
                check(f'{label}c stores the value a loaded',
                      re.search(r'store i32 %load_a_\d+_0, i32\* %gep_c_', agu_c) is not None,
                      failures)
            elif prefix == 'if':
                check(f'{label}the datapath computes the condition',
                      re.search(r'= icmp sgt i32 %load_a_\S+, 0', datapath) is not None,
                      failures)
                check(f'{label}the AGU branches on it',
                      re.search(r'br i1 %\d+, label %\d+, label %\d+', agu_a) is not None,
                      failures)
            elif prefix == 'sw':
                check(f'{label}the datapath computes the selector',
                      re.search(r'= srem i32 %i3, 3', datapath) is not None, failures)
                check(f'{label}the AGU switches on it',
                      re.search(r'switch i32 %\d+, label %\d+ \[ i32 0, label %\d+ i32 1, label %\d+ \]',
                                agu_a) is not None, failures)
            elif prefix == 'ct':
                inner = min(loops, key=len)
                check(f'{label}the inner loop has two latches',
                      len(inner) == 4, failures)
                check(f'{label}both latches advance the counter',
                      '%i3_next = add i32 %i3, 1' in agu_a
                      and re.search(r'%i3_next_\d+ = add i32 %i3, 1', agu_a) is not None,
                      failures)
            elif prefix == 'do':
                check(f'{label}the inner loop is one block',
                      any(len(loop) == 1 for loop in loops), failures)
                one = [loop for loop in loops if len(loop) == 1][0][0]
                block = agu_a.split(f'\n{one}:', 1)[-1].split('\n\n', 1)[0]
                check(f'{label}the block advances before it compares',
                      block.index('%i3_next = add') < block.index('%cond_i3 = icmp'),
                      failures)
            elif prefix == 'vb':
                check(f'{label}the bound is a loaded value',
                      re.search(r'%cond_i1 = icmp slt i32 %i1, %load_n_\S+', agu_a) is not None,
                      failures)
                check(f'{label}the start is a loaded value',
                      re.search(r'store i32 %load_s\w+, i32\* %i1_ptr', agu_a) is not None,
                      failures)
                check(f'{label}the bound object gets an AGU program',
                      os.path.exists(os.path.join(out, f'{prefix}_n_agu.ll')), failures)
            elif prefix == 'lc':
                local = glob.glob(os.path.join(out, f'{prefix}_l*_agu.ll'))
                check(f'{label}the local array gets an AGU program', len(local) == 1, failures)
                if local:
                    text = read(local[0])
                    check(f'{label}declared with its own shape',
                          re.search(r'@l\w+ = external global \[24 x i32\]', text) is not None,
                          failures)
                    check(f'{label}stored and loaded through one stream',
                          re.search(r'store i32 %load_a_\w+, i32\* (%gep_l\w+), align 4\n'
                                    r'\s+%load_l\w+ = load i32, i32\* \1,', text) is not None,
                          failures)
            check_linkage(out, prefix, label.strip(), failures)

        # --- AB..AH: subscripts, pointers, counters, cycles -------------
        shapes = [
            ('AB expr       ', 'mmm24_expr', 'ex'),
            ('AC indirect   ', 'mmm24_indirect', 'in'),
            ('AD pointers   ', 'mmm24_ptr', 'pt'),
            ('AE step       ', 'mmm24_vstep', 'vs'),
            ('AF sentinel   ', 'mmm24_sentinel', 'sn'),
            ('AG do-pre     ', 'mmm24_dopre', 'dp'),
            ('AH irreducible', 'mmm24_irreducible', 'ir'),
        ]
        for label, base, prefix in shapes:
            out = os.path.join(root, prefix)
            if not run_pipeline(out, UNROLL_DIR, base, prefix, '1'):
                check(f'{label}pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(UNROLL_DIR, f'{base}.ll'), out, prefix)
            a_name = 'ptr_a' if prefix == 'pt' else 'a'
            b_name = 'ptr_b' if prefix == 'pt' else 'b'
            agu_a = read(os.path.join(out, f'{prefix}_{a_name}_agu.ll'))
            agu_b = read(os.path.join(out, f'{prefix}_{b_name}_agu.ll'))
            datapath = instructions(os.path.join(out, f'{prefix}_datapath.ll'))
            loops = ast.literal_eval(read(os.path.join(out, f'{base}_merged_cfg_loop.txt')))

            if prefix == 'ex':
                check(f'{label}the AGU computes the subscript',
                      re.search(r'%idx\d+_b_\d+_0 = add i32 %i3, %i2\n'
                                r'\s+%idx\d+_b_\d+_0 = srem i32 %idx\d+_b_\d+_0, 24', agu_b)
                      is not None, failures)
            elif prefix == 'in':
                check(f'{label}the subscript is a loaded value',
                      re.search(r'sext i32 %load_idx_\d+_0 to i64', agu_b) is not None, failures)
                check(f'{label}idx gets an AGU program',
                      os.path.exists(os.path.join(out, f'{prefix}_idx_agu.ll')), failures)
            elif prefix == 'pt':
                check(f'{label}declared without an extent',
                      '@ptr_a = external global [0 x i32]' in agu_a, failures)
                check(f'{label}indexed by the computed offset',
                      re.search(r'%idx\d+_ptr_a_\d+_0 = mul i32 %i1, 24\n'
                                r'\s+%idx\d+_ptr_a_\d+_0 = add i32 %idx\d+_ptr_a_\d+_0, %i3', agu_a)
                      is not None, failures)
            elif prefix == 'vs':
                check(f'{label}the step is a loaded value',
                      re.search(r'%i3_next = add i32 %i3, %load_step_\d+_0', agu_a) is not None,
                      failures)
            elif prefix == 'sn':
                inner = min(loops, key=len)
                header = inner[0]
                block = agu_a.split(f'\n{header}:', 1)[-1].split('\n\n', 1)[0]
                check(f'{label}the header loads the probe and branches on the datapath',
                      '%load_a_' in block and re.search(r'br i1 %\d+, label', block) is not None,
                      failures)
                check(f'{label}the datapath computes the compare',
                      re.search(r'= icmp ne i32 %load_a_\S+, 0', datapath) is not None, failures)
            elif prefix == 'dp':
                one = [loop for loop in loops if len(loop) == 1][0][0]
                block = agu_a.split(f'\n{one}:', 1)[-1].split('\n\n', 1)[0]
                check(f'{label}the block compares the value before the update',
                      '%cond_i3 = icmp slt i32 %i3, 23' in block
                      and block.index('%i3_next = add') < block.index('%cond_i3'), failures)
            elif prefix == 'ir':
                check(f'{label}only the two natural loops are reported', len(loops) == 2, failures)
                check(f'{label}the cycle counter is a streamed scalar',
                      re.search(r'sext i32 %load_s\d+_\S+ to i64', agu_a) is not None, failures)
            check_linkage(out, prefix, label.strip(), failures)

        # --- AI..AM: types, parameters, calls, a break-driven loop --------
        shapes = [
            ('AI float      ', 'mmm24_float', 'fl'),
            ('AJ parameter  ', 'mmm24_param', 'pm'),
            ('AK call       ', 'mmm24_call', 'cl'),
            ('AL select     ', 'mmm24_select', 'se'),
            ('AM break      ', 'mmm24_break', 'bk'),
        ]
        for label, base, prefix in shapes:
            out = os.path.join(root, prefix)
            if not run_pipeline(out, UNROLL_DIR, base, prefix, '1'):
                check(f'{label}pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(UNROLL_DIR, f'{base}.ll'), out, prefix)
            agu_a = read(os.path.join(out, f'{prefix}_a_agu.ll'))
            datapath = read(os.path.join(out, f'{prefix}_datapath.ll'))

            if prefix == 'fl':
                check(f'{label}the AGU loads doubles',
                      re.search(r'%load_a_\S+ = load double, double\*', agu_a) is not None, failures)
                check(f'{label}the datapath multiplies doubles and casts the counter',
                      re.search(r'= fmul double %load_a_\S+, %load_b_', datapath) is not None
                      and '= sitofp i32 %i3 to double' in datapath, failures)
            elif prefix == 'pm':
                check(f'{label}the parameter is read from its input global',
                      '@arg_n = external global i32' in datapath
                      and '%n = load i32, i32* @arg_n' in datapath, failures)
                check(f'{label}the loops compare against it',
                      re.search(r'%cond_i1 = icmp slt i32 %i1, %load_s\w+', agu_a) is not None,
                      failures)
            elif prefix == 'cl':
                check(f'{label}the datapath calls the intrinsic',
                      re.search(r'= call i32 @llvm\.smax\.i32\(i32 %\d+, i32 0\)', datapath)
                      is not None, failures)
            elif prefix == 'se':
                check(f'{label}the datapath selects',
                      re.search(r'= select i1 %\d+, i32 %\d+, i32 0', datapath) is not None, failures)
            elif prefix == 'bk':
                check(f'{label}the latch decides on the advanced counter',
                      re.search(r'%i3_next = add i32 %i3, 1\n\s+store i32 %i3_next, i32\* %i3_ptr, align 4\n'
                                r'\s+br i1 %\d+, label', agu_a) is not None, failures)
                check(f'{label}the datapath compares the advanced counter',
                      '= icmp slt i32 %i3_next, 24' in datapath, failures)
            check_linkage(out, prefix, label.strip(), failures)

        # --- AO: parameter attributes ------------------------------------
        for base, prefix, old, new in (
                ('mmm24_param', 'pm', 'i32 %n', 'i32 noundef %n'),
                ('mmm24_ptr', 'pt', 'i32* %', 'i32* noundef %')):
            plain_source, plain_out, _ = generated[prefix]
            attributed = os.path.join(root, f'attr_{prefix}')
            os.makedirs(attributed, exist_ok=True)
            source = read(plain_source)
            define = re.search(r'^define\b.*$', source, re.M).group(0)
            with open(os.path.join(attributed, f'{base}.ll'), 'w') as f:
                f.write(source.replace(define, define.replace(old, new)))
            out = os.path.join(attributed, 'out')
            label = f'AO attributes {base}'
            if not run_pipeline(out, attributed, base, prefix, '1'):
                check(f'{label}: pipeline', False, failures)
                continue
            names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(plain_out, f'{prefix}_*.ll')))
            same = all(read(os.path.join(out, name)) == read(os.path.join(plain_out, name))
                       for name in names)
            check(f'{label}: the same programs as without them', same, failures)

        # --- AP: counter ownership --------------------------------------
        do_source = read(os.path.join(UNROLL_DIR, 'mmm24_do.ll'))
        latch = re.search(r'\n(\s+%(\d+) = add nsw i32 %\d+, 1\n\s+store i32 %\2, i32\* (%\d+), align 4\n)'
                          r'\s+%\d+ = load i32, i32\* \3', do_source)
        if latch is None:
            raise RuntimeError('mmm24_do.ll no longer has the latch shape AP, AR expect')
        update, k_slot = latch.group(1), latch.group(3)

        # (a) an assignment to the counter after the nest is refused
        owned = os.path.join(root, 'owned')
        os.makedirs(owned, exist_ok=True)
        with open(os.path.join(owned, 'owned.ll'), 'w') as f:
            f.write(do_source.replace('  ret i32', f'  store i32 7, i32* {k_slot}, align 4\n  ret i32', 1))
        ok, text = run_stages(os.path.join(owned, 'out'), owned, 'owned', 'ow', '1')
        check('AP ownership  an assignment after the loop is refused',
              not ok and 'is a loop counter' in text, failures)

        # (b) two updates in one latch: the slot is no counter at all
        twice = os.path.join(root, 'twice')
        os.makedirs(twice, exist_ok=True)
        second = (f'  %900 = load i32, i32* {k_slot}, align 4\n  %901 = add nsw i32 %900, 1\n'
                  f'  store i32 %901, i32* {k_slot}, align 4\n')
        with open(os.path.join(twice, 'twice.ll'), 'w') as f:
            f.write(renumber(do_source.replace(update, update + second, 1)))
        out = os.path.join(twice, 'out')
        if run_pipeline(out, twice, 'twice', 'tw', '1'):
            generated['tw'] = (os.path.join(twice, 'twice.ll'), out, 'tw')
            check('AP ownership  a counter updated twice per latch is a plain scalar',
                  os.path.exists(os.path.join(out, f'tw_s{k_slot[1:]}_agu.ll'))
                  and '%i3_next' not in read(os.path.join(out, 'tw_a_agu.ll')), failures)
        else:
            check('AP ownership  twice: pipeline', False, failures)

        # --- AQ: *p through a pointer parameter -------------------------
        deref = os.path.join(root, 'deref')
        os.makedirs(deref, exist_ok=True)
        with open(os.path.join(deref, 'deref.ll'), 'w') as f:
            f.write(DEREF_SOURCE)
        out = os.path.join(deref, 'out')
        if run_pipeline(out, deref, 'deref', 'dr', '1'):
            generated['dr'] = (os.path.join(deref, 'deref.ll'), out, 'dr')
            programs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(out, 'dr_*_agu.ll')))
            check('AQ deref      the pointer is an object, not a scalar',
                  programs == ['dr_a_agu.ll', 'dr_ptr_out_agu.ll'], failures)
            check('AQ deref      *out is element 0 of it',
                  re.search(r'%gep_ptr_out_\S+ = getelementptr inbounds \[0 x i32\], \[0 x i32\]\* '
                            r'@ptr_out, i64 0, i64 0', read(os.path.join(out, 'dr_ptr_out_agu.ll')))
                  is not None, failures)
            check_linkage(out, 'dr', 'AQ deref', failures)
        else:
            check('AQ deref      pipeline', False, failures)

        # --- AR: the advanced counter stored in the latch ----------------
        late = os.path.join(root, 'late')
        os.makedirs(late, exist_ok=True)
        use = (f'  %910 = load i32, i32* {k_slot}, align 4\n  %911 = sext i32 %910 to i64\n'
               f'  %912 = getelementptr inbounds [25 x i32], [25 x i32]* @d, i64 0, i64 %911\n'
               f'  store i32 %910, i32* %912, align 4\n')
        text = do_source.replace(update, update + use, 1)
        text = text.replace('define ', '@d = dso_local global [25 x i32] zeroinitializer, align 16\ndefine ', 1)
        with open(os.path.join(late, 'late.ll'), 'w') as f:
            f.write(renumber(text))
        out = os.path.join(late, 'out')
        if run_pipeline(out, late, 'late', 'lt', '1'):
            generated['lt'] = (os.path.join(late, 'late.ll'), out, 'lt')
            agu_d = read(os.path.join(out, 'lt_d_agu.ll'))
            check('AR late use   the store follows the update it uses',
                  re.search(r'%i3_next = add i32 %i3, 1\n(?:.*\n)*?\s+store i32 %i3_next, i32\* %gep_d_',
                            agu_d) is not None, failures)
            check_linkage(out, 'lt', 'AR late use', failures)
        else:
            check('AR late use   pipeline', False, failures)

        # --- AS: the verifier notices ------------------------------------
        mmm_source = os.path.join(TEST_DIR, 'mmm.ll')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_c_agu.ll'), '  store i32 %45, i32* %gep_c_22_0, align 4\n', ''),
            failures, 'AGU store deleted', 'the datapath sent values no AGU program stored')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), '%45 = add i32 %load_c_22_0, %37\n', ''),
            failures, 'datapath value deleted', "nobody defines: {'mmm_c_agu.ll': 'store i32 %45")
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), '%37 = mul i32', '%37 = fmul double'),
            failures, 'operation type changed', 'is used as double')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), 'store i32 %45, i32* %gep_c_22_0, align 4\n', ''),
            failures, 'datapath store deleted', "nobody defines: {'mmm_c_agu.ll': 'store i32 %45")
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), 'store i32 %45, i32* %gep_c_22_0', 'store i32 %45, i32* %gep_a_22_0'),
            failures, 'datapath store misdirected', "nobody defines: {'mmm_c_agu.ll': 'store i32 %45")
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), 'store i32 0, i32* %1, align 4', 'store i32 5, i32* %1, align 4'),
            failures, 'datapath scalar changed', 'FAIL 1:')

        # --- AT: everything i64 -----------------------------------------
        wide = os.path.join(root, 'wide')
        os.makedirs(wide, exist_ok=True)
        with open(os.path.join(wide, 'wide.ll'), 'w') as f:
            f.write(widen_program(read(os.path.join(TEST_DIR, 'mmm.ll'))))
        out = os.path.join(wide, 'out')
        if run_pipeline(out, wide, 'wide', 'wd', '1'):
            generated['wd'] = (os.path.join(wide, 'wide.ll'), out, 'wd')
            agu_a = read(os.path.join(out, 'wd_a_agu.ll'))
            check('AT i64        counters are i64 from alloca to update',
                  '%i3_ptr = alloca i64' in agu_a and '%i3 = load i64, i64* %i3_ptr' in agu_a
                  and '%i3_next = add i64 %i3, 1' in agu_a
                  and '%cond_i3 = icmp slt i64 %i3, 32' in agu_a, failures)
            check('AT i64        an i64 subscript is used without widening',
                  'sext' not in agu_a
                  and re.search(r'@a, i64 0, i64 %i1, i64 %i3\b', agu_a) is not None, failures)
            check_linkage(out, 'wd', 'AT i64', failures)
        else:
            check('AT i64        pipeline', False, failures)

        # --- AU: the header compares through a cast ----------------------
        casted = os.path.join(root, 'casted')
        os.makedirs(casted, exist_ok=True)
        source = read(os.path.join(TEST_DIR, 'mmm.ll'))
        head = re.search(r'\n(\s+%(\d+) = load i32, i32\* %4, align 4\n\s+%(\d+) = icmp slt i32 %\2, 32\n)', source)
        if head is None:
            raise RuntimeError('mmm.ll no longer has the header shape AU expects')
        loaded, cond = head.group(2), head.group(3)
        replacement = (f'  %{loaded} = load i32, i32* %4, align 4\n  %900 = sext i32 %{loaded} to i64\n'
                       f'  %{cond} = icmp slt i64 %900, 32\n')
        with open(os.path.join(casted, 'casted.ll'), 'w') as f:
            f.write(renumber(source.replace(head.group(1), replacement, 1)))
        out = os.path.join(casted, 'out')
        if run_pipeline(out, casted, 'casted', 'cc', '1'):
            generated['cc'] = (os.path.join(casted, 'casted.ll'), out, 'cc')
            agu_a = read(os.path.join(out, 'cc_a_agu.ll'))
            check('AU cast cmp   the counter is widened for its compare',
                  '%cmp_i3 = sext i32 %i3 to i64' in agu_a
                  and '%cond_i3 = icmp slt i64 %cmp_i3, 32' in agu_a, failures)
            check_linkage(out, 'cc', 'AU cast cmp', failures)
        else:
            check('AU cast cmp   pipeline', False, failures)

        # --- AV: refused with a message ----------------------------------
        for label, needle, replacement_text in (
                ('phi', '  ret i32 %56\n', '  %x = phi i32 [ 7, %5 ]\n  ret i32 %x\n'),
                ('atomic', '  store i32 0, i32* %1, align 4\n', '  store atomic i32 0, i32* %1 monotonic, align 4\n'),
                ('unreachable', '  ret i32 %56\n', '  unreachable\n')):
            bad = os.path.join(root, 'bad_' + label.replace(' ', '_'))
            os.makedirs(bad, exist_ok=True)
            with open(os.path.join(bad, 'bad.ll'), 'w') as f:
                f.write(source.replace(needle, replacement_text, 1))
            ok, text = run_stages(os.path.join(bad, 'out'), bad, 'bad', 'bd', '1')
            reason = {'phi': 'phi nodes are not supported', 'atomic': 'atomic memory operations',
                      'unreachable': 'ends in unreachable'}[label]
            check(f'AV refusals   {label} is refused by name',
                  not ok and 'NotImplementedError' in text and reason in text, failures)

        # --- AW: the verifier refuses an access outside the extent --------
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_a_agu.ll'), 'i64 %sext_1_a_22_0\n', 'i64 32\n'),
            failures, 'access outside the extent', 'outside the declared')

        # --- AX: a named scalar slot ------------------------------------
        named = os.path.join(root, 'named')
        os.makedirs(named, exist_ok=True)
        subprocess.run([sys.executable, os.path.join(UNROLL_DIR, 'gen_mmm.py'), '--size', '24',
                        '--names', '--loop-scalar', '--out', os.path.join(named, 'named.ll')],
                       capture_output=True, text=True, check=True)
        out = os.path.join(named, 'out')
        if run_pipeline(out, named, 'named', 'nm', '1'):
            generated['nm'] = (os.path.join(named, 'named.ll'), out, 'nm')
            check('AX named      the named slot gets an AGU program',
                  os.path.exists(os.path.join(out, 'nm_ssum_agu.ll')), failures)
        else:
            check('AX named      pipeline', False, failures)

        # --- AY: generator combinations -----------------------------------
        for options, reason in ((['--ptr', '--expr'], 'takes only the plain nest'),
                                (['--vstep', '--factor', '3'], 'can be at most 2'),
                                (['--param', '--le'], 'does not combine'),
                                (['--minus'], 'at least 2'),
                                (['--size', '16', '--param'], 'at least 20')):
            result = subprocess.run([sys.executable, os.path.join(UNROLL_DIR, 'gen_mmm.py')]
                                    + options + ['--out', os.path.join(root, 'refused.ll')],
                                    capture_output=True, text=True)
            check(f'AY generator  {" ".join(options)} is refused',
                  result.returncode != 0 and 'Traceback' not in result.stderr
                  and reason in result.stderr, failures)
        for options, name, prefix in ((['--ptr', '--factor', '3'], 'ptr3', 'p3'),
                                      (['--loop-scalar', '--sentinel'], 'lssn', 'ls'),
                                      (['--float', '--sentinel', '--if'], 'flsn', 'fs')):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            result = subprocess.run([sys.executable, os.path.join(UNROLL_DIR, 'gen_mmm.py'), '--size', '24']
                                    + options + ['--out', os.path.join(work, f'{name}.ll')],
                                    capture_output=True, text=True)
            check(f'AY generator  {" ".join(options)} is accepted', result.returncode == 0, failures)
            if result.returncode:
                continue
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'AY generator  {" ".join(options)} is valid IR', ok, failures)
            out = os.path.join(work, 'out')
            if run_pipeline(out, work, name, prefix, '1'):
                generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
                if prefix == 'p3':
                    agu_a = read(os.path.join(out, 'p3_ptr_a_agu.ll'))
                    check('AY generator  --ptr --factor 3 reads three distinct elements',
                          len(re.findall(r'%gep_ptr_a_\S+ = getelementptr', agu_a)) >= 3
                          and re.search(r'= add i32 %i3, 2', agu_a) is not None, failures)
            else:
                check(f'AY generator  {name}: pipeline', False, failures)

        # --- AZ: scale -----------------------------------------------------
        for name, prefix, text in (('chain', 'ch', chain_program(1500)), ('blocks', 'bl', blocks_program(1500))):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(text)
            out = os.path.join(work, 'out')
            if run_pipeline(out, work, name, prefix, '1'):
                generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
                check(f'AZ scale      {name} of 1500 compiles', True, failures)
            else:
                check(f'AZ scale      {name} of 1500 compiles', False, failures)

        # --- BA / BB: casts and source order --------------------------------
        for label, name, prefix, text, probes in (
                ('BA casts     ', 'zidx', 'zi', ZEXT_INDEX_SOURCE,
                 [('the unsigned index is zext', 'zi_a_agu.ll', r'= zext i8 %load_idx_\S+ to i64')]),
                ('BA casts     ', 'zbit', 'zb', ZEXT_BIT_SOURCE,
                 [('the i1 is zext', 'zb_c_agu.ll', r'= zext i1 %\w+ to i32')]),
                ('BA casts     ', 'sextstore', 'ws', SEXT_STORE_SOURCE,
                 [('the i64 store takes the datapath\'s sext', 'ws_c_agu.ll', r'store i64 %\d+, i64\* %gep_c_'),
                  ('which the datapath computes', 'ws_datapath.ll', r'= sext i32 %i1 to i64')]),
                ('BB order     ', 'derived', 'dv', DERIVED_LATCH_SOURCE,
                 [('the store follows the update', 'dv_c_agu.ll',
                   r'%i2_next = add i32 %i2, 1\n(?:.*\n)*?\s+store i32 %\d+, i32\* %gep_c_')]),
                ('BB order     ', 'initk', 'ik', INIT_USE_SOURCE,
                 [('the counter read after its init store is the literal', 'ik_c_agu.ll',
                   r'@c, i64 0, i64 0, i64 %sext_')]),
                ('BB order     ', 'dupoff', 'df', DUP_OFFSET_SOURCE,
                 [('the offset register is defined once', 'df_a_agu.ll', None)])):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
                if not ok:
                    print(f'        {error}')
            out = os.path.join(work, 'out')
            if not run_pipeline(out, work, name, prefix, '1'):
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                content = read(os.path.join(out, file_name))
                if pattern is None:
                    defined, duplicated, _ = definitions_and_uses(os.path.join(out, file_name))
                    check(f'{label} {what}', not duplicated, failures)
                else:
                    check(f'{label} {what}', re.search(pattern, content) is not None, failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)

        # --- BE / BF: constant addresses, pointer arithmetic ------------------
        for label, name, prefix, text, probes in (
                ('BE constants ', 'cgload', 'cg', CONST_LOAD_SOURCE,
                 [('the folded subscripts are the stream\'s literals', 'cg_a_agu.ll',
                   r'@a, i64 0, i64 0, i64 3')]),
                ('BE constants ', 'cgbase', 'cb', CONST_BASE_SOURCE,
                 [('the folded row is a literal subscript', 'cb_a_agu.ll',
                   r'@a, i64 0, i64 2, i64 %sext_')]),
                ('BE constants ', 'constk', 'ck', CONST_GLOBAL_SOURCE,
                 [('the constant is a memory object', 'ck_k_agu.ll', r'@k = external global i32')]),
                ('BF pointers  ', 'ptrarith', 'pa', PTR_ARITH_SOURCE,
                 [('the offsets add up', 'pa_ptr_p_agu.ll', r'= add i64 2, %cast\d+_ptr_p_')]),
                ('BF pointers  ', 'fnptr', 'fp', FNPTR_SOURCE,
                 [('the parameter after the function pointer is read', 'fp_datapath.ll',
                   r'%n = load i32, i32\* @arg_n')])):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
                if not ok:
                    print(f'        {error}')
            out = os.path.join(work, 'out')
            if not run_pipeline(out, work, name, prefix, '1'):
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                check(f'{label} {what}', re.search(pattern, read(os.path.join(out, file_name))) is not None,
                      failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)

        # --- BG: more mutations ------------------------------------------------
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), '; block 22\n', '; block 999\n%stray = add i32 %i3, 1\n; block 22\n'),
            failures, 'datapath group for an unknown block', 'no AGU program has')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), '%load_a_22_0 = load i32,', '%load_a_22_0 = load i64,'),
            failures, 'datapath load of the wrong type', 'is received as i64')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_c_agu.ll'), 'store i32 0, i32* %gep_c_12_0', 'store i32 0.000000e+00, i32* %gep_c_12_0'),
            failures, 'literal spelled for the wrong type', 'not an integer literal')

        # --- BH: the branch-to-leaf enumeration is opt-in --------------------
        by_default = glob.glob(os.path.join(runs['1'], 'mmm_merged_bblock_*_bpath_branch_leaf.txt'))
        check('BH paths      no branch-to-leaf files by default', not by_default, failures)
        with_flag = os.path.join(root, 'branch_leaf')
        os.makedirs(with_flag, exist_ok=True)
        result = subprocess.run([sys.executable, os.path.join(HERE, 'gen_path.py'), '--src_path', runs['1'],
                                 '--src_name', 'mmm_merged', '--w_path', with_flag, '--branch_leaf'],
                                capture_output=True, text=True, cwd=HERE, timeout=STAGE_TIMEOUT)
        written = glob.glob(os.path.join(with_flag, 'mmm_merged_bblock_*_bpath_branch_leaf.txt'))
        check('BH paths      --branch_leaf writes one per block with a branch',
              result.returncode == 0 and len(written) >= 1
              and any(read(path).strip() for path in written), failures)

        # --- BI: more ways the oracle must not be fooled ----------------------
        two_source, two_out, _ = generated['two']
        verifier_fails(two_source, two_out, 'two', lambda d: edit(
            os.path.join(d, 'two_datapath.ll'), '= mul i32 %load_d_', '= mul i32 %load_a_'),
            failures, 'load from the wrong array', 'FAIL f')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_a_agu.ll'), '@a, i64 0, i64 %sext_0_a_22_0', '@a, i64 1, i64 %sext_0_a_22_0'),
            failures, 'leading subscript steps past the array', 'steps past')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), '%56 = load i32, i32* %1, align 4\n', ''),
            failures, 'return value not computed', "nobody defines: {'datapath': 'ret i32 %56'")
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: (
            edit(os.path.join(d, 'mmm_datapath.ll'), '%1 = alloca i32, align 4\n', ''),
            edit(os.path.join(d, 'mmm_datapath.ll'), 'store i32 0, i32* %1, align 4\n', ''),
            edit(os.path.join(d, 'mmm_datapath.ll'), '%56 = load i32, i32* %1, align 4\n', ''),
            edit(os.path.join(d, 'mmm_datapath.ll'), 'ret i32 %56', 'ret i32 0')),
            failures, 'datapath scalar dropped', '(dropped)')

        # --- BJ: edges of the counter model ------------------------------------
        for label, name, prefix, text, probes in (
                ('BJ edges     ', 'narrow', 'nw', NARROW_COUNTER_SOURCE,
                 [('the counter is widened before the offset is added', 'nw_a_agu.ll',
                   r'= sext i8 %i1 to i32\n\s+%idx\d+_a_\S+ = add i32 %cast\d+_a_\S+, 100')]),
                ('BJ edges     ', 'initre', 'ir2', INIT_REASSIGN_SOURCE,
                 [('the re-assigned init value is the datapath\'s', 'ir2_datapath.ll', r'%\d+ = sub i32 3, 2')]),
                ('BJ edges     ', 'deadinc', 'di', DEAD_BLOCK_SOURCE,
                 [('the entry block comes first', 'di_a_agu.ll', r'@a_agu\(\) #0 \{\nentry:')])):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
                if not ok:
                    print(f'        {error}')
            out = os.path.join(work, 'out')
            if not run_pipeline(out, work, name, prefix, '1'):
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                check(f'{label} {what}', re.search(pattern, read(os.path.join(out, file_name))) is not None,
                      failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)
        early = os.path.join(root, 'early')
        os.makedirs(early, exist_ok=True)
        with open(os.path.join(early, 'early.ll'), 'w') as f:
            f.write(renumber(READ_BEFORE_LOOP_SOURCE))
        # A read between the initialisation and the header is the
        # initial value (it used to be refused as a read before the loop).
        ok, output = run_stages(os.path.join(early, 'out'), early, 'early', 'ea', '1')
        check('BJ edges      a counter read between its initialisation and its loop compiles', ok, failures)
        if ok:
            generated['ea'] = (os.path.join(early, 'early.ll'), os.path.join(early, 'out'), 'ea')
            check('BJ edges      the read is the initial value',
                  re.search(r'store i32 0, i32\* %gep_b_', read(os.path.join(early, 'out', 'ea_b_agu.ll'))) is not None,
                  failures)

        # --- BK: model details ----------------------------------------------
        for label, name, prefix, text, probes in (
                ('BK model     ', 'swbit', 'sb', SWITCH_I1_SOURCE, []),
                ('BK model     ', 'initarr', 'ia', INIT_ARRAY_SOURCE,
                 [('the initialised array is an object', 'ia_k_agu.ll', r'@k = external global \[4 x i32\]')]),
                ('BK model     ', 'hdrstep', 'hs', HEADER_STEP_SOURCE, [])):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
                if not ok:
                    print(f'        {error}')
            out = os.path.join(work, 'out')
            ok, output = run_stages(out, work, name, prefix, '1')
            if not ok:
                print(output)
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                check(f'{label} {what}', re.search(pattern, read(os.path.join(out, file_name))) is not None,
                      failures)
            if name == 'hdrstep':
                check(f'{label} the header-advanced counter is reported',
                      'advances %j in its header' in output, failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)
        # the initialised array's values reach the result: the verifier
        # must fail when the AGU reads a different element of it
        lc_source, lc_out, _ = generated['lc']
        verifier_fails(lc_source, lc_out, 'lc', lambda d: edit(
            os.path.join(d, 'lc_l5_agu.ll'), '= sext i32 %i3 to i64', '= add i64 200, 0'),
            failures, 'local array accessed outside its extent', 'outside the declared')

        # --- BL: types from the IR, initial values, global counters --------
        for label, name, prefix, text, probes in (
                ('BL types     ', 'long', 'lg', LONG_LITERAL_SOURCE,
                 [('the add is i64', 'lg_datapath.ll', r'= add i64 0, 3')]),
                ('BL types     ', 'param64', 'p6', I64_PARAM_SOURCE,
                 [('the parameter multiplies at i64', 'p6_datapath.ll', r'= mul i64 %load_s\w+, 2')]),
                ('BL types     ', 'initload', 'il', INIT_LOAD_SOURCE,
                 [('the initial value is the AGU\'s load', 'il_datapath.ll', r'= srem i32 %load_idx_entry_0, 4')]),
                ('BL types     ', 'gcounter', 'gn', GLOBAL_COUNTER_SOURCE,
                 [('the global is a memory object, not a counter', 'gn_n_agu.ll', r'@n = external global i32')]),
                ('BL types     ', 'annot', 'an', ANNOTATED_SOURCE, [])):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
                if not ok:
                    print(f'        {error}')
            out = os.path.join(work, 'out')
            if not run_pipeline(out, work, name, prefix, '1'):
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                check(f'{label} {what}', re.search(pattern, read(os.path.join(out, file_name))) is not None,
                      failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)
            if prefix == 'gn':
                check('BL types      the global counter is not carried as %i',
                      '; counter @n' not in read(os.path.join(out, 'gn_datapath.ll')), failures)
        # --skip-merge goes through the orchestrator, which normalises the copy
        skip = os.path.join(root, 'skipmerge')
        os.makedirs(skip, exist_ok=True)
        with open(os.path.join(skip, 'cgload.ll'), 'w') as f:
            f.write(renumber(CONST_LOAD_SOURCE))
        result = subprocess.run([sys.executable, os.path.join(HERE, 'pipeline.py'), '--src', 'cgload.ll',
                                 '--output', 'sm', '--src-path', skip, '--output-path', os.path.join(skip, 'out'),
                                 '--skip-merge'], capture_output=True, text=True, cwd=HERE, timeout=STAGE_TIMEOUT)
        check('BL types      --skip-merge compiles a constant-expression address', result.returncode == 0, failures)
        if result.returncode == 0:
            generated['sm'] = (os.path.join(skip, 'cgload.ll'), os.path.join(skip, 'out'), 'sm')

        # --- BM: refusals -----------------------------------------------------
        for label, text, needle in (
                ('a loop starting from another loop\'s counter', SEQ_NO_INIT_SOURCE, 'not initialised before the loop'),
                ('two slots sharing an object name', NAME_COLLISION_SOURCE, 'would stand for'),
                ('a call passing an address', POINTER_ARG_SOURCE, 'address or a constant expression')):
            bad = os.path.join(root, 'bm_' + label.split()[1])
            os.makedirs(bad, exist_ok=True)
            with open(os.path.join(bad, 'bad.ll'), 'w') as f:
                f.write(renumber(text))
            ok, output = run_stages(os.path.join(bad, 'out'), bad, 'bad', 'bd', '1')
            check(f'BM refusals   {label} is refused', not ok and needle in output, failures)

        # --- BN: details ----------------------------------------------------
        for label, name, prefix, text, probes in (
                ('BN details   ', 'derefloop', 'dl', DEREF_LOOP_SOURCE, []),
                ('BN details   ', 'notail', 'nt', NOTAIL_SOURCE,
                 [('the datapath calls the intrinsic', 'nt_datapath.ll', r'= call i32 @llvm\.smax\.i32')]),
                ('BN details   ', 'strconst', 'sc', STRING_CONST_SOURCE, [])):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
                if not ok:
                    print(f'        {error}')
            out = os.path.join(work, 'out')
            if not run_pipeline(out, work, name, prefix, '1'):
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                check(f'{label} {what}', re.search(pattern, read(os.path.join(out, file_name))) is not None,
                      failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), 'ret i32 %56', 'ret i32 %i1'),
            failures, 'datapath returns the wrong value', 'FAIL ret %56')
        result = subprocess.run([sys.executable, os.path.join(UNROLL_DIR, 'gen_mmm.py'), '--size', '24',
                                 '--sentinel', '--factor', '4', '--out', os.path.join(root, 'refused.ll')],
                                capture_output=True, text=True)
        check('BN details    --sentinel --factor 4 is refused',
              result.returncode != 0 and 'first zero' in result.stderr, failures)
        hs_source, hs_out, _ = generated['hs']
        noted = os.path.join(root, 'noted')
        result = subprocess.run([sys.executable, os.path.join(HERE, 'pipeline.py'), '--src', os.path.basename(hs_source),
                                 '--output', 'hs', '--src-path', os.path.dirname(hs_source), '--output-path', noted],
                                capture_output=True, text=True, cwd=HERE, timeout=STAGE_TIMEOUT)
        check('BN details    the pipeline echoes a stage\'s note',
              result.returncode == 0 and 'Note: loop do.body advances %j' in result.stdout, failures)
        stale = os.path.join(root, 'stale')
        os.makedirs(stale, exist_ok=True)
        with open(os.path.join(stale, 'cgload.ll'), 'w') as f:
            f.write(renumber(CONST_LOAD_SOURCE))
        os.makedirs(os.path.join(stale, 'out'), exist_ok=True)
        with open(os.path.join(stale, 'out', 'cgload_merged.ll'), 'w') as f:
            f.write('; a merged file from an earlier run\n')
        result = subprocess.run([sys.executable, os.path.join(HERE, 'pipeline.py'), '--src', 'cgload.ll',
                                 '--output', 'st', '--src-path', stale, '--output-path', os.path.join(stale, 'out'),
                                 '--skip-merge'], capture_output=True, text=True, cwd=HERE, timeout=STAGE_TIMEOUT)
        check('BN details    --skip-merge leaves an earlier merged file alone',
              result.returncode == 0 and os.path.exists(os.path.join(stale, 'out', 'cgload_merged.ll')), failures)
        undeclared = os.path.join(root, 'undeclared')
        os.makedirs(undeclared, exist_ok=True)
        with open(os.path.join(undeclared, 'bad.ll'), 'w') as f:
            f.write(renumber(GLOBAL_COUNTER_SOURCE.replace('@n = dso_local global i32 0, align 4\n', '')))
        ok, output = run_stages(os.path.join(undeclared, 'out'), undeclared, 'bad', 'bd', '1')
        check('BN details    an undeclared global scalar is refused',
              not ok and 'used but not declared' in output, failures)

        # --- BO: the function's result -----------------------------------------
        for label, name, prefix, text, probes in (
                ('BO results   ', 'retmul', 'rm', RET_MUL_SOURCE,
                 [('the datapath returns the product', 'rm_datapath.ll', r'\nret i32 %\w+\n')]),
                ('BO results   ', 'rettrunc', 'rt', RET_TRUNC_SOURCE,
                 [('the datapath returns the truncation', 'rt_datapath.ll', r'= trunc i64 %\w+ to i32\nret i32 ')]),
                ('BO results   ', 'retelem', 're', RET_ELEMENT_SOURCE,
                 [('the datapath returns the element', 're_datapath.ll', r'\nret i32 %load_c_\S+\n')]),
                ('BO results   ', 'dotname', 'dn', DOT_NAME_SOURCE, [])):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
                if not ok:
                    print(f'        {error}')
            out = os.path.join(work, 'out')
            if not run_pipeline(out, work, name, prefix, '1'):
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                check(f'{label} {what}', re.search(pattern, read(os.path.join(out, file_name))) is not None,
                      failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)
        rm_source, rm_out, _ = generated['rm']
        verifier_fails(rm_source, rm_out, 'rm', lambda d: edit(
            os.path.join(d, 'rm_datapath.ll'), '\nret i32 %', '\nret i32 7 ; %'),
            failures, 'datapath returns another value', 'FAIL ret')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), '; counter %4 = %i3\n', '; counter %4 = %i3\n; counter %1 = %i9\n'),
            failures, 'counter claim no address program keeps', 'no address program keeps')
        gn_source, gn_out, _ = generated['gn']

        def datapath_writes_n(d):
            path = os.path.join(d, 'gn_datapath.ll')
            text = read(path)
            first = re.search(r'^; block \S+\n', text, re.M)
            if first is None:
                raise RuntimeError('gn_datapath.ll has no block group')
            text = ('@n = external global i32, align 4\n' + text[:first.end()]
                    + 'store i32 5, i32* @n, align 4\n' + text[first.end():])
            with open(path, 'w') as f:
                f.write(text)
        verifier_fails(gn_source, gn_out, 'gn', datapath_writes_n,
                       failures, 'datapath declares and writes a streamed scalar', 'which an address program streams')
        dn_source, dn_out, _ = generated['dn']
        verifier_fails(dn_source, dn_out, 'dn', lambda d: edit(
            os.path.join(d, 'dn_.str_agu.ll'), 'i64 %sext_0_.str_', 'i64 200 ; %sext_0_.str_'),
            failures, 'dotted array accessed outside its extent', 'outside the declared')

        # --- BP: refusals ------------------------------------------------------
        for label, text, needle in (
                ('an address compared as a value', PTR_COMPARE_SOURCE, 'compared as a value'),
                ('ptrtoint', PTRTOINT_SOURCE, 'turns an address into a value'),
                ('a global named like a parameter input', ARG_GLOBAL_SOURCE, "parameter %n's input")):
            bad = os.path.join(root, 'bp_' + re.sub(r'[^a-z0-9]+', '_', label.lower())[:24])
            os.makedirs(bad, exist_ok=True)
            with open(os.path.join(bad, 'bad.ll'), 'w') as f:
                f.write(renumber(text))
            ok, output = run_stages(os.path.join(bad, 'out'), bad, 'bad', 'bd', '1')
            check(f'BP refusals   {label} is refused', not ok and needle in output, failures)

        # --- BQ: round five ------------------------------------------------------
        import importlib.util
        spec = importlib.util.spec_from_file_location('vs', os.path.join(HERE, 'verify_semantics.py'))
        vs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vs)
        three = vs.array_initializers(
            '@k = dso_local constant [2 x [2 x [2 x i32]]] [[2 x [2 x i32]] zeroinitializer, '
            '[2 x [2 x i32]] [[2 x i32] zeroinitializer, [2 x i32] [i32 1, i32 2]]], align 16\n')
        check('BQ round five a zero row inside a non-zero row stays a row',
              three.get('k', {}).get((1, 1, 1)) == 2 and three['k'].get((1, 0, 1)) == 0
              and three['k'].get((0, 1, 1)) == 0, failures)
        spec = importlib.util.spec_from_file_location('aia', os.path.join(HERE, 'funcs', 'analyzer_ir_access.py'))
        sys.path.insert(0, HERE)
        aia = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(aia)
        check('BQ round five the call result type is read past attributes and conventions',
              aia._return_type('coldcc i32 ') == 'i32' and aia._return_type('noundef signext i8 ') == 'i8'
              and aia._return_type('i32 (i8*, ...) ') == 'i32' and aia._return_type('noundef i64 ') == 'i64',
              failures)
        try:
            aia._return_type('dereferenceable(4) i32* ')
            refused = False
        except NotImplementedError:
            refused = True
        check('BQ round five a call returning an address is refused', refused, failures)
        recorded = os.path.join(root, 'dbgrecord')
        os.makedirs(recorded, exist_ok=True)
        with open(os.path.join(recorded, 'rec.ll'), 'w') as f:
            f.write(renumber(RET_MUL_SOURCE.replace('  store i32 0, i32* %1, align 4\n',
                                                     '  store i32 0, i32* %1, align 4\n    #dbg_declare(i32* %1, !10, !DIExpression(), !12)\n', 1)))
        ok, output = run_stages(os.path.join(recorded, 'out'), recorded, 'rec', 'rc', '1')
        check('BQ round five an LLVM 19 debug record is dropped', ok, failures)
        if ok:
            generated['rc'] = (os.path.join(recorded, 'rec.ll'), os.path.join(recorded, 'out'), 'rc')
        twice = os.path.join(root, 'twice_out')
        os.makedirs(twice, exist_ok=True)
        produced = []
        for source in (os.path.join(UNROLL_DIR, 'mmm24_two.ll'), os.path.join(UNROLL_DIR, 'mmm24_copy.ll')):
            result = subprocess.run([sys.executable, os.path.join(HERE, 'pipeline.py'), '--src', os.path.basename(source),
                                     '--output', 'again', '--src-path', os.path.dirname(source), '--output-path', twice],
                                    capture_output=True, text=True, cwd=HERE, timeout=STAGE_TIMEOUT)
            produced.append(sorted(os.path.basename(p) for p in glob.glob(os.path.join(twice, 'again_*_agu.ll'))))
        # The first run must have left programs the second has to remove,
        # or an empty directory would satisfy the check.
        check('BQ round five an earlier run\'s address programs are removed',
              result.returncode == 0 and len(produced[0]) > 2 and 'again_d_agu.ll' in produced[0]
              and produced[1] == ['again_a_agu.ll', 'again_c_agu.ll'], failures)
        for options in (['--sentinel', '--factor', '3', '--start', '6'], ['--sentinel', '--factor', '7', '--size', '49']):
            result = subprocess.run([sys.executable, os.path.join(UNROLL_DIR, 'gen_mmm.py')] + (['--size', '24'] if '--size' not in options else [])
                                    + options + ['--out', os.path.join(root, 'refused.ll')],
                                    capture_output=True, text=True)
            check(f'BQ round five {" ".join(options)} is refused',
                  result.returncode != 0 and 'first zero' in result.stderr, failures)

        # --- BR: round six ---------------------------------------------------
        for label, text, needle in (
                ('a call returning an address', PTR_CALL_SOURCE, 'a call returning an address'),
                ('a function returning an address', RET_PTR_SOURCE, 'an address cannot be returned')):
            bad = os.path.join(root, 'br_' + re.sub(r'[^a-z0-9]+', '_', label.lower())[:24])
            os.makedirs(bad, exist_ok=True)
            with open(os.path.join(bad, 'bad.ll'), 'w') as f:
                f.write(renumber(text))
            ok, output = run_stages(os.path.join(bad, 'out'), bad, 'bad', 'bd', '1')
            check(f'BR round six  {label} is refused', not ok and needle in output, failures)

        def move_ret(d):
            path = os.path.join(d, 'mmm_datapath.ll')
            text = read(path)
            if '%56 = load i32, i32* %1, align 4\nret i32 %56\n' not in text:
                raise RuntimeError('mmm_datapath.ll no longer ends with the expected ret')
            text = text.replace('%56 = load i32, i32* %1, align 4\nret i32 %56\n', '')
            # At the end of the loop body's group (a ret that is not the
            # group's last line is refused as following its ret).
            text = text.replace('store i32 %45, i32* %gep_c_22_0, align 4\n',
                                'store i32 %45, i32* %gep_c_22_0, align 4\n%56 = load i32, i32* %1, align 4\nret i32 %56\n', 1)
            with open(path, 'w') as f:
                f.write(text)
        verifier_fails(mmm_source, runs['1'], 'mmm', move_ret,
                       failures, 'datapath returns from another block', 'returns more than once')
        def ret_from_entry(d):
            path = os.path.join(d, 'mmm_datapath.ll')
            text = read(path).replace('%56 = load i32, i32* %1, align 4\nret i32 %56\n', '')
            text = text.replace('store i32 0, i32* %1, align 4\n',
                                'store i32 0, i32* %1, align 4\n%56 = load i32, i32* %1, align 4\nret i32 %56\n', 1)
            with open(path, 'w') as f:
                f.write(text)
        verifier_fails(mmm_source, runs['1'], 'mmm', ret_from_entry,
                       failures, 'datapath returns from the entry block', 'returned from block entry')
        dr_source, dr_out, _ = generated['dr']

        def void_returns(d):
            edit(os.path.join(d, 'dr_datapath.ll'), 'ret void', 'ret i32 0')
        verifier_fails(dr_source, dr_out, 'dr', void_returns,
                       failures, 'datapath returns where the source is void', 'FAIL ret')
        se_source, se_out, se_prefix = generated['scalar_ends']
        verifier_fails(se_source, se_out, se_prefix, lambda d: edit(
            os.path.join(d, f'{se_prefix}_datapath.ll'), '; block entry\n',
            '; block entry\n%5 = alloca i32, align 4\nstore i32 9, i32* %5, align 4\n'),
            failures, 'datapath declares a streamed scalar', 'one owner')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), '; counter %4 = %i3\n', '; counter %4 = %i3\n; counter %99 = %i3\n'),
            failures, 'counter claim for a slot the source has not', 'no such slot')

        manifest = os.path.join(root, 'manifest')
        os.makedirs(manifest, exist_ok=True)
        def pipeline(src, out_name, *extra):
            return subprocess.run([sys.executable, os.path.join(HERE, 'pipeline.py'), '--src', os.path.basename(src),
                                   '--output', out_name, '--src-path', os.path.dirname(src),
                                   '--output-path', manifest] + list(extra),
                                  capture_output=True, text=True, cwd=HERE, timeout=STAGE_TIMEOUT)
        pipeline(os.path.join(UNROLL_DIR, 'mmm24_two.ll'), 'mf', '--gen', 'agu')
        pipeline(os.path.join(UNROLL_DIR, 'mmm24_copy.ll'), 'mf', '--gen', 'datapath')
        present = sorted(os.path.basename(p) for p in glob.glob(os.path.join(manifest, 'mf_*.ll')))
        check('BR round six  --gen datapath keeps an earlier --gen agu\'s programs',
              'mf_d_agu.ll' in present and 'mf_datapath.ll' in present, failures)
        pipeline(os.path.join(UNROLL_DIR, 'mmm24_copy.ll'), 'mf')
        present = sorted(os.path.basename(p) for p in glob.glob(os.path.join(manifest, 'mf_*.ll')))
        check('BR round six  a full run removes the programs it does not regenerate',
              present == ['mf_a_agu.ll', 'mf_c_agu.ll', 'mf_datapath.ll'], failures)
        with open(os.path.join(manifest, 'broken.ll'), 'w') as f:
            f.write(read(os.path.join(UNROLL_DIR, 'mmm24_copy.ll')).replace('@c = dso_local global', '@c_unused = dso_local global', 1))
        result = pipeline(os.path.join(manifest, 'broken.ll'), 'mf')
        present = sorted(os.path.basename(p) for p in glob.glob(os.path.join(manifest, 'mf_*.ll')))
        check('BR round six  a failing run keeps the previous outputs',
              result.returncode != 0 and present == ['mf_a_agu.ll', 'mf_c_agu.ll', 'mf_datapath.ll'], failures)
        with open(os.path.join(manifest, 'mmm24_do.ll'), 'w') as f:
            f.write('; a file of the user\'s\n')
        result = pipeline(os.path.join(UNROLL_DIR, 'mmm24_do.ll'), 'sk', '--skip-merge')
        check('BR round six  --skip-merge refuses to overwrite a file in the output directory',
              result.returncode != 0 and 'already exists' in result.stdout + result.stderr
              and read(os.path.join(manifest, 'mmm24_do.ll')).startswith('; a file'), failures)

        # --- BS: fneg, no empty groups ----------------------------------------
        work = os.path.join(root, 'fneg')
        os.makedirs(work, exist_ok=True)
        with open(os.path.join(work, 'fneg.ll'), 'w') as f:
            f.write(renumber(FNEG_SOURCE))
        if tool is not None:
            ok, error = assembles(tool, os.path.join(work, 'fneg.ll'))
            check('BS fneg       fneg is valid IR', ok, failures)
        out = os.path.join(work, 'out')
        if run_pipeline(out, work, 'fneg', 'fn', '1'):
            generated['fn'] = (os.path.join(work, 'fneg.ll'), out, 'fn')
            check('BS fneg       the datapath negates', '= fneg double %load_a_' in read(os.path.join(out, 'fn_datapath.ll')),
                  failures)
            check_linkage(out, 'fn', 'BS fneg', failures)
        else:
            check('BS fneg       pipeline', False, failures)
        groups = re.findall(r'^; block (\S+)\n(?=\n|; block|\Z)', read(os.path.join(runs['1'], 'mmm_datapath.ll')), re.M)
        check('BS fneg       the datapath has no empty block group', not groups, failures)

        # --- BT: round seven ---------------------------------------------------
        for label, name, prefix, text, probes in (
                ('BT round seven', 'bareglobal', 'bg', BARE_GLOBAL_SOURCE,
                 [('a[0] is element 0 of the array', 'bg_a_agu.ll', r'@a, i64 0, i64 0\n')]),
                ('BT round seven', 'brick', 'bri', re.sub(r'@b\b', '@abr', re.sub(r'@a\b', '@brick', read(os.path.join(TEST_DIR, 'mmm.ll')))),
                 [('an array named like a branch is an array', 'bri_brick_agu.ll', r'@brick = external global')]),
                ('BT round seven', 'payload', 'pl', re.sub(r'%5\b', '%payload', read(os.path.join(NOLOOP_DIR, 'scalar_ends.ll'))),
                 [])):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
                if not ok:
                    print(f'        {error}')
            out = os.path.join(work, 'out')
            if not run_pipeline(out, work, name, prefix, '1'):
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                check(f'{label} {what}', re.search(pattern, read(os.path.join(out, file_name))) is not None,
                      failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: (
            edit(os.path.join(d, 'mmm_datapath.ll'), '%load_c_22_0 = load i32, i32* %gep_c_22_0', '%zz = load i32, i32* %gep_c_22_0'),
            edit(os.path.join(d, 'mmm_datapath.ll'), '%45 = add i32 %load_c_22_0, %37', '%45 = add i32 %zz, %37')),
            failures, 'datapath reads memory under its own name', 'reads memory the address units own')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_b_agu.ll'), '  %i3 = load i32, i32* %i3_ptr, align 4\n', ''),
            failures, 'address program borrows a counter', "nobody defines: {'mmm_b_agu.ll': '%cond_i3")
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: (
            edit(os.path.join(d, 'mmm_datapath.ll'), '%1 = alloca i32, align 4\n', '%1 = alloca i32, align 4\n%4 = alloca i32, align 4\n'),
            edit(os.path.join(d, 'mmm_datapath.ll'), '; block 55\n', '; block 55\nstore i32 32, i32* %4, align 4\n')),
            failures, 'datapath declares a counter', 'one owner')
        # a code generation that fails after writing keeps the previous outputs
        partial = os.path.join(root, 'partial')
        os.makedirs(partial, exist_ok=True)
        pipeline_partial = lambda: subprocess.run(
            [sys.executable, os.path.join(HERE, 'pipeline.py'), '--src', 'mmm24_copy.ll', '--output', 'pw',
             '--src-path', UNROLL_DIR, '--output-path', partial], capture_output=True, text=True, cwd=HERE,
            timeout=STAGE_TIMEOUT)
        pipeline_partial()
        before = {name: read(os.path.join(partial, name)) for name in ('pw_a_agu.ll', 'pw_c_agu.ll', 'pw_datapath.ll')}
        os.makedirs(os.path.join(partial, 'pw_datapath.ll.tmp'))		# the rename will fail
        result = pipeline_partial()
        os.rmdir(os.path.join(partial, 'pw_datapath.ll.tmp'))
        after = {name: read(os.path.join(partial, name)) for name in before if os.path.exists(os.path.join(partial, name))}
        check('BT round seven a failing write keeps the previous outputs and no temporaries',
              result.returncode != 0 and after == before
              and not glob.glob(os.path.join(partial, '*.tmp')), failures)

        # --- BU: round seven, continued ------------------------------------------
        for label, name, prefix, text, probes in (
                ('BU round seven', 'decay', 'dc', DECAY_SOURCE,
                 [('the offset is the subscript', 'dc_a_agu.ll', r'@a, i64 0, i64 %sext_0_a_')]),):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
            out = os.path.join(work, 'out')
            if not run_pipeline(out, work, name, prefix, '1'):
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                check(f'{label} {what}', re.search(pattern, read(os.path.join(out, file_name))) is not None,
                      failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)
        for label, text, needle in (
                ('a flattened matrix', FLAT_MATRIX_SOURCE, 'in units of'),
                ('an empty one-block loop', SELF_LOOP_SOURCE, 'do nothing'),
                ('an empty two-block loop', TWO_BLOCK_EMPTY_LOOP_SOURCE, 'do nothing')):
            bad = os.path.join(root, 'bu_' + re.sub(r'[^a-z0-9]+', '_', label.lower())[:24])
            os.makedirs(bad, exist_ok=True)
            with open(os.path.join(bad, 'bad.ll'), 'w') as f:
                f.write(renumber(text))
            ok, output = run_stages(os.path.join(bad, 'out'), bad, 'bad', 'bd', '1')
            check(f'BU round seven {label} is refused', not ok and needle in output, failures)
        for options, reason in ((['--size', '20', '--sentinel', '--minus', '--factor', '3'], 'first zero'),
                                (['--shape', '24,24,8', '--start', '10', '--do'], 'runs its body once'),
                                (['--minus', '--factor', '3', '--start', '2'], 'does not apply')):
            result = subprocess.run([sys.executable, os.path.join(UNROLL_DIR, 'gen_mmm.py')] + options
                                    + ['--out', os.path.join(root, 'refused.ll')], capture_output=True, text=True)
            check(f'BU round seven {" ".join(options)} is refused',
                  result.returncode != 0 and 'Traceback' not in result.stderr and reason in result.stderr, failures)
        os.remove(os.path.join(manifest, 'mf_datapath.ll'))
        pipeline(os.path.join(UNROLL_DIR, 'mmm24_copy.ll'), 'mf', '--gen', 'agu')
        check('BU round seven a deleted output drops out of the manifest',
              'mf_datapath.ll' not in read(os.path.join(manifest, 'mf_outputs.txt')), failures)

        # --- BV: round eight -----------------------------------------------------
        # `*(*(m + i) + j)`: clang steps a row pointer with a getelementptr
        # whose leading index is the row, not 0. Dropping the leading
        # index whatever it was wrote every row into row 0.
        for label, name, prefix, text, probes in (
                ('BV round eight', 'rowptr', 'rp', ROW_POINTER_SOURCE,
                 [('a row pointer plus i is row i', 'rp_m_agu.ll',
                   r'@m, i64 0, i64 %sext_0_m_for\.body3_0, i64 %sext_1_m_for\.body3_0'),
                  ('the read side too', 'rp_t_agu.ll',
                   r'@t, i64 0, i64 %sext_0_t_for\.body14_0, i64 %sext_1_t_for\.body14_0')]),
                ('BV round eight', 'zero', 'zs', ZERO_STORE_SOURCE, []),
                ('BV round eight', 'leafs', 'lf', re.sub(r'@n\b', '@LEAFS', read(os.path.join(UNROLL_DIR, 'mmm24_variables.ll'))),
                 [('an object named @LEAFS is not a leaf', 'lf_LEAFS_agu.ll', r'@LEAFS')]),
                ('BV round eight', 'leaf', 'le', re.sub(r'%1\b', '%LEAF', read(mmm_source)),
                 [('a register named %LEAF is not a leaf', 'le_datapath.ll', r'%LEAF')]),
                # `*p += 1` through the parameter register itself, with no
                # spill slot: the store is through a pointer holder, not a
                # scalar slot the loop could carry as its counter.
                ('BV round eight', 'direct', 'dr2', DIRECT_PARAM_SOURCE,
                 [('a store through the parameter is an element', 'dr2_ptr_p_agu.ll', r'store i32 %add, i32\* %gep_ptr_p_')])):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
            out = os.path.join(work, 'out')
            if not run_pipeline(out, work, name, prefix, '1'):
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                check(f'{label} {what}', re.search(pattern, read(os.path.join(out, file_name))) is not None,
                      failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)
        for label, text, needle in (
                ('a leading subscript past the array', LEADING_ONE_SOURCE, 'steps past'),
                ('a row pointer stepped as another type', REINTERPRET_SOURCE, 'points at a'),
                ('more subscripts than dimensions', TOO_DEEP_SOURCE, 'more subscripts than'),
                ('a parameter stored into another\'s slot', PARAM_SWAP_SOURCE, 'not its own spill slot'),
                ('a global holding an address', GLOBAL_POINTER_SOURCE, 'holds an address'),
                ('a quoted function name', QUOTED_NAME_SOURCE, "cannot read the function's name")):
            bad = os.path.join(root, 'bv_' + re.sub(r'[^a-z0-9]+', '_', label.lower())[:24])
            os.makedirs(bad, exist_ok=True)
            with open(os.path.join(bad, 'bad.ll'), 'w') as f:
                f.write(renumber(text))
            # LLVM itself refuses more subscripts than dimensions, so that
            # fixture is the one the assembler cannot be asked about.
            if tool is not None and text is not TOO_DEEP_SOURCE:
                ok, error = assembles(tool, os.path.join(bad, 'bad.ll'))
                check(f'BV round eight {label}: fixture is valid IR', ok, failures)
            ok, output = run_stages(os.path.join(bad, 'out'), bad, 'bad', 'bd', '1')
            check(f'BV round eight {label} is refused', not ok and needle in output, failures)
        # An output name with a glob metacharacter: the cleanup's protected
        # set matched nothing, and every final output went with the
        # intermediates.
        result = pipeline(mmm_source, 'mmm_merged_cfg[x]')
        kept = sorted(os.path.basename(p) for p in glob.glob(os.path.join(manifest, 'mmm_merged_cfg[[]x]_*')))
        check('BV round eight an output name with a glob metacharacter keeps its outputs',
              result.returncode == 0 and kept == ['mmm_merged_cfg[x]_a_agu.ll', 'mmm_merged_cfg[x]_b_agu.ll',
                                                  'mmm_merged_cfg[x]_c_agu.ll', 'mmm_merged_cfg[x]_datapath.ll',
                                                  'mmm_merged_cfg[x]_outputs.txt'], failures)
        # The verifier: the datapath owns no memory; the address programs'
        # final block runs; an element nobody wrote holds its fill value;
        # a counter's slot is not also an object another program streams.
        def datapath_own_store(d):
            edit(os.path.join(d, 'mmm_c_agu.ll'), '  store i32 %45, i32* %gep_c_22_0, align 4\n', '')
            edit(os.path.join(d, 'mmm_datapath.ll'), 'store i32 %45, i32* %gep_c_22_0, align 4',
                 '%own = getelementptr inbounds [32 x [32 x i32]], [32 x [32 x i32]]* @c, i64 0, '
                 'i64 %sext_0_c_22_0, i64 %sext_1_c_22_0\nstore i32 %45, i32* %own, align 4')
        verifier_fails(mmm_source, runs['1'], 'mmm', datapath_own_store,
            failures, 'datapath stores through its own address', 'the datapath addresses c')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_a_agu.ll'), 'ret:\n  ret void',
            'ret:\n  %late = getelementptr inbounds [32 x [32 x i32]], [32 x [32 x i32]]* @a, i64 0, i64 0, i64 0\n'
            '  store i32 7, i32* %late, align 4\n  ret void'),
            failures, 'store in the final block', 'not a stream address')
        zs_source, zs_out, _ = generated['zs']
        verifier_fails(zs_source, zs_out, 'zs', lambda d: (
            edit(os.path.join(d, 'zs_ptr_p_agu.ll'), '  store i32 0, i32* %gep_ptr_p_for.body_0, align 4\n', ''),
            edit(os.path.join(d, 'zs_datapath.ll'), 'store i32 0, i32* %gep_ptr_p_for.body_0, align 4\n', '')),
            failures, 'zero store dropped on both sides', 'FAIL ptr_p:')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), '; counter %2 = %i1\n', '; counter %2 = %i1\n; counter @a = %i1\n'),
            failures, 'counter claim on an object another program streams', 'another streams it as an object')
        # Code generation's rename sweep: a destination that is a directory
        # is refused before anything is written, and a rename that fails
        # halfway leaves a manifest of what is actually there.
        os.remove(os.path.join(partial, 'pw_datapath.ll'))
        os.makedirs(os.path.join(partial, 'pw_datapath.ll'))
        manifest_before = read(os.path.join(partial, 'pw_outputs.txt'))
        result = pipeline_partial()
        os.rmdir(os.path.join(partial, 'pw_datapath.ll'))
        after = {name: read(os.path.join(partial, name)) for name in ('pw_a_agu.ll', 'pw_c_agu.ll')}
        check('BV round eight a directory where a program goes is refused before writing',
              result.returncode != 0 and 'is a directory' in result.stdout + result.stderr
              and after == {name: before[name] for name in after}
              and read(os.path.join(partial, 'pw_outputs.txt')) == manifest_before
              and not glob.glob(os.path.join(partial, '*.tmp')), failures)
        import importlib
        sweep = os.path.join(root, 'sweep')
        os.makedirs(sweep, exist_ok=True)
        for name in ('x_a_agu.ll', 'x_b_agu.ll', 'x_datapath.ll'):
            with open(os.path.join(sweep, name), 'w') as f:
                f.write('old ' + name)
        for name in ('x_a_agu.ll', 'x_datapath.ll'):
            with open(os.path.join(sweep, name + '.tmp'), 'w') as f:
                f.write('new ' + name)
        with open(os.path.join(sweep, 'x_outputs.txt'), 'w') as f:
            f.write('x_a_agu.ll\nx_b_agu.ll\nx_datapath.ll\n')
        real_replace = os.replace
        def failing_replace(src, dst):
            if dst.endswith('x_datapath.ll'):
                raise OSError('rename refused')
            real_replace(src, dst)
        os.replace = failing_replace
        try:
            importlib.import_module('gen_prog').replace_outputs(
                sweep, ['x_a_agu.ll', 'x_datapath.ll'], ['x_a_agu.ll', 'x_b_agu.ll', 'x_datapath.ll'],
                os.path.join(sweep, 'x_outputs.txt'), True, True)
            raised = False
        except OSError:
            raised = True
        finally:
            os.replace = real_replace
        check('BV round eight a rename that fails halfway leaves a manifest of what is there',
              raised and read(os.path.join(sweep, 'x_outputs.txt')).split() == ['x_a_agu.ll', 'x_b_agu.ll', 'x_datapath.ll']
              and read(os.path.join(sweep, 'x_a_agu.ll')) == 'new x_a_agu.ll'
              and read(os.path.join(sweep, 'x_datapath.ll')) == 'old x_datapath.ll', failures)

        # --- BW: round nine ------------------------------------------------------
        # A counter read in a block the loop leaves from its latch after
        # the update (`k++; if (k >= n) break;` then a use of k) read the
        # header's stale %i<level>; the block reads %i<level>_next, and a
        # block entered both ways reads the slot again (%i<level>_at_<block>).
        for label, name, prefix, text, probes in (
                ('BW round nine', 'latchread', 'lr', LATCH_READ_SOURCE,
                 [('a read after a latch exit is the advanced counter', 'lr_datapath.ll', r'ret i32 %i1_next')]),
                ('BW round nine', 'latchbody', 'lb', LATCH_BODY_SOURCE,
                 [('a body block after the update reads the advanced counter', 'lb_c_agu.ll',
                   r'%sext_0_c_\w+_0 = sext i32 %i1_next(?:_\w+)? to i64')]),
                ('BW round nine', 'reload', 'rlo', COUNTER_RELOAD_SOURCE,
                 [('a block entered both ways reads the slot again', 'rlo_c_agu.ll',
                   r'%i2_at_\w+ = load i32, i32\* %i2_ptr')]),
                # With the hoisted address taking the local's name, the local
                # vanished into a[3]'s stream; it is its own scalar object.
                ('BW round nine', 'cgepname', 'cn', CGEP_NAME_SOURCE,
                 [('a hoisted address never takes a name in use', 'cn_scgep0_agu.ll', r'@scgep0')]),
                ('BW round nine', 'derefgep', 'dgp', DEREF_GEP_SOURCE,
                 [('a dereference then a step on one pointer', 'dgp_ptr_p_agu.ll', r'@ptr_p, i64 0, i64 1')]),
                # Every integer and floating-point operation the datapath
                # carries, verified end to end: none of these had a
                # semantic check before.
                ('BW round nine', 'intops', 'io', INT_OPS_SOURCE,
                 [('the datapath carries every integer operation', 'io_datapath.ll',
                   r'(?s)(?=.*sdiv i32)(?=.*srem i32)(?=.*udiv i32)(?=.*urem i32)(?=.*and i32)(?=.*or i32)(?=.*xor i32)(?=.*shl i32)(?=.*ashr i32)(?=.*lshr i32)(?=.*icmp ugt)')]),
                ('BW round nine', 'floatops', 'fo', FLOAT_OPS_SOURCE,
                 [('the datapath carries every floating-point operation', 'fo_datapath.ll',
                   r'(?s)(?=.*fpext float)(?=.*fsub double)(?=.*fdiv double)(?=.*frem double)(?=.*fptosi double)(?=.*sitofp i32)(?=.*uitofp i32)(?=.*fptoui double)(?=.*fptrunc double)')])):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
            out = os.path.join(work, 'out')
            if not run_pipeline(out, work, name, prefix, '1'):
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                check(f'{label} {what}', re.search(pattern, read(os.path.join(out, file_name))) is not None,
                      failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)
        for label, text, needle in (
                ('an ambiguous stream register name', STREAM_NAME_SOURCE, 'would share the register names'),
                ('a block labelled ret', RET_LABEL_SOURCE, 'labelled ret'),
                ('a later block labelled entry', ENTRY_LABEL_SOURCE, 'two blocks are named entry'),
                ('an element accessed as another type', ELEMENT_TYPE_SOURCE, 'accessed as its own type'),
                ('a select between addresses', SELECT_ADDR_SOURCE, 'a select between addresses'),
                ('a vector type', VECTOR_SOURCE, 'vector types are not supported'),
                ('an aggregate loaded whole', AGGREGATE_SOURCE, 'an aggregate is loaded or stored whole'),
                ('a pointer to a structure', STRUCT_PTR_SOURCE, 'points to a structure'),
                ('a counter initialised in two places', TWO_INITS_SOURCE, 'two places'),
                ('a local named like a counter', LOCAL_I1_SOURCE, 'the name the generated programs give a loop')):
            bad = os.path.join(root, 'bw_' + re.sub(r'[^a-z0-9]+', '_', label.lower())[:24])
            os.makedirs(bad, exist_ok=True)
            with open(os.path.join(bad, 'bad.ll'), 'w') as f:
                f.write(renumber(text))
            ok, output = run_stages(os.path.join(bad, 'out'), bad, 'bad', 'bd', '1')
            check(f'BW round nine {label} is refused', not ok and needle in output, failures)
        # The verifier: an address program streams its own object only,
        # through stream registers, in the stream's block, storing what
        # it received; a slot holds nothing before its first store;
        # nothing follows a terminator; a %load_ name shared must be a
        # load; every counter kept is claimed; every program has an
        # object; the datapath returns where the programs end.
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: (
            edit(os.path.join(d, 'mmm_a_agu.ll'), '  %sext_1_a_22_0 = sext i32 %i3 to i64\n',
                 '  %sext_1_a_22_0 = sext i32 %i3 to i64\n  %sext_1_a_22_9 = sext i32 %i2 to i64\n'),
            edit(os.path.join(d, 'mmm_a_agu.ll'), '  %load_a_22_0 = load i32, i32* %gep_a_22_0, align 4\n',
                 '  %load_a_22_0 = load i32, i32* %gep_a_22_0, align 4\n'
                 '  %gep_a_22_9 = getelementptr inbounds [32 x [32 x i32]], [32 x [32 x i32]]* @c, i64 0, '
                 'i64 %sext_0_a_22_0, i64 %sext_1_a_22_9\n  store i32 %45, i32* %gep_a_22_9, align 4\n'),
            edit(os.path.join(d, 'mmm_c_agu.ll'), '  store i32 %45, i32* %gep_c_22_0, align 4\n', ''),
            edit(os.path.join(d, 'mmm_datapath.ll'), 'store i32 %45, i32* %gep_c_22_0, align 4',
                 'store i32 %45, i32* %gep_a_22_9, align 4')),
            failures, 'store moved into another object\'s program', 'an object it does not stream')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: [
            edit(os.path.join(d, f'mmm_{x}_agu.ll'), '  store i32 0, i32* %i1_ptr, align 4\n', '')
            for x in 'abc'],
            failures, 'dropped initialisation of a counter', 'reads %i1_ptr before anything is stored')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), 'store i32 0, i32* %1, align 4\n', ''),
            failures, 'dropped initialisation of a datapath scalar', 'reads %1 before anything is stored')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_c_agu.ll'), '  store i32 %45, i32* %gep_c_22_0, align 4\n  br label %46\n',
            '  br label %46\n  store i32 %45, i32* %gep_c_22_0, align 4\n'),
            failures, 'store after the terminator', "follows the block's terminator")
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_a_agu.ll'), '12:\n',
            '12:\n  %sx = sext i32 %i1 to i64\n  %sy = sext i32 %i2 to i64\n'
            '  %p = getelementptr inbounds [32 x [32 x i32]], [32 x [32 x i32]]* @a, i64 0, i64 %sx, i64 %sy\n'
            '  store i32 7, i32* %p, align 4\n'),
            failures, 'store through an address that is not a stream', 'not a stream address')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_c_agu.ll'), '  store i32 %45, i32* %gep_c_22_0, align 4\n',
            '  %37x = mul i32 %load_a_22_0, %load_b_22_0\n  %45 = add i32 %load_c_22_0, %37x\n'
            '  store i32 %45, i32* %gep_c_22_0, align 4\n'),
            failures, 'address program computes the value it stores', 'a value it computed itself')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: (
            edit(os.path.join(d, 'mmm_c_agu.ll'), '  store i32 %45, i32* %gep_c_22_0, align 4\n  br label %46\n', '  br label %46\n'),
            edit(os.path.join(d, 'mmm_c_agu.ll'), '46:\n', '46:\n  store i32 %45, i32* %gep_c_22_0, align 4\n'),
            edit(os.path.join(d, 'mmm_datapath.ll'), 'store i32 %45, i32* %gep_c_22_0, align 4\n', ''),
            edit(os.path.join(d, 'mmm_datapath.ll'), '; block 55\n', '; block 46\nstore i32 %45, i32* %gep_c_22_0, align 4\n\n; block 55\n')),
            failures, 'store moved to another block on both sides', 'in block 46')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: (
            edit(os.path.join(d, 'mmm_a_agu.ll'), '  %load_a_22_0 = load i32, i32* %gep_a_22_0, align 4\n',
                 '  %load_a_22_0 = load i32, i32* %gep_a_22_0, align 4\n  %load_k_22_0 = add i32 %i3, 0\n'),
            edit(os.path.join(d, 'mmm_b_agu.ll'), '%sext_0_b_22_0 = sext i32 %i3 to i64', '%sext_0_b_22_0 = sext i32 %load_k_22_0 to i64')),
            failures, 'counter laundered through a %load_ name', "nobody defines: {'mmm_b_agu.ll': '%sext_0_b_22_0")
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), '; counter %2 = %i1\n', ''),
            failures, 'counter kept but not claimed', 'no ; counter line claims it')
        def extra_program(d):
            shutil.copy(os.path.join(d, 'mmm_a_agu.ll'), os.path.join(d, 'mmm_zz_agu.ll'))
            text = read(os.path.join(d, 'mmm_zz_agu.ll')).replace('@a_agu', '@zz_agu').replace('@a =', '@zz =')
            text = re.sub(r'  %(sext_\d|gep|load)_a_22_0 = .*\n', '', text)
            with open(os.path.join(d, 'mmm_zz_agu.ll'), 'w') as f:
                f.write(text)
        verifier_fails(mmm_source, runs['1'], 'mmm', extra_program,
            failures, 'address program for an object the source has not', 'no such object in the source')
        zs_source, zs_out, _ = generated['zs']
        verifier_fails(zs_source, zs_out, 'zs', lambda d: edit(
            os.path.join(d, 'zs_datapath.ll'), 'ret void', ''),
            failures, 'datapath of a void function never returns', 'the datapath never returns')
        verifier_fails(zs_source, zs_out, 'zs', lambda d: edit(
            os.path.join(d, 'zs_ptr_p_agu.ll'), 'label %for.body, label %for.end', 'label %for.body, label %ret'),
            failures, 'programs of a void function end elsewhere', 'the datapath never returns')
        # A second fill of the input arrays takes other data-dependent
        # branches; the `if` variant verifies under both.
        if_cases = [key for key in generated if str(key).endswith('if')]
        for key in if_cases[:1]:
            source_if, out_if, prefix_if = generated[key]
            returncode, text = run_verifier(source_if, out_if, prefix_if, seed='second')
            check('BW round nine the if variant verifies under a second fill', returncode == 0, failures)
        check('BW round nine an if variant exists to verify twice', bool(if_cases), failures)

        # --- BX: round ten -------------------------------------------------------
        # A latch's update adds to the value the block was entered with,
        # a block reached by skipping a loop reloads the counter, a dead
        # store before the initialisation is allowed, loop detection
        # starts from the function's first block whatever its label,
        # an external scalar has a value.
        for label, name, prefix, text, probes in (
                ('BX round ten', 'latchlatch', 'll', LATCH_FROM_LATCH_SOURCE,
                 [('a latch entered after another latch adds to that value', 'll_c_agu.ll',
                   r'%i1_next = add i32 %i1_at_[-\w.$]+, 1')]),
                ('BX round ten', 'bypass', 'byp', BYPASS_SOURCE,
                 [('a block reached by skipping the loop reloads the counter', 'byp_d_agu.ll',
                   r'%i2_at_\w+ = load i32, i32\* %i2_ptr')]),
                ('BX round ten', 'declinit', 'dci', DECL_INIT_SOURCE,
                 [('a dead store before the initialisation is allowed', 'dci_c_agu.ll', r'%i2_at_')]),
                ('BX round ten', 'entrylater', 'enl', ENTRY_LATER_SOURCE,
                 [('the loop is found from the first block, not the one named entry', 'enl_a_agu.ll',
                   r'%cond_i1 = icmp slt i32 %i1, 8')]),
                ('BX round ten', 'externscalar', 'exs', EXTERN_SCALAR_SOURCE,
                 [('an external scalar is streamed', 'exs_K_agu.ll', r'@K = external')]),
                # A goto out of the first loop past the second: the block
                # after both reads whichever loop's value arrives, from the
                # slot the two loops share.
                ('BX round ten', 'crossjoin', 'cj', CROSS_LOOP_JOIN_SOURCE,
                 [('loops on one variable share a slot', 'cj_d_agu.ll', r'%i3 = load i32, i32\* %i2_ptr'),
                  ('the join reads the shared slot again', 'cj_d_agu.ll', r'%i2_at_\w+ = load i32, i32\* %i2_ptr')])):
            work = os.path.join(root, name)
            os.makedirs(work, exist_ok=True)
            with open(os.path.join(work, f'{name}.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(work, f'{name}.ll'))
                check(f'{label} {name} is valid IR', ok, failures)
            out = os.path.join(work, 'out')
            if not run_pipeline(out, work, name, prefix, '1'):
                check(f'{label} {name}: pipeline', False, failures)
                continue
            generated[prefix] = (os.path.join(work, f'{name}.ll'), out, prefix)
            for what, file_name, pattern in probes:
                check(f'{label} {what}', re.search(pattern, read(os.path.join(out, file_name))) is not None,
                      failures)
            check_linkage(out, prefix, f'{label.strip()} {name}', failures)
        for label, text, needle in (
                ('a counter initialised by a latch that can be bypassed', BYPASSABLE_LATCH_INIT_SOURCE,
                 'can be left before it'),
                ('a call to a function that is not an intrinsic', EXTERNAL_CALL_SOURCE, 'only LLVM intrinsics')):
            bad = os.path.join(root, 'bx_' + re.sub(r'[^a-z0-9]+', '_', label.lower())[:24])
            os.makedirs(bad, exist_ok=True)
            with open(os.path.join(bad, 'bad.ll'), 'w') as f:
                f.write(renumber(text))
            if tool is not None:
                ok, error = assembles(tool, os.path.join(bad, 'bad.ll'))
                check(f'BX round ten {label}: fixture is valid IR', ok, failures)
            ok, output = run_stages(os.path.join(bad, 'out'), bad, 'bad', 'bd', '1')
            check(f'BX round ten {label} is refused', not ok and needle in output, failures)
        # The verifier: a stored or sent %load_/%i register must be a real
        # load or counter; a load is consumed in the block that loaded it;
        # the datapath touches no streamed scalar; a pointer's array is
        # read within the source's footprint; a wide fill; a source out of
        # range under a fill is reported as such, not as a verdict.
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: (
            edit(os.path.join(d, 'mmm_c_agu.ll'), '  store i32 %45, i32* %gep_c_22_0, align 4\n',
                 '  %load_c_22_7 = add i32 %load_c_22_0, %37\n  store i32 %load_c_22_7, i32* %gep_c_22_0, align 4\n'),
            edit(os.path.join(d, 'mmm_datapath.ll'), '%45 = add i32 %load_c_22_0, %37\n', ''),
            edit(os.path.join(d, 'mmm_datapath.ll'), 'store i32 %45, i32* %gep_c_22_0, align 4',
                 'store i32 %load_c_22_7, i32* %gep_c_22_0, align 4')),
            failures, 'address program computes under a %load_ name', 'a value it computed itself')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: (
            edit(os.path.join(d, 'mmm_datapath.ll'), 'ret i32 %56', '%late = add i32 %load_a_22_0, 0\nret i32 %late')),
            failures, 'datapath reads a load outside its block', 'not the block that loaded it')
        def datapath_peeks_n(d):
            path = os.path.join(d, 'gn_datapath.ll')
            text = read(path)
            first = re.search(r'^; block \S+\n', text, re.M)
            with open(path, 'w') as f:
                f.write(text[:first.end()] + '%peek = load i32, i32* @n, align 4\n' + text[first.end():])
        verifier_fails(gn_source, gn_out, 'gn', datapath_peeks_n,
            failures, 'datapath reads a streamed scalar itself', 'which an address program streams')
        # Rules that had no mutation: a load's stream register names its
        # block, a %gep_ is defined in its block, nothing follows the
        # datapath's ret, an element is loaded only into a %load_
        # register, every program has the same blocks, fmul on integers.
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: (
            edit(os.path.join(d, 'mmm_c_agu.ll'), '%load_c_22_0 = load i32, i32* %gep_c_22_0', '%load_c_46_0 = load i32, i32* %gep_c_22_0'),
            edit(os.path.join(d, 'mmm_datapath.ll'), '%load_c_22_0 = load i32, i32* %gep_c_22_0', '%load_c_46_0 = load i32, i32* %gep_c_22_0'),
            edit(os.path.join(d, 'mmm_datapath.ll'), '%45 = add i32 %load_c_22_0, %37', '%45 = add i32 %load_c_46_0, %37')),
            failures, 'load register names another block', 'loads through %gep_c_22_0 in block 22')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_c_agu.ll'), '%gep_c_22_0 = getelementptr', '%gep_c_46_0 = getelementptr'),
            failures, 'stream address named after another block', 'is defined in block 22')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), 'ret i32 %56\n', 'ret i32 %56\n%zz = add i32 %56, 1\n'),
            failures, 'datapath instruction after its ret', 'follows its ret')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: (
            edit(os.path.join(d, 'mmm_c_agu.ll'), '%load_c_22_0 = load i32, i32* %gep_c_22_0', '%x = load i32, i32* %gep_c_22_0')),
            failures, 'element loaded into a register not named %load_', 'other than through a stream address')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_a_agu.ll'), 'ret:\n  ret void', 'zz:\n  br label %ret\n\nret:\n  ret void'),
            failures, 'programs with different blocks', 'do not have the same blocks')
        verifier_fails(mmm_source, runs['1'], 'mmm', lambda d: edit(
            os.path.join(d, 'mmm_datapath.ll'), '%37 = mul i32', '%37 = fmul i32'),
            failures, 'floating-point operation on integers', 'on an integer type')
        verifier_fails(zs_source, zs_out, 'zs', lambda d: edit(
            os.path.join(d, 'zs_ptr_p_agu.ll'), '  store i32 0, i32* %gep_ptr_p_for.body_0, align 4\n',
            '  store i32 0, i32* %gep_ptr_p_for.body_0, align 4\n'
            '  %gep_ptr_p_for.body_1 = getelementptr inbounds [0 x i32], [0 x i32]* @ptr_p, i64 0, i64 1000\n'
            '  %load_ptr_p_for.body_1 = load i32, i32* %gep_ptr_p_for.body_1, align 4\n'),
            failures, 'pointer array read past the source\'s footprint', 'the source never touched')
        for key in if_cases[:1]:
            source_if, out_if, prefix_if = generated[key]
            returncode, text = run_verifier(source_if, out_if, prefix_if, seed='wide')
            check('BX round ten the if variant verifies under a wide fill', returncode == 0, failures)
        # The goto in the cross-loop join depends on the data: every fill
        # must agree, whichever path it takes.
        if 'cj' in generated:
            source_cj, out_cj, _ = generated['cj']
            for seed in ('second', 'third', 'wide'):
                returncode, text = run_verifier(source_cj, out_cj, 'cj', seed=seed)
                check(f'BX round ten the cross-loop join verifies under fill {seed}', returncode == 0, failures)
        sentinel_cases = [key for key in generated if key == 'sn']
        for key in sentinel_cases[:1]:
            source_sn, out_sn, prefix_sn = generated[key]
            returncode, text = run_verifier(source_sn, out_sn, prefix_sn, seed='second')
            check('BX round ten a sentinel source out of range under a fill is reported, not judged',
                  returncode in (0, 3) and (returncode == 0 or 'SOURCE OUT OF RANGE' in text), failures)
        check('BX round ten a sentinel variant exists', bool(sentinel_cases), failures)
        result = subprocess.run([sys.executable, os.path.join(UNROLL_DIR, 'gen_mmm.py'), '--help'],
                                capture_output=True, text=True)
        check('BX round ten gen_mmm.py --help prints its options', result.returncode == 0 and '--switch' in result.stdout, failures)

        # --- BC: pointers the model cannot name ------------------------------
        for label, text, needle in (
                ('a re-assigned pointer parameter', PTR_REASSIGN_SOURCE, 'other than its parameter'),
                ('a pointer copied into a local', PTR_COPY_SOURCE, 'other than its parameter'),
                ('a second function', DEREF_SOURCE + SECOND_FUNCTION, 'one function per module'),
                ('a value used outside its block', CROSS_BLOCK_SOURCE, 'crosses blocks')):
            bad = os.path.join(root, 'ptr_' + label.split()[1])
            os.makedirs(bad, exist_ok=True)
            with open(os.path.join(bad, 'bad.ll'), 'w') as f:
                f.write(text)
            ok, output = run_stages(os.path.join(bad, 'out'), bad, 'bad', 'bd', '1')
            check(f'BC pointers   {label} is refused', not ok and needle in output, failures)

        # --- F: AGU / datapath register linkage ----------------------
        check_linkage(runs['1'], 'mmm', 'mmm', failures)
        check_linkage(ren, 'ren', 'renamed', failures)
        check_linkage(d16, 'd16', '16x16 i64', failures)

        # --- G: the generated code computes the same thing -----------
        cases = [('mmm', os.path.join(TEST_DIR, 'mmm.ll'), runs['1'], 'mmm')]
        for key, (source, out, prefix) in sorted(generated.items(),
                                                 key=lambda kv: str(kv[0])):
            label = f'unroll {key}' if isinstance(key, int) else key
            cases.append((label, source, out, prefix))
        for label, source, out_dir, prefix in cases:
            returncode, text = run_verifier(source, out_dir, prefix)
            check(f'G semantics   {label}: matches the source', returncode == 0, failures)
            if returncode != 0:
                print('      ' + text.strip().replace('\n', '\n      ')[-1500:])

    except RuntimeError as error:
        # A case an earlier section failed to produce: the checks that
        # build on it cannot run, but the failures so far are reported.
        failures.append(f'aborted: {error}')
        print(f'  FAIL  {error}')
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == '__main__':
    sys.exit(main())
