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
Emit matrix-multiply LLVM IR to exercise the front end.

    python gen_mmm.py --size 24 --factor 3 --out mmm24_unroll3.ll

Options shape the loop nest:

  --factor N    unroll the innermost loop N times. The inner dimension
                must be a multiple of N so no remainder iteration is
                needed. An odd factor leaves an odd number of products to
                reduce, an even one pairs up.
  --shape M,N,K c[M][N] = a[M][K] * b[K][N]: three different trip counts
                and three differently shaped arrays, so a bound taken
                from the wrong place shows. --size M is short for M,M,M.
  --start S     every loop counter starts from S instead of 0.
  --le          loops test `counter <= bound - 1` instead of
                `counter < bound`; the trip count is unchanged.
  --minus       the unrolled copies read k - step instead of k + step,
                with k starting at factor - 1, so a subscript with a
                negative constant offset is exercised.
  --while       the innermost loop is a `while`: two blocks, the body
                advancing the counter itself and branching back to the
                compare, with no separate latch block.
  --do          the innermost loop is a `do ... while`: one block that
                does the work, advances the counter and then tests it.
  --dopre       like --do, but the compare reads the counter before the
                block advances it: `do { ... } while (k++ < K - 1)`.
  --continue    the innermost loop is a `while` whose body skips odd k
                with `k++; continue;`, so the loop has two latches.
  --sentinel    the innermost loop is `while (a[i][k] != 0)`: its header
                decides on a loaded value, not on the counter.
  --irreducible the innermost loop is two blocks that alternate, entered
                at either one depending on j: an irreducible cycle with
                no natural loop, whose counter is an ordinary scalar.
  --if          the product is only accumulated when a[i][k] > 0: a
                conditional branch inside the body on a loaded value.
  --switch      k % 3 selects whether the product is added, subtracted
                or ignored: a switch inside the body.
  --copy        the innermost body copies a[i][k] into c[i][j] and does
                no arithmetic at all.
  --expr        b is read as b[(k + j) % K][j]: a subscript computed from
                two counters and a literal.
  --indirect    b is read as b[idx[k]][j] with idx[k] = (5 k) % K written
                just before: a subscript loaded from another array.
  --ptr         the arrays are pointer parameters of the function and
                are indexed flat, as a[i * K + k]: no declared extent.
  --variables   the loops compare against a global `@n` and start from a
                local `s`, both variables rather than literals.
  --vstep       the innermost loop advances by a global `@step`.
  --param       the bounds come from an integer parameter `n` of the
                function, spilled to `%n.addr` as clang does.
  --float       the arrays hold doubles: fmul/fadd, an fcmp when --if is
                given, and (double)k added to each product via sitofp.
  --call        each product is clamped with `@llvm.smax.i32`, a call
                the datapath carries.
  --select      each product is clamped with a `select` instead.
  --break       the innermost loop is `for (;;)`: its header tests
                a[i][k] > 0 between two of its own blocks, and the latch
                leaves when k reaches K -- a header with no exit compare.
  --local       a[i][k] is staged through a local array t[k] before use.
  --sequential  two loop nests one after the other, the second computing
                a second product over its own arrays but reusing the same
                counter variables.
  --names       named labels and named counter allocas (`for.cond.i`,
                `%i`), the way clang emits them with value names kept,
                and an explicit `entry:` label.
  --opaque      opaque pointers (`ptr`) instead of typed ones (`i32*`),
                the syntax of LLVM 15 and later.
  --products N  compute N independent matrix products in the same nest,
                each over its own three arrays. Checks that separate
                address streams are generated per product.
  --straight    wrap the loop nest in straight-line code: a prologue that
                writes p[0] from constant subscripts, and an epilogue that
                reads p[0] back together with the loop's result. Gives the
                ordinary program shape of setup, loop, teardown.
  --loop-scalar the nest accumulates a scalar instead of computing matrix
                products, so nothing inside it touches an array. Combined
                with --straight or --scalar this covers all four ways of
                mixing arrays and scalars inside and outside a loop.
  --scalar      like --straight, but the code outside the loop nest uses
                only a scalar local: no array is touched there. The nest
                scales its products by that scalar, so the prologue still
                reaches the arrays through a data dependency.
  --between     compute v[i] in the block between the outer and middle
                loops and scale each product by it in the innermost block.
                The two are joined by a real data dependency, so this
                checks that work outside the innermost block feeds the
                inner computation, and that a one-dimensional access is
                handled.

Registers and block labels share one counter, the way clang numbers
unnamed values, so the output looks like the input the front end normally
sees; `renumber.py` puts them in textual order, as `llvm-as` demands.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from renumber import renumber  # noqa: E402

# Array names per product: (lhs, rhs, accumulator).
TRIPLES = [('a', 'b', 'c'), ('d', 'e', 'f'), ('g', 'h', 'm')]
BETWEEN_ARRAY = 'v'
STRAIGHT_ARRAY = 'p'
BOUND_GLOBAL = 'n'
STEP_GLOBAL = 'step'
INDEX_ARRAY = 'idx'
ELEM = 'i32'


class Emitter:
    """Emits instructions while handing out the next unnamed value."""

    def __init__(self, names: bool = False):
        self.counter = 1
        self.lines = []
        self.names = names
        self.used = set()

    def take(self) -> int:
        value = self.counter
        self.counter += 1
        return value

    def take_label(self, base: str):
        """A block label: the next number, or a unique name."""
        if not self.names:
            return self.take()
        name = base
        suffix = 1
        while name in self.used:
            suffix += 1
            name = f'{base}{suffix}'
        self.used.add(name)
        return name

    def take_ptr(self, base: str):
        """A counter alloca: the next number, or its name."""
        return base if self.names else self.take()

    def emit(self, line: str) -> None:
        self.lines.append('  ' + line)

    def label(self, block) -> None:
        self.lines.append('')
        self.lines.append(f'{block}:')


def generate(shape, factor: int, products: int, between: bool,
             straight: bool = False, scalar: bool = False,
             loop_scalar: bool = False, start: int = 0, le: bool = False,
             minus: bool = False, while_loop: bool = False,
             sequential: bool = False, names: bool = False,
             opaque: bool = False, do_loop: bool = False,
             continue_loop: bool = False, if_body: bool = False,
             switch_body: bool = False, copy_body: bool = False,
             variables: bool = False, local_array: bool = False,
             dopre: bool = False, sentinel: bool = False,
             irreducible: bool = False, expr: bool = False,
             indirect: bool = False, ptr: bool = False,
             vstep: bool = False, param: bool = False,
             float_data: bool = False, call: bool = False,
             select: bool = False, break_loop: bool = False) -> str:
    rows, cols, inner = shape
    if start < 0:
        raise SystemExit("--start must not be negative: a subscript would be")
    # Reading k .. k+factor-1 while k < inner overruns unless the steps
    # land exactly on inner; --minus reads k-factor+1 .. k and cannot.
    if not minus and (inner - start) % factor:
        raise SystemExit(f"the inner loop runs from {start} to {inner} in steps of {factor}, "
                         f"which is not a whole number of steps: the last body would read past the end")
    if vstep and (inner - start) % 2:
        raise SystemExit(f"--vstep advances by 2 from {start}, which does not reach {inner} exactly")
    if not 1 <= products <= len(TRIPLES):
        raise SystemExit(f"products must be between 1 and {len(TRIPLES)}")
    if sequential and products > 1:
        raise SystemExit("--sequential takes one product per nest")
    stride = 2 if vstep else factor
    if minus and start:
        raise SystemExit("--minus starts the inner counter at factor - 1, so --start does not apply to it")
    first = factor - 1 if minus else start
    if start >= inner and (do_loop or dopre or irreducible or break_loop):
        raise SystemExit(f"--start {start} is past the inner dimension {inner}, and this shape runs "
                         f"its body once before testing")
    if start > inner:
        raise SystemExit(f"--start {start} is past the inner dimension {inner}")
    if sentinel and (first + 6 * stride >= inner or stride % 7 == 0):
        raise SystemExit("--sentinel probes a[i][k] every `factor` elements from `start` and the "
                         "verifier's input pattern repeats every 7: the first zero can be 6 steps "
                         "away, so start + 6 * factor must stay below the inner dimension and the "
                         "factor must not be a multiple of 7")
    if sum([do_loop, dopre, continue_loop, while_loop, sentinel, irreducible, break_loop]) > 1:
        raise SystemExit("--while, --do, --dopre, --continue, --sentinel, --irreducible and "
                         "--break exclude one another")
    if sum([if_body, switch_body, copy_body]) > 1:
        raise SystemExit("--if, --switch and --copy exclude one another")
    if ptr and (straight or scalar or loop_scalar or between or sequential or local_array
                or expr or indirect):
        raise SystemExit("--ptr takes only the plain nest")
    if vstep and inner % 2:
        raise SystemExit("--vstep steps by 2, so the inner dimension must be even")
    if vstep and factor > 2:
        raise SystemExit("--vstep advances by 2, so --factor can be at most 2")
    if vstep and (do_loop or dopre or continue_loop or irreducible or break_loop):
        raise SystemExit("--vstep applies to the for and while shapes only")
    if (param or variables) and not rows == cols == inner:
        raise SystemExit("--param and --variables bound every loop alike: the shape must be square")
    if param and rows < 20:
        raise SystemExit("--param is verified with n = 20, so --size must be at least 20")
    if le and (param or variables):
        raise SystemExit("--le compares against a literal; it does not combine with --param or --variables")
    if loop_scalar and (if_body or switch_body or copy_body):
        raise SystemExit("--loop-scalar has no product for --if, --switch or --copy to shape")
    if factor > 1 and (continue_loop or copy_body):
        raise SystemExit("--continue and --copy advance by one and read one element: --factor must be 1")
    if minus and factor == 1:
        raise SystemExit("--minus reads a[i][k-1..]: it needs --factor of at least 2")
    if float_data and (straight or scalar or loop_scalar or between or local_array
                       or indirect or copy_body or switch_body or call or select or break_loop):
        raise SystemExit("--float takes the plain nest, optionally with --if")
    if (call or select) and (copy_body or loop_scalar):
        raise SystemExit("--call and --select need a product to clamp")
    if break_loop and (if_body or switch_body or copy_body or loop_scalar):
        raise SystemExit("--break brings its own body")

    DATA = 'double' if float_data else ELEM
    ZERO = '0.000000e+00' if float_data else '0'

    triples = TRIPLES[:products]
    nests = [triples, [TRIPLES[1]]] if sequential else [triples]
    e = Emitter(names)

    # Shapes: a[M][K], b[K][N], c[M][N]; v and p are rows of M, t and idx
    # rows of K.
    dims = {}
    for lhs, rhs, acc in [t for nest in nests for t in nest]:
        dims[lhs] = [rows, inner]
        dims[rhs] = [inner, cols]
        dims[acc] = [rows, cols]
    dims[BETWEEN_ARRAY] = [rows]
    dims[STRAIGHT_ARRAY] = [rows]
    dims['t'] = [inner]
    dims[INDEX_ARRAY] = [inner]
    pointer_arrays = {name for triple in triples for name in triple} if ptr else set()

    data_arrays = {name for triple in TRIPLES for name in triple}

    def type_of(array: str, depth: int = 0) -> str:
        """LLVM type of an array, or of the row `depth` subscripts in."""
        type_str = DATA if array in data_arrays else ELEM
        for size in reversed(dims[array][depth:]):
            type_str = f'[{size} x {type_str}]'
        return type_str

    def ptr_to(type_str: str) -> str:
        return 'ptr' if opaque else f'{type_str}*'

    lhs0, rhs0, acc0 = triples[0]
    addr_of = {}
    if ptr:
        for name in sorted(pointer_arrays):
            addr_of[name] = e.take_ptr(f'{name}.addr') if names else e.take()
    ret_p = None if ptr else e.take_ptr('retval')
    i_p, j_p, k_p = e.take_ptr('i'), e.take_ptr('j'), e.take_ptr('k')
    scalar_p = e.take_ptr('s') if scalar else None
    sum_p = e.take_ptr('sum') if loop_scalar else None
    start_p = e.take_ptr('start') if variables else None
    t_p = e.take_ptr('t') if local_array else None
    n_addr = e.take_ptr('n.addr') if param else None
    for name in sorted(pointer_arrays):
        e.emit(f'%{addr_of[name]} = alloca {ptr_to(DATA)}, align 8')
    if param:
        e.emit(f'%{n_addr} = alloca {ELEM}, align 4')
    for reg in ([] if ptr else [ret_p]) + [i_p, j_p, k_p]:
        e.emit(f'%{reg} = alloca {ELEM}, align 4')
    if scalar:
        e.emit(f'%{scalar_p} = alloca {ELEM}, align 4')
    if loop_scalar:
        e.emit(f'%{sum_p} = alloca {ELEM}, align 4')
    if variables:
        e.emit(f'%{start_p} = alloca {ELEM}, align 4')
    if local_array:
        e.emit(f'%{t_p} = alloca {type_of("t")}, align 16')
    for name in sorted(pointer_arrays):
        e.emit(f'store {ptr_to(DATA)} %{name}, {ptr_to(ptr_to(DATA))} %{addr_of[name]}, align 8')
    if param:
        e.emit(f'store {ELEM} %n, {ptr_to(ELEM)} %{n_addr}, align 4')
    if loop_scalar:
        e.emit(f'store {ELEM} 0, {ptr_to(ELEM)} %{sum_p}, align 4')
    if not ptr:
        e.emit(f'store {ELEM} 0, {ptr_to(ELEM)} %{ret_p}, align 4')
    if variables:
        # The bounds live in a global, the start in a local; both are
        # read back where the loops need them.
        e.emit(f'store {ELEM} {start}, {ptr_to(ELEM)} %{start_p}, align 4')
    k_start = factor - 1 if minus else start

    def load(pointer, type_str: str = ELEM) -> int:
        value = e.take()
        e.emit(f'%{value} = load {type_str}, {ptr_to(type_str)} {pointer}, align 4')
        return value

    def store(value, pointer, type_str: str = ELEM) -> None:
        e.emit(f'store {type_str} {value}, {ptr_to(type_str)} {pointer}, align 4')

    def load_data(pointer) -> int:
        return load(pointer, DATA)

    def store_data(value, pointer) -> None:
        store(value, pointer, DATA)

    def counter_value(ptr_reg) -> int:
        return load(f'%{ptr_reg}')

    def binop(op: str, lhs, rhs) -> int:
        value = e.take()
        flags = 'nsw ' if op in ('add', 'sub', 'mul') else ''
        e.emit(f'%{value} = {op} {flags}{ELEM} {lhs}, {rhs}')
        return value

    def data_op(op: str, lhs, rhs) -> int:
        """add/sub/mul on the array data, integer or floating."""
        if not float_data:
            return binop(op, lhs, rhs)
        value = e.take()
        e.emit(f'%{value} = f{op} {DATA} {lhs}, {rhs}')
        return value

    def widen(value) -> int:
        wide = e.take()
        e.emit(f'%{wide} = sext {ELEM} %{value} to i64')
        return wide

    def subscript(ptr_reg, offset: int = 0) -> int:
        """Load a loop counter, add a constant, and sign extend it."""
        value = counter_value(ptr_reg)
        if offset:
            value = binop('sub' if offset < 0 else 'add', f'%{value}', abs(offset))
        return widen(value)

    def address(array: str, outer: int, inner_sub: int) -> int:
        """Two-step getelementptr chain, outermost subscript first."""
        base = e.take()
        e.emit(f'%{base} = getelementptr inbounds {type_of(array)}, '
               f'{ptr_to(type_of(array))} @{array}, i64 0, i64 %{outer}')
        cell_reg = e.take()
        e.emit(f'%{cell_reg} = getelementptr inbounds {type_of(array, 1)}, '
               f'{ptr_to(type_of(array, 1))} %{base}, i64 0, i64 %{inner_sub}')
        return cell_reg

    def flat(array: str, outer: int, inner_sub: int) -> int:
        """A pointer parameter indexed as array[outer * stride + inner]."""
        pointer = e.take()
        e.emit(f'%{pointer} = load {ptr_to(DATA)}, {ptr_to(ptr_to(DATA))} %{addr_of[array]}, align 8')
        row = binop('mul', f'%{outer}', dims[array][1])
        total = binop('add', f'%{row}', f'%{inner_sub}')
        cell_reg = e.take()
        e.emit(f'%{cell_reg} = getelementptr inbounds {DATA}, {ptr_to(DATA)} %{pointer}, i64 %{widen(total)}')
        return cell_reg

    def cell(array: str, row_ptr, col_ptr, col_offset: int = 0, row_offset: int = 0) -> int:
        """The address of array[row][col], however the array is reached."""
        if ptr:
            row = counter_value(row_ptr)
            if row_offset:
                row = binop('sub' if row_offset < 0 else 'add', f'%{row}', abs(row_offset))
            col = counter_value(col_ptr)
            if col_offset:
                col = binop('sub' if col_offset < 0 else 'add', f'%{col}', abs(col_offset))
            return flat(array, row, col)
        return address(array, subscript(row_ptr, row_offset), subscript(col_ptr, col_offset))

    def element(array: str, subscripts) -> int:
        """Address one element with literal subscripts."""
        cell_reg = e.take()
        e.emit(f'%{cell_reg} = getelementptr inbounds {type_of(array)}, '
               f'{ptr_to(type_of(array))} @{array}, i64 0, i64 {subscripts[0]}')
        for depth, value in enumerate(subscripts[1:], 1):
            nxt = e.take()
            e.emit(f'%{nxt} = getelementptr inbounds {type_of(array, depth)}, '
                   f'{ptr_to(type_of(array, depth))} %{cell_reg}, i64 0, i64 {value}')
            cell_reg = nxt
        return cell_reg

    def start_value() -> str:
        """The literal, or the register the start is loaded into."""
        if not variables:
            return str(start)
        return f'%{load(f"%{start_p}")}'

    def compare(reg: int, bound: int) -> int:
        if variables:
            limit = f'%{load(f"@{BOUND_GLOBAL}")}'
        elif param:
            limit = f'%{load(f"%{n_addr}")}'
        else:
            limit = str(bound - 1 if le else bound)
        predicate = 'sle' if (le and not variables and not param) else 'slt'
        cond = e.take()
        e.emit(f'%{cond} = icmp {predicate} {ELEM} %{reg}, {limit}')
        return cond

    def advance(ptr_reg, step: int, variable: bool = False) -> None:
        reg = counter_value(ptr_reg)
        amount = f'%{load(f"@{STEP_GLOBAL}")}' if variable else str(step)
        nxt = binop('add', f'%{reg}', amount)
        store(f'%{nxt}', f'%{ptr_reg}')

    # Prologue: straight-line work before any loop runs. p[0] is read
    # back by the epilogue, so the two ends of the program are joined.
    if straight:
        left = load_data(f'%{element(lhs0, [0, 0])}')
        right = load_data(f'%{element(rhs0, [0, 0])}')
        seeded = binop('mul', f'%{left}', f'%{right}')
        store(f'%{seeded}', f'%{element(STRAIGHT_ARRAY, [0])}')

    # Prologue with no array access at all: a scalar local is set up
    # here and read inside the nest, so the two are still connected.
    if scalar:
        store('3', f'%{scalar_p}')
        seed = load(f'%{scalar_p}')
        scaled = binop('mul', f'%{seed}', 5)
        store(f'%{scaled}', f'%{scalar_p}')

    replacements = {}

    def rhs_cell(rhs: str, offset: int) -> int:
        """b[k + offset][j], or one of the computed-row variants."""
        if expr:
            # b[(k + j) % K][j]
            k_val = counter_value(k_p)
            if offset:
                k_val = binop('sub' if offset < 0 else 'add', f'%{k_val}', abs(offset))
            total = binop('add', f'%{k_val}', f'%{counter_value(j_p)}')
            row = binop('srem', f'%{total}', inner)
            return address(rhs, widen(row), subscript(j_p))
        if indirect:
            # idx[k] = (5 k) % K; b[idx[k]][j]
            k_val = counter_value(k_p)
            if offset:
                k_val = binop('sub' if offset < 0 else 'add', f'%{k_val}', abs(offset))
            scaled = binop('mul', f'%{k_val}', 5)
            row = binop('srem', f'%{scaled}', inner)
            slot = e.take()
            e.emit(f'%{slot} = getelementptr inbounds {type_of(INDEX_ARRAY)}, '
                   f'{ptr_to(type_of(INDEX_ARRAY))} @{INDEX_ARRAY}, i64 0, i64 %{widen(k_val)}')
            store(f'%{row}', f'%{slot}')
            loaded = load(f'%{slot}')
            return address(rhs, widen(loaded), subscript(j_p))
        return cell(rhs, k_p, j_p, row_offset=offset)

    def product(lhs: str, rhs: str, acc: str, negate: bool = False) -> None:
        """c[i][j] += (or -=) the sum of the unrolled products."""
        summands = []
        for step in range(factor):
            offset = -step if minus else step
            if local_array:
                # Stage a[i][k] through t[k] before using it.
                staged = load_data(f'%{cell(lhs, i_p, k_p, offset)}')
                slot = e.take()
                e.emit(f'%{slot} = getelementptr inbounds {type_of("t")}, '
                       f'{ptr_to(type_of("t"))} %{t_p}, i64 0, i64 %{subscript(k_p, offset)}')
                store(f'%{staged}', f'%{slot}')
                lhs_val = load(f'%{slot}')
            else:
                lhs_val = load_data(f'%{cell(lhs, i_p, k_p, offset)}')
            rhs_val = load_data(f'%{rhs_cell(rhs, offset)}')
            prod = data_op('mul', f'%{lhs_val}', f'%{rhs_val}')
            if call:
                # Clamp at zero through an intrinsic the datapath calls.
                clamped = e.take()
                e.emit(f'%{clamped} = call {ELEM} @llvm.smax.i32({ELEM} %{prod}, {ELEM} 0)')
                prod = clamped
            if select:
                positive = e.take()
                e.emit(f'%{positive} = icmp sgt {ELEM} %{prod}, 0')
                clamped = e.take()
                e.emit(f'%{clamped} = select i1 %{positive}, {ELEM} %{prod}, {ELEM} 0')
                prod = clamped
            summands.append(prod)

        total = summands[0]
        for prod in summands[1:]:
            total = data_op('add', f'%{total}', f'%{prod}')

        if float_data:
            # Mix the integer counter in, through a cast.
            widened = e.take()
            e.emit(f'%{widened} = sitofp {ELEM} %{counter_value(k_p)} to {DATA}')
            total = data_op('add', f'%{total}', f'%{widened}')

        if scalar:
            # The nest reads the scalar the prologue produced.
            factor_val = load(f'%{scalar_p}')
            total = binop('mul', f'%{total}', f'%{factor_val}')

        if between:
            # Consume the value the outer level produced.
            index = subscript(i_p)
            cell_reg = e.take()
            e.emit(f'%{cell_reg} = getelementptr inbounds {type_of(BETWEEN_ARRAY)}, '
                   f'{ptr_to(type_of(BETWEEN_ARRAY))} @{BETWEEN_ARRAY}, i64 0, i64 %{index}')
            scale = load(f'%{cell_reg}')
            total = binop('mul', f'%{total}', f'%{scale}')

        cell_reg = cell(acc, i_p, j_p)
        old = load_data(f'%{cell_reg}')
        new = data_op('sub' if negate else 'add', f'%{old}', f'%{total}')
        store_data(f'%{new}', f'%{cell_reg}')

    def body(nest_triples) -> None:
        """The work of the innermost block, in one of its shapes."""
        if loop_scalar:
            running = load(f'%{sum_p}')
            counter = counter_value(k_p)
            grown = binop('add', f'%{running}', f'%{counter}')
            store(f'%{grown}', f'%{sum_p}')
            return

        for lhs, rhs, acc in nest_triples:
            if copy_body:
                value = load_data(f'%{cell(lhs, i_p, k_p)}')
                store_data(f'%{value}', f'%{cell(acc, i_p, j_p)}')
            elif if_body:
                value = load_data(f'%{cell(lhs, i_p, k_p)}')
                cond = e.take()
                if float_data:
                    e.emit(f'%{cond} = fcmp ogt {DATA} %{value}, {ZERO}')
                else:
                    e.emit(f'%{cond} = icmp sgt {ELEM} %{value}, 0')
                then = e.take_label('if.then')
                end = e.take_label('if.end')
                e.emit(f'br i1 %{cond}, label %{then}, label %{end}')
                e.label(then)
                product(lhs, rhs, acc)
                e.emit(f'br label %{end}')
                e.label(end)
            elif switch_body:
                counter = counter_value(k_p)
                rem = binop('srem', f'%{counter}', 3)
                case0 = e.take_label('sw.bb')
                case1 = e.take_label('sw.bb')
                default = e.take_label('sw.default')
                end = e.take_label('sw.epilog')
                e.emit(f'switch {ELEM} %{rem}, label %{default} [')
                e.lines.append(f'    {ELEM} 0, label %{case0}')
                e.lines.append(f'    {ELEM} 1, label %{case1}')
                e.lines.append('  ]')
                e.label(case0)
                product(lhs, rhs, acc)
                e.emit(f'br label %{end}')
                e.label(case1)
                product(lhs, rhs, acc, negate=True)
                e.emit(f'br label %{end}')
                e.label(default)
                e.emit(f'br label %{end}')
                e.label(end)
            else:
                product(lhs, rhs, acc)

    def nest(nest_triples, tag: str) -> None:
        """One three-level nest; the caller's block sets i up first."""
        store(start_value(), f'%{i_p}')
        i_head = e.take_label('for.cond.i')
        e.emit(f'br label %{i_head}')

        # Outer loop header
        e.label(i_head)
        cond = compare(counter_value(i_p), rows)
        i_body = e.take_label('for.body.i')
        e.emit(f'br i1 %{cond}, label %{i_body}, label %__END{tag}__')

        # Between the outer and middle loops: v[i] = i + 7, plus j = start.
        # The innermost block reads v[i] back, so the two nesting levels are
        # joined by a data dependency rather than sitting side by side.
        e.label(i_body)
        if between:
            value = counter_value(i_p)
            shifted = binop('add', f'%{value}', 7)
            index = subscript(i_p)
            cell_reg = e.take()
            e.emit(f'%{cell_reg} = getelementptr inbounds {type_of(BETWEEN_ARRAY)}, '
                   f'{ptr_to(type_of(BETWEEN_ARRAY))} @{BETWEEN_ARRAY}, i64 0, i64 %{index}')
            store(f'%{shifted}', f'%{cell_reg}')
        store(start_value(), f'%{j_p}')
        j_head = e.take_label('for.cond.j')
        e.emit(f'br label %{j_head}')

        # Middle loop header
        e.label(j_head)
        cond = compare(counter_value(j_p), cols)
        j_body = e.take_label('for.body.j')
        e.emit(f'br i1 %{cond}, label %{j_body}, label %__I_LATCH{tag}__')

        # Zero every accumulator, then k = start.
        e.label(j_body)
        for _, _, acc in ([] if loop_scalar else nest_triples):
            store_data(ZERO, f'%{cell(acc, i_p, j_p)}')
        store(start_value() if not minus else str(k_start), f'%{k_p}')

        if break_loop:
            # for (;;) { if (a[i][k] > 0) c += a*b; k++; if (k >= K) break; }
            k_head = e.take_label('for.body')
            e.emit(f'br label %{k_head}')
            e.label(k_head)
            lhs, rhs, acc = nest_triples[0]
            probe = load_data(f'%{cell(lhs, i_p, k_p)}')
            positive = e.take()
            e.emit(f'%{positive} = icmp sgt {ELEM} %{probe}, 0')
            then = e.take_label('if.then')
            latch = e.take_label('if.end')
            e.emit(f'br i1 %{positive}, label %{then}, label %{latch}')
            e.label(then)
            for triple in nest_triples:
                product(*triple)
            e.emit(f'br label %{latch}')
            e.label(latch)
            advance(k_p, factor)
            more = compare(counter_value(k_p), inner)
            e.emit(f'br i1 %{more}, label %{k_head}, label %__J_LATCH{tag}__')
        elif do_loop or dopre:
            # do { work; k += step } while (k < K), testing the advanced
            # counter (--do) or the one before the update (--dopre).
            k_body = e.take_label('do.body')
            e.emit(f'br label %{k_body}')
            e.label(k_body)
            body(nest_triples)
            old = counter_value(k_p)
            new = binop('add', f'%{old}', factor)
            store(f'%{new}', f'%{k_p}')
            if dopre:
                cond = e.take()
                e.emit(f'%{cond} = icmp slt {ELEM} %{old}, {inner - factor}')
            else:
                cond = compare(counter_value(k_p), inner)
            e.emit(f'br i1 %{cond}, label %{k_body}, label %__J_LATCH{tag}__')
        elif irreducible:
            # Two alternating blocks, entered at either depending on j.
            first = e.take_label('alt.a')
            second = e.take_label('alt.b')
            parity = binop('srem', f'%{counter_value(j_p)}', 2)
            even = e.take()
            e.emit(f'%{even} = icmp eq {ELEM} %{parity}, 0')
            e.emit(f'br i1 %{even}, label %{first}, label %{second}')
            for block, other in ((first, second), (second, first)):
                e.label(block)
                body(nest_triples)
                advance(k_p, factor)
                cond = compare(counter_value(k_p), inner)
                e.emit(f'br i1 %{cond}, label %{other}, label %__J_LATCH{tag}__')
        else:
            two_block = while_loop or continue_loop or sentinel
            k_head = e.take_label('while.cond.k' if two_block else 'for.cond.k')
            e.emit(f'br label %{k_head}')

            # Inner loop header
            e.label(k_head)
            if sentinel:
                # while (a[i][k] != 0)
                probe = load_data(f'%{cell(nest_triples[0][0], i_p, k_p)}')
                cond = e.take()
                if float_data:
                    e.emit(f'%{cond} = fcmp une {DATA} %{probe}, {ZERO}')
                else:
                    e.emit(f'%{cond} = icmp ne {ELEM} %{probe}, 0')
            else:
                cond = compare(counter_value(k_p), inner)
            k_body = e.take_label('while.body.k' if two_block else 'for.body.k')
            e.emit(f'br i1 %{cond}, label %{k_body}, label %__J_LATCH{tag}__')

            e.label(k_body)
            if continue_loop:
                # if (k % 2 == 1) { k++; continue; }
                counter = counter_value(k_p)
                rem = binop('srem', f'%{counter}', 2)
                odd = e.take()
                e.emit(f'%{odd} = icmp eq {ELEM} %{rem}, 1')
                skip = e.take_label('if.then')
                work = e.take_label('if.end')
                e.emit(f'br i1 %{odd}, label %{skip}, label %{work}')
                e.label(skip)
                advance(k_p, 1)
                e.emit(f'br label %{k_head}')
                e.label(work)
                body(nest_triples)
                advance(k_p, 1)
                e.emit(f'br label %{k_head}')
            elif two_block:
                body(nest_triples)
                # The body advances the counter and goes back to the compare.
                advance(k_p, factor, vstep)
                e.emit(f'br label %{k_head}')
            else:
                body(nest_triples)
                k_latch = e.take_label('for.inc.k')
                e.emit(f'br label %{k_latch}')
                e.label(k_latch)
                advance(k_p, factor, vstep)
                e.emit(f'br label %{k_head}')

        j_latch = e.take_label('for.inc.j')
        e.label(j_latch)
        advance(j_p, 1)
        e.emit(f'br label %{j_head}')
        i_latch = e.take_label('for.inc.i')
        e.label(i_latch)
        advance(i_p, 1)
        e.emit(f'br label %{i_head}')

        end = e.take_label('for.end.i')
        e.label(end)
        replacements[f'__END{tag}__'] = str(end)
        replacements[f'__I_LATCH{tag}__'] = str(i_latch)
        replacements[f'__J_LATCH{tag}__'] = str(j_latch)

    for number, nest_triples in enumerate(nests):
        nest(nest_triples, chr(ord('A') + number))

    # Epilogue: straight-line work after the nest, reading both the value
    # the prologue produced and the value the loop computed.
    if straight:
        seeded = load(f'%{element(STRAIGHT_ARRAY, [0])}')
        if loop_scalar:
            computed = load(f'%{sum_p}')
        else:
            computed = load_data(f'%{element(acc0, [0, 0])}')
        combined = binop('add', f'%{seeded}', f'%{computed}')
        store(f'%{combined}', f'%{element(STRAIGHT_ARRAY, [1])}')
    # Epilogue with no array access either.
    if scalar:
        tail = load(f'%{scalar_p}')
        if loop_scalar:
            # Consume what the nest accumulated.
            produced = load(f'%{sum_p}')
            bumped = binop('add', f'%{tail}', f'%{produced}')
        else:
            bumped = binop('add', f'%{tail}', 1)
        store(f'%{bumped}', f'%{scalar_p}')

    if ptr:
        e.emit('ret void')
    else:
        reg = load(f'%{ret_p}')
        e.emit(f'ret {ELEM} %{reg}')

    body_text = '\n'.join(e.lines)
    for placeholder, target in replacements.items():
        body_text = body_text.replace(placeholder, target)
    if names:
        body_text = 'entry:\n' + body_text

    header = [
        "; ModuleID = 'mmm.cc'",
        'source_filename = "mmm.cc"',
        'target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-'
        'i64:64-f80:128-n8:16:32:64-S128"',
        'target triple = "x86_64-pc-linux-gnu"',
    ]
    used = []
    if not loop_scalar:
        used += [name for nest_triples in nests for triple in nest_triples for name in triple
                 if name not in pointer_arrays]
    elif straight or sentinel:
        used += [lhs0, rhs0]        # only the prologue, or the sentinel, reads them
    if between:
        used.append(BETWEEN_ARRAY)
    if straight:
        used.append(STRAIGHT_ARRAY)
    if indirect:
        used.append(INDEX_ARRAY)
    for name in used:
        header.append(f'@{name} = dso_local global {type_of(name)} zeroinitializer, align 16')
    if variables:
        # Every trip count is the same, so one global bound serves all.
        header.append(f'@{BOUND_GLOBAL} = dso_local global {ELEM} {rows}, align 4')
    if vstep:
        header.append(f'@{STEP_GLOBAL} = dso_local global {ELEM} 2, align 4')
    if call:
        header.append(f'declare {ELEM} @llvm.smax.i32({ELEM}, {ELEM})')
    params = []
    if param:
        params.append(f'{ELEM} %n')
    params += [f'{ptr_to(DATA)} %{name}' for name in sorted(pointer_arrays)]
    if ptr:
        header.append(f'define dso_local void @kernel({", ".join(params)}) #0 {{')
    elif param:
        header.append(f'define dso_local noundef i32 @kernel({", ".join(params)}) #0 {{')
    else:
        header.append('define dso_local noundef i32 @main() #0 {')

    footer = ['}', 'attributes #0 = { nounwind }']
    text = '\n'.join(header) + '\n' + body_text + '\n' + '\n'.join(footer) + '\n'
    # Labels and registers were numbered as they were reserved, not as
    # they were emitted; LLVM wants them in textual order.
    return renumber(text)


def parse_shape(text: str):
    parts = [int(n) for n in text.split(',')]
    if len(parts) == 1:
        return parts * 3
    if len(parts) != 3:
        raise SystemExit("--shape takes M,N,K")
    return parts


FLAGS = [
    # (option, attribute, help, summary)
    ('--le', 'le', 'test counter <= bound - 1 instead of counter < bound', '<= bounds'),
    ('--minus', 'minus', 'unrolled copies read k - step, k starting at factor - 1', 'negative offsets'),
    ('--while', 'while_loop', 'the innermost loop is a two-block while loop', 'while-shaped inner loop'),
    ('--do', 'do_loop', 'the innermost loop is a single-block do-while loop', 'do-while inner loop'),
    ('--dopre', 'dopre', 'a do-while loop comparing the counter before advancing it', 'do-while comparing first'),
    ('--continue', 'continue_loop', 'the innermost while loop skips odd k with continue', 'continue in the inner loop'),
    ('--sentinel', 'sentinel', 'the innermost loop runs while a[i][k] != 0', 'sentinel-driven inner loop'),
    ('--irreducible', 'irreducible', 'the innermost loop is an irreducible two-block cycle', 'irreducible inner loop'),
    ('--if', 'if_body', 'accumulate only when a[i][k] > 0', 'if in the body'),
    ('--switch', 'switch_body', 'k %% 3 selects add, subtract or nothing', 'switch in the body'),
    ('--copy', 'copy_body', 'the body copies a[i][k] into c[i][j]', 'copy-only body'),
    ('--expr', 'expr', 'read b[(k + j) %% K][j]', 'computed subscript'),
    ('--indirect', 'indirect', 'read b[idx[k]][j]', 'indirect subscript'),
    ('--ptr', 'ptr', 'arrays are pointer parameters indexed flat', 'pointer parameters'),
    ('--variables', 'variables', 'bounds from a global and starts from a local variable', 'variable bounds'),
    ('--vstep', 'vstep', 'the innermost loop steps by a global variable', 'variable step'),
    ('--param', 'param', 'bounds from an integer parameter of the function', 'parameter bound'),
    ('--float', 'float_data', 'the arrays hold doubles', 'floating-point data'),
    ('--call', 'call', 'clamp each product with @llvm.smax.i32', 'intrinsic call'),
    ('--select', 'select', 'clamp each product with a select', 'select'),
    ('--break', 'break_loop', 'a for(;;) inner loop leaving from its latch', 'break-driven inner loop'),
    ('--local', 'local_array', 'stage a[i][k] through a local array', 'local array'),
    ('--sequential', 'sequential', 'two loop nests in sequence sharing the counters', 'two nests in sequence'),
    ('--names', 'names', 'named labels and counter allocas', 'named labels'),
    ('--opaque', 'opaque', 'opaque pointers (ptr) instead of typed ones', 'opaque pointers'),
    ('--between', 'between', 'compute v[i] between the outer and middle loops', 'inter-nest computation'),
    ('--straight', 'straight', 'wrap the loop nest in straight-line code', 'straight-line prologue and epilogue'),
    ('--scalar', 'scalar', 'wrap the nest in scalar-only straight-line code', 'scalar-only prologue and epilogue'),
    ('--loop-scalar', 'loop_scalar', 'the nest accumulates a scalar, touching no array', 'scalar-only nest'),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--size', type=int, default=24, help='array dimension')
    parser.add_argument('--shape', help='M,N,K for c[M][N] = a[M][K] * b[K][N]')
    parser.add_argument('--factor', type=int, default=1,
                        help='inner loop unroll factor')
    parser.add_argument('--start', type=int, default=0,
                        help='initial value of every loop counter')
    parser.add_argument('--products', type=int, default=1,
                        help='independent matrix products in the same nest')
    for option, attribute, help_text, _ in FLAGS:
        parser.add_argument(option, dest=attribute, action='store_true', help=help_text)
    parser.add_argument('--out', required=True, help='file to write')
    args = parser.parse_args()
    if args.factor < 1:
        raise SystemExit("--factor must be at least 1")

    shape = parse_shape(args.shape) if args.shape else [args.size] * 3
    options = {attribute: getattr(args, attribute) for _, attribute, _, _ in FLAGS}
    with open(args.out, 'w') as f:
        f.write(generate(shape, args.factor, args.products, start=args.start, **options))
    extras = [summary for _, attribute, _, summary in FLAGS if getattr(args, attribute)]
    if args.products > 1:
        extras.insert(0, f'{args.products} products')
    if args.start:
        extras.append(f'counters from {args.start}')
    detail = f", {', '.join(extras)}" if extras else ''
    print(f"wrote {args.out}: {'x'.join(str(n) for n in shape)}, "
          f"unrolled {args.factor}x{detail}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
