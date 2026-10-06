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
Check that generated code computes what the source program computed.

The generators split one program in two: the AGU files walk the loop
nest and produce addresses, the datapath file does the arithmetic. Neither
runs on its own, so this script interprets them together and compares the
resulting arrays against interpreting the original IR.

Usage:
    python verify_semantics.py SOURCE.ll OUTPUT_DIR OUTPUT_PREFIX [SEED]

SEED, any word, varies the values the input arrays are filled with, so
a second run takes other data-dependent branches.

Only the instruction subset the front end emits is supported; anything
else raises, rather than being silently skipped.
"""
import collections
import glob
import os
import re
import sys
from utils.IRNormalize import bracket_depth, hoist_constant_geps, leading_type, split_top_level, strip_debug
from utils.Naming import local_array_name, object_name, pointer_object_name, scalar_param_name
from typing import Dict, List, Optional, Tuple


_WRITE_ORDER = __import__('itertools').count()


# What an address program's block leads to once it has run `ret void`.
# It used to be the string 'ret', which is also the label of the
# generators' final block (`br label %ret` ... `ret:` / `ret void`), so
# the branch there was taken for the end and that block never ran.
HALTED = object()


class _Undefined:
    """What an alloca holds before anything is stored to it."""

    def __repr__(self):
        return 'undefined'


UNDEFINED = _Undefined()


class Halt(Exception):
    """Raised by `ret` to stop interpretation; carries (register, value)."""

    def __init__(self, register=None, value=None):
        super().__init__()
        self.register = register
        self.value = value


def literal(token: str):
    """An integer or floating-point literal, in LLVM's spellings."""
    try:
        return int(token)
    except ValueError:
        pass
    if token in ('true', 'false'):
        return token == 'true'
    if token in ('undef', 'poison'):
        return 0
    if token == 'null':
        return ('ptr', 'null', [])
    if token.startswith('0x') and len(token) == 18:
        import struct
        return struct.unpack('>d', bytes.fromhex(token[2:]))[0]
    return float(token)


def _sqrt(a):
    if a < 0:
        raise ValueError(f"sqrt of a negative value ({a}) is a NaN, which the model does not carry")
    return a ** 0.5


# The functions the datapath may call: LLVM intrinsics with a scalar
# result, evaluated here by name. Each entry is (arity, 'int' or
# 'float', function of the arguments and the result's width); integer
# results are reduced to their width and the unsigned ones compare as
# unsigned.
_INTRINSICS = {
    'smax': (2, 'int', lambda a, b, w: max(a, b)),
    'smin': (2, 'int', lambda a, b, w: min(a, b)),
    'umax': (2, 'int', lambda a, b, w: max(unsigned(a, w), unsigned(b, w))),
    'umin': (2, 'int', lambda a, b, w: min(unsigned(a, w), unsigned(b, w))),
    'abs': (2, 'int', lambda a, poison, w: abs(a)),
    'fabs': (1, 'float', lambda a, w: abs(a)),
    'sqrt': (1, 'float', lambda a, w: _sqrt(a)),
    'floor': (1, 'float', lambda a, w: float(int(a // 1))),
    'ceil': (1, 'float', lambda a, w: float(-int(-a // 1))),
    'fmuladd': (3, 'float', lambda a, b, c, w: a * b + c),
    'fma': (3, 'float', lambda a, b, c, w: a * b + c),
    'maxnum': (2, 'float', lambda a, b, w: max(a, b)),
    'minnum': (2, 'float', lambda a, b, w: min(a, b)),
}


# Mixed into every fill value: a second run with another seed takes
# other branches on the data (`if (a[i] > 0)`), which one pattern alone
# might never take.
FILL_SEED = ''


def default_value(name: str, index) -> int:
    """
    The value an unwritten element of an input array holds.

    Declared arrays are `zeroinitializer` in the source, so comparing
    runs of the untouched program would only ever compare zeros; the
    inputs are filled with this pattern instead. An array reached by
    pointer has no declared extent, so it is filled on first read. The
    value is a hash of the array's name and the element's subscripts,
    so no two arrays hold the same values and no shift of the
    subscripts maps an array onto itself: a linear pattern let arrays
    whose names agreed modulo 7 (`a` and `h`) pass for one another, and
    a pointer's array read 7 elements off pass as read in place.
    """
    import zlib
    digest = zlib.crc32(f"{FILL_SEED}:{name}:{list(index)}".encode())
    # A seed starting with `wide` fills from -50..50, so a compare
    # against a literal beyond the small range is taken both ways.
    return digest % 101 - 50 if FILL_SEED.startswith('wide') else digest % 7 - 3


def parse_params(text: str) -> List[Tuple[str, str]]:
    """
    (type, register) of the function's parameters.

    The type is the first token (extended while its brackets are open);
    what follows before the name is attributes such as `noundef`.
    """
    match = re.search(r'^define\b[^(]*?@[-\w.$]+\s*\(', text, re.M)
    params = []
    if match:
        start = match.end() - 1
        depth = 0
        for index in range(start, len(text)):
            if text[index] == '(':
                depth += 1
            elif text[index] == ')':
                depth -= 1
                if depth == 0:
                    break
        parameter_list = text[start + 1:index]
        for param in split_top_level(parameter_list):
            tokens = param.split()
            if len(tokens) < 2 or not tokens[-1].startswith('%'):
                continue
            type_tokens = [tokens[0]]
            depth = bracket_depth(tokens[0])
            k = 1
            while k < len(tokens) - 1 and (depth > 0 or tokens[k].startswith('(')):
                type_tokens.append(tokens[k])
                depth += bracket_depth(tokens[k])
                k += 1
            params.append((' '.join(type_tokens), tokens[-1]))
    return params


def is_pointer_type(type_str: str) -> bool:
    return type_str.endswith('*') or type_str == 'ptr'


def parse_blocks(text: str) -> Tuple[List[str], Dict[str, List[str]]]:
    """Split a function body into ordered basic blocks."""
    order: List[str] = []
    blocks: Dict[str, List[str]] = {}
    # The parser calls an unlabelled first block `entry`; a function
    # whose first block is labelled may use `entry` for a later one.
    current = None
    in_body = False
    pending_switch: Optional[List[str]] = None
    for line in text.splitlines():
        stripped = line.split(';')[0].strip()
        if pending_switch is not None:
            pending_switch.append(stripped)
            if ']' not in stripped:
                continue
            stripped = ' '.join(pending_switch)
            pending_switch = None
        elif stripped.startswith('switch ') and ']' not in stripped:
            pending_switch = [stripped]
            continue
        if stripped.startswith('define '):
            in_body = True
            continue
        if not in_body or not stripped:
            continue
        if stripped == '}':
            break
        stripped = re.sub(r'%"([-\w.$]+)"', r'%\1', stripped)
        label = re.match(r'^(?:"([^"]+)"|([-\w.$]+)):', line)
        if label:
            current = label.group(1) or label.group(2)
            if current not in blocks:
                order.append(current)
                blocks[current] = []
            continue
        if current is None:
            current = 'entry'
            order.append(current)
            blocks[current] = []
        if blocks[current] and is_terminator(blocks[current][-1]):
            # The interpreter ran on past a branch; LLVM would not.
            raise RuntimeError(f"block {current}: {stripped} follows the block's terminator")
        blocks[current].append(stripped)
    return order, blocks


def is_terminator(line: str) -> bool:
    return re.match(r'^(br|switch|ret)\b', line) is not None


def _sdiv(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def width_of(type_str: str) -> Optional[int]:
    """Bits of an integer type; None for anything else."""
    m = re.fullmatch(r'i(\d+)', type_str)
    return int(m.group(1)) if m else None


def wrap(value: int, width: Optional[int]) -> int:
    """An integer reduced to its type's width, in signed form (i1 as 0/1)."""
    if width is None:
        return value
    value %= 1 << width
    if width > 1 and value >= 1 << (width - 1):
        value -= 1 << width
    return value


def unsigned(value: int, width: Optional[int]) -> int:
    return value % (1 << width) if width else value


_INT_BINARY = {
    'add': lambda a, b, w: a + b,
    'sub': lambda a, b, w: a - b,
    'mul': lambda a, b, w: a * b,
    'sdiv': lambda a, b, w: _sdiv(a, b),
    'srem': lambda a, b, w: a - _sdiv(a, b) * b,
    'udiv': lambda a, b, w: unsigned(a, w) // unsigned(b, w),
    'urem': lambda a, b, w: unsigned(a, w) % unsigned(b, w),
    'and': lambda a, b, w: a & b,
    'or': lambda a, b, w: a | b,
    'xor': lambda a, b, w: a ^ b,
    'shl': lambda a, b, w: a << b,
    'ashr': lambda a, b, w: a >> b,
    'lshr': lambda a, b, w: unsigned(a, w) >> b,
}

_FLOAT_BINARY = {
    'fadd': lambda a, b: a + b,
    'fsub': lambda a, b: a - b,
    'fmul': lambda a, b: a * b,
    'fdiv': lambda a, b: a / b,
    'frem': lambda a, b: __import__('math').fmod(a, b),
}

_BINARY = set(_INT_BINARY) | set(_FLOAT_BINARY)

_SIGNED_COMPARE = {
    'slt': lambda a, b: a < b, 'sle': lambda a, b: a <= b,
    'sgt': lambda a, b: a > b, 'sge': lambda a, b: a >= b,
    'eq': lambda a, b: a == b, 'ne': lambda a, b: a != b,
}
_UNSIGNED_COMPARE = {
    'ult': lambda a, b: a < b, 'ule': lambda a, b: a <= b,
    'ugt': lambda a, b: a > b, 'uge': lambda a, b: a >= b,
}
_COMPARE = {**_SIGNED_COMPARE, **_UNSIGNED_COMPARE}

# Floating-point predicates: 'o' ordered (false on NaN), 'u' unordered
# (true on NaN); neither run produces a NaN here.
_FCOMPARE = {
    'oeq': lambda a, b: a == b, 'one': lambda a, b: a != b,
    'olt': lambda a, b: a < b, 'ole': lambda a, b: a <= b,
    'ogt': lambda a, b: a > b, 'oge': lambda a, b: a >= b,
    'ueq': lambda a, b: a == b, 'une': lambda a, b: a != b,
    'ult': lambda a, b: a < b, 'ule': lambda a, b: a <= b,
    'ugt': lambda a, b: a > b, 'uge': lambda a, b: a >= b,
    'ord': lambda a, b: True, 'uno': lambda a, b: False,
    'true': lambda a, b: True, 'false': lambda a, b: False,
}

# (value, from width, to width) -> value
_CASTS = {
    'sext': lambda v, f, t: (-1 if v else 0) if f == 1 else v,
    'zext': lambda v, f, t: unsigned(v, f),
    'trunc': lambda v, f, t: wrap(v, t),
    'fpext': lambda v, f, t: float(v),
    'fptrunc': lambda v, f, t: __import__('struct').unpack('f', __import__('struct').pack('f', float(v)))[0],
    'sitofp': lambda v, f, t: float(v), 'uitofp': lambda v, f, t: float(unsigned(v, f)),
    'fptosi': lambda v, f, t: wrap(int(v), t), 'fptoui': lambda v, f, t: wrap(int(v), t),
}


class Interpreter:
    """
    Interpreter for the LLVM subset the front end produces.

    Memory is modelled as two spaces: scalar allocas and globals keyed by
    name, and arrays keyed by (name, index tuple). A getelementptr yields
    a pointer token, and a chained one appends a subscript. An alloca of
    array type is a local array, an object of its own; a pointer
    parameter is an array whose extent is unknown, filled on first read.

    Each generated program runs in an interpreter of its own, with its
    own registers and its own allocas. A register the program reads but
    does not define -- the datapath reading an AGU's %load_, an AGU
    storing a value the datapath computed or branching on one -- is
    looked up in the other interpreters listed as `fallbacks`.
    """

    def __init__(self, arrays: Dict[str, Dict[Tuple[int, ...], int]], name: str = 'program'):
        self.arrays = arrays
        self.name = name
        self.regs: Dict[str, object] = {}
        # The declared type of every register defined here. An operand
        # used at another type than it was produced with is an error:
        # `mul i32` on a double, `fadd` on integers, a `ugt` on a value
        # compared `sgt` in the source would otherwise evaluate to the
        # same numbers and pass.
        self.types: Dict[str, str] = {}
        self.stack: Dict[str, int] = {}
        self.fallbacks: List['Interpreter'] = []
        self.lazy: set = set()
        # {array: dims} for the declared arrays: an access outside them
        # is an error, not a zero. Both runs used to make the same
        # out-of-range read and agree on it.
        self.shapes: Dict[str, List[int]] = {}
        # The datapath's hand-offs, as (value, AGU address register)
        # pairs: `sent` the ones no AGU program has stored yet, `unsent`
        # the ones an AGU program stored before the datapath sent them
        # (a literal, or a value another AGU program loaded, needs no
        # wait). Both must be empty when a block ends.
        self.sent = collections.Counter()
        self.unsent = collections.Counter()
        self.is_datapath = False
        # Scalar slots this program loaded or stored, and the elements of
        # each array it stored.
        self.touched: set = set()
        self.written: Dict[str, set] = {}
        # The value a `ret` returned, once it has, and the block it was in.
        self.returned = None
        self.returning_block = None
        self.current_block = None
        self.object = None          # the memory object an address program streams
        self.loaded: set = set()    # registers a load defined
        self.counter_regs: set = set()    # registers holding a counter: loads of %i<L>_ptr and their updates
        self.read_keys: Dict[str, set] = {}    # elements read of each pointer parameter's array
        self.agu_objects: set = set()
        # Order in which counter slots (%i<level>_ptr) were last written.
        self.counter_order: Dict[str, int] = {}

    def lookup(self, token: str):
        """The value of a register defined here or in a fallback, else None."""
        if token in self.regs:
            return self.regs[token]
        for other in self.fallbacks:
            if token in other.regs and (other.is_datapath or self.is_datapath
                                        or (token.startswith('%load_') and token in other.loaded)):
                # An address program shares with the others only what it
                # loaded (%load_...): its counters are its own, so a
                # program that dropped its %i3 cannot borrow another's,
                # nor one laundered through a register merely named
                # %load_. A load is read in the block that loaded it: a
                # value carried into a later block is a hoisted load,
                # which the model forbids (and which is only ever wrong
                # when the data happens to change).
                if token.startswith('%load_') and other.object is not None \
                        and not other.in_stream(token, '%load_'):
                    raise RuntimeError(
                        f"{self.name}: reads {token} in block {self.current_block}, not the block "
                        f"that loaded it")
                return other.regs[token]
        return None

    def value(self, token: str):
        token = token.rstrip(',')
        if token.startswith('%'):
            found = self.lookup(token)
            if found is None:
                raise KeyError(f"{self.name}: undefined register {token}")
            return found
        return literal(token)

    def type_of(self, token: str) -> Optional[str]:
        """The declared type of a register, here or in a fallback."""
        for interp in [self] + self.fallbacks:
            if token in interp.types:
                return interp.types[token]
        return None

    def typed(self, token: str, declared: str, line: str):
        """The value of an operand, checked against the type it is used at."""
        token = token.rstrip(',')
        if token.startswith('%'):
            produced = self.type_of(token)
            if produced is not None and produced != declared:
                raise RuntimeError(
                    f"{self.name}: {token} is a {produced} but is used as {declared}: {line}")
            return self.value(token)
        value = self.value(token)
        if token not in ('true', 'false', 'undef', 'poison', 'null'):
            width = width_of(declared)
            if width is not None and isinstance(value, float):
                raise RuntimeError(f"{self.name}: {token} is not an integer literal for {declared}: {line}")
            if width is None and declared in ('double', 'float') and isinstance(value, int):
                raise RuntimeError(f"{self.name}: {token} is not a floating-point literal for {declared}: {line}")
        return value

    def define(self, reg: str, type_str: str, value) -> None:
        self.regs[reg] = value
        self.types[reg] = type_str

    @staticmethod
    def element_key(ptr) -> tuple:
        """The subscripts an address names; a bare pointer is element 0."""
        key = tuple(ptr[2])
        return key if key or ptr[0] != 'ptr' else (0,)

    def in_range(self, ptr) -> None:
        dims = self.shapes.get(ptr[1])
        if dims is None:
            return
        key = self.element_key(ptr)
        if len(key) != len(dims) or any(not 0 <= k < n for k, n in zip(key, dims)):
            raise RuntimeError(
                f"{self.name}: {ptr[1]}{list(key)} is outside the declared {dims}")

    def owns_no_memory(self, ptr) -> None:
        """
        The datapath owns scalars only: every array element it needs is
        loaded by an address program (received) or stored by one (sent).
        A load or store through an address it computed itself would read
        or write memory at its own timing, bypassing the address units.
        """
        if self.is_datapath and isinstance(ptr, tuple):
            raise RuntimeError(
                f"{self.name}: the datapath addresses {ptr[1]}{list(ptr[2])} itself; only the "
                f"address programs read and write memory objects")

    def own_object(self, ptr) -> None:
        """
        An address program streams one memory object, the one it is
        named after; a load or store on another is another program's
        work done at the wrong time, and used to pass.
        """
        if self.object is not None and ptr[1] != self.object:
            raise RuntimeError(
                f"{self.name}: addresses {ptr[1]}{list(ptr[2])}, an object it does not stream")

    def streamed_elsewhere(self, ptr) -> None:
        """A scalar an address program streams is not the datapath's to touch."""
        if self.is_datapath and isinstance(ptr, str) and ptr.startswith('@') and ptr[1:] in self.agu_objects:
            raise RuntimeError(
                f"{self.name}: the datapath touches {ptr}, which an address program streams")

    def read(self, ptr):
        self.owns_no_memory(ptr)
        self.streamed_elsewhere(ptr)
        if not isinstance(ptr, tuple):
            self.touched.add(ptr)
        if isinstance(ptr, tuple) and ptr[0] in ('array', 'ptr'):
            self.own_object(ptr)
            self.in_range(ptr)
            elements = self.arrays.setdefault(ptr[1], {})
            key = self.element_key(ptr)
            if ptr[1] in self.lazy:
                self.read_keys.setdefault(ptr[1], set()).add(key)
            if key not in elements and ptr[1] in self.lazy:
                elements[key] = default_value(ptr[1], key)
            return elements.get(key, 0)
        # A slot holds nothing until it is stored: a dropped
        # initialisation used to read as 0 on both sides.
        value = self.stack.get(ptr, UNDEFINED if ptr.startswith('%') else 0)
        if value is UNDEFINED:
            raise RuntimeError(f"{self.name}: reads {ptr} before anything is stored to it")
        return value

    def write(self, ptr, val):
        self.owns_no_memory(ptr)
        self.streamed_elsewhere(ptr)
        if not isinstance(ptr, tuple):
            self.touched.add(ptr)
            if re.fullmatch(r'%i\d+_ptr', ptr):
                self.counter_order[ptr] = next(_WRITE_ORDER)
        if isinstance(ptr, tuple) and ptr[0] in ('array', 'ptr'):
            self.own_object(ptr)
            self.in_range(ptr)
            self.written.setdefault(ptr[1], set()).add(self.element_key(ptr))
            self.arrays.setdefault(ptr[1], {})[self.element_key(ptr)] = val
        else:
            self.stack[ptr] = val

    def in_stream(self, name: str, prefix: str) -> bool:
        """
        Whether an address program's stream register -- `%gep_<object>_
        <block>_<stream>`, or `%load_...` with a load's ordinal after --
        names this program's object and the block being run. The front
        end refuses names where the split is ambiguous.
        """
        tail = name[len(prefix):]
        head = f"{self.object}_{self.current_block}_"
        return tail.startswith(head) and re.fullmatch(r'\d+(?:_\d+)?', tail[len(head):]) is not None

    def pointer(self, token: str):
        """A pointer operand: a register holding an address, or a slot."""
        found = self.lookup(token)
        return token if found is None else found

    def received(self, line: str) -> Optional[str]:
        """The register a `receive` pseudo-instruction takes, or None."""
        m = re.match(r'^(%[-\w.$]+)\s*=\s*receive\s+(\S+)$', line)
        return m.group(1) if m else None

    def can_run(self, line: str) -> bool:
        """Whether every register the instruction reads is available."""
        received = self.received(line)
        if received is not None:
            return any(received in other.regs for other in self.fallbacks)
        # An AGU store of a value the datapath computed waits for the
        # datapath to send that value through this very address: a
        # datapath store that is missing, or through the wrong address,
        # leaves the AGU's store waiting.
        m = re.match(r'^store\s+.*\s(%[-\w.$]+),.*\s(%gep_[-\w.$]+)', line)
        if m and not self.is_datapath and m.group(1) not in self.regs:
            for other in self.fallbacks:
                if other.is_datapath and m.group(1) in other.regs:
                    if not other.sent[(m.group(1), m.group(2))]:
                        return False
        body = line.split('=', 1)[1] if re.match(r'^%[-\w.$]+\s*=', line) else line
        body = re.sub(r'label\s+%[-\w.$]+', '', body)
        for token in re.findall(r'%[-\w.$]+', body):
            if token in self.stack or self.lookup(token) is not None:
                continue
            return False
        return True

    def execute(self, line: str) -> Optional[str]:
        """Run one instruction. Returns a branch target, or None."""
        received = self.received(line)
        if received is not None:
            # The datapath's `%load_x = load ...` line stands for taking
            # the value the AGU program loaded under that name; reading
            # memory again here could see a later store.
            declared = line.split()[-1]
            for other in self.fallbacks:
                if received in other.regs:
                    if received not in other.loaded or not other.in_stream(received, '%load_'):
                        raise RuntimeError(
                            f"{self.name}: receives {received} in block {self.current_block}, "
                            f"which is not what an address program loaded there")
                    self.regs[received] = other.regs[received]
                    if received in other.types:
                        if other.types[received] != declared:
                            raise RuntimeError(
                                f"{self.name}: {received} is received as {declared} but the AGU "
                                f"loaded a {other.types[received]}")
                        self.types[received] = other.types[received]
                    return None
            raise KeyError(f"{self.name}: nothing provides {received}")

        m = re.match(r'^send\s+(\S+)\s+(\S+)\s+(%gep_[-\w.$]+)$', line)
        if m:
            # The datapath's store through an AGU address: the value is
            # handed to the AGU program, which performs the store. Writing
            # memory here as well let a missing store on either side pass;
            # the pair is recorded so the AGU's store can be matched to it.
            self.typed(m.group(2), m.group(1), line)
            value = m.group(2)
            if value.startswith('%') and value not in self.regs and not any(
                    (value in other.loaded and other.in_stream(value, '%load_')) or value in other.counter_regs
                    for other in self.fallbacks):
                raise RuntimeError(
                    f"{self.name}: sends {value}, which neither it nor an address program's load or "
                    f"counter defines: {line}")
            pair = (m.group(2), m.group(3))
            if self.unsent[pair]:
                self.unsent[pair] -= 1
            else:
                self.sent[pair] += 1
            return None

        m = re.match(r'^(%[-\w.$]+)\s*=\s*alloca\s+(\[.*\])\s*(?:,|$)', line)
        if m:
            self.regs[m.group(1)] = ('array', local_array_name(m.group(1)), [])
            # A local array has an extent too.
            self.shapes.setdefault(local_array_name(m.group(1)),
                                   [int(n) for n in re.findall(r'\[(\d+) x', m.group(2))])
            return None

        m = re.match(r'^(%[-\w.$]+)\s*=\s*alloca\b', line)
        if m:
            self.stack.setdefault(m.group(1), UNDEFINED)
            return None

        m = re.match(r'^store\s+(?:volatile\s+)?(.*)$', line)
        if m:
            parts = split_top_level(m.group(1))
            type_str, value = leading_type(parts[0]), parts[0].split()[-1]
            ptr = parts[1].split()[-1]
            address = self.pointer(ptr)
            if self.object is not None and isinstance(address, tuple):
                # An address program stores an element through its stream
                # address, in the stream's block, and stores what the
                # datapath sent (or a counter, a literal, its own load):
                # a value it computed itself is the datapath's work.
                if not ptr.startswith('%gep_'):
                    raise RuntimeError(
                        f"{self.name}: stores through {ptr}, which is not a stream address: {line}")
                if not self.in_stream(ptr, '%gep_'):
                    raise RuntimeError(
                        f"{self.name}: stores through {ptr} in block {self.current_block}: {line}")
                if value in self.regs and value not in self.counter_regs \
                        and not (value.startswith('%load_') and value in self.loaded):
                    raise RuntimeError(
                        f"{self.name}: stores {value}, a value it computed itself: {line}")
            self.write(address, self.typed(value, type_str, line))
            if not self.is_datapath and ptr.startswith('%gep_'):
                pair = (value, ptr)
                for other in self.fallbacks:
                    if other.is_datapath:
                        if other.sent[pair]:
                            other.sent[pair] -= 1
                        else:
                            other.unsent[pair] += 1
            return None

        m = re.match(r'^(%[-\w.$]+)\s*=\s*load\s+(?:volatile\s+)?(.*)$', line)
        if m:
            parts = split_top_level(m.group(2))
            ptr = parts[1].split()[-1]
            address = self.pointer(ptr)
            if self.object is not None and isinstance(address, tuple):
                if not ptr.startswith('%gep_') or not m.group(1).startswith('%load_'):
                    raise RuntimeError(
                        f"{self.name}: an element is loaded other than through a stream "
                        f"address into a %load_ register: {line}")
                if not self.in_stream(ptr, '%gep_') or not self.in_stream(m.group(1), '%load_'):
                    raise RuntimeError(
                        f"{self.name}: loads through {ptr} in block {self.current_block}: {line}")
            self.define(m.group(1), parts[0].strip(), self.read(address))
            self.loaded.add(m.group(1))
            if re.fullmatch(r'%i\d+_ptr', ptr):
                self.counter_regs.add(m.group(1))
            return None

        m = re.match(r'^(%[-\w.$]+)\s*=\s*icmp\s+(?:samesign\s+)?(\w+)\s+(\S+)\s+(\S+?),\s*(\S+)', line)
        if m:
            op, type_str = m.group(2), m.group(3)
            lhs, rhs = self.typed(m.group(4), type_str, line), self.typed(m.group(5), type_str, line)
            if op in _UNSIGNED_COMPARE:
                width = width_of(type_str)
                lhs, rhs = unsigned(lhs, width), unsigned(rhs, width)
            elif op not in _SIGNED_COMPARE:
                raise NotImplementedError(f"icmp {op}")
            self.define(m.group(1), 'i1', _COMPARE[op](lhs, rhs))
            return None

        m = re.match(r'^(%[-\w.$]+)\s*=\s*fcmp\s+(?:fast\s+|nnan\s+|ninf\s+|nsz\s+|arcp\s+|contract\s+|afn\s+|reassoc\s+)*(\w+)\s+(\S+)\s+(\S+?),\s*(\S+)', line)
        if m:
            type_str = m.group(3)
            lhs, rhs = self.typed(m.group(4), type_str, line), self.typed(m.group(5), type_str, line)
            if m.group(2) not in _FCOMPARE:
                raise NotImplementedError(f"fcmp {m.group(2)}")
            self.define(m.group(1), 'i1', _FCOMPARE[m.group(2)](lhs, rhs))
            return None

        m = re.match(r'^(%[-\w.$]+)\s*=\s*(\w+)\s+(?:nsw\s+|nuw\s+|exact\s+|disjoint\s+|nneg\s+|fast\s+|nnan\s+|ninf\s+|nsz\s+|contract\s+|reassoc\s+|arcp\s+|afn\s+)*(\S+)\s+(\S+?),\s*(\S+)$', line)
        if m and m.group(2) in _BINARY:
            op, type_str = m.group(2), m.group(3)
            lhs, rhs = self.typed(m.group(4), type_str, line), self.typed(m.group(5), type_str, line)
            if op in _FLOAT_BINARY:
                if width_of(type_str) is not None:
                    raise RuntimeError(f"{self.name}: {op} on an integer type: {line}")
                result = _FLOAT_BINARY[op](float(lhs), float(rhs))
            else:
                width = width_of(type_str)
                if width is None:
                    raise RuntimeError(f"{self.name}: {op} on a non-integer type: {line}")
                result = wrap(_INT_BINARY[op](lhs, rhs, width), width)
            self.define(m.group(1), type_str, result)
            if re.fullmatch(r'%i\d+_next(?:_[-\w.$]*)?', m.group(1)) \
                    and (m.group(4) in self.counter_regs or m.group(5) in self.counter_regs):
                self.counter_regs.add(m.group(1))
            return None

        m = re.match(r'^(%[-\w.$]+)\s*=\s*(\w+)\s+(?:nneg\s+)?(\S+)\s+(\S+)\s+to\s+(\S+)', line)
        if m and m.group(2) in _CASTS:
            source, target = m.group(3), m.group(5)
            value = self.typed(m.group(4), source, line)
            self.define(m.group(1), target,
                        _CASTS[m.group(2)](value, width_of(source), width_of(target)))
            return None

        m = re.match(r'^(%[-\w.$]+)\s*=\s*fneg\s+(?:(?:fast|nnan|ninf|nsz|arcp|contract|afn|reassoc)\s+)*(\S+)\s+(\S+)$', line)
        if m:
            if width_of(m.group(2)) is not None:
                raise RuntimeError(f"{self.name}: fneg on an integer type: {line}")
            self.define(m.group(1), m.group(2), -float(self.typed(m.group(3), m.group(2), line)))
            return None

        m = re.match(r'^(%[-\w.$]+)\s*=\s*select\s+i1\s+(\S+?),\s*(\S+)\s+(\S+?),\s*\S+\s+(\S+)$', line)
        if m:
            chosen = m.group(4) if self.typed(m.group(2), 'i1', line) else m.group(5)
            self.define(m.group(1), m.group(3), self.typed(chosen, m.group(3), line))
            return None

        m = re.match(r'^(%[-\w.$]+)\s*=\s*(?:(?:tail|musttail|notail)\s+)?call\s+(?:[^@(]*\s)?(\S+)\s+(@[-\w.$]+)\s*\((.*)\)', line)
        if m:
            name = m.group(3).lstrip('@')
            base = name.split('.')[1] if name.startswith('llvm.') else name
            if base not in _INTRINSICS:
                raise NotImplementedError(f"{self.name}: call to unknown function {m.group(3)}")
            arity, kind, function = _INTRINSICS[base]
            args = []
            for token in m.group(4).split(','):
                if token.strip():
                    parts = token.split()
                    args.append(self.typed(parts[-1], parts[0], line))
            if len(args) != arity:
                raise RuntimeError(f"{self.name}: {m.group(3)} takes {arity} arguments: {line}")
            width = width_of(m.group(2))
            if (kind == 'int') != (width is not None):
                raise RuntimeError(f"{self.name}: {m.group(3)} does not return {m.group(2)}: {line}")
            result = function(*args, width)
            self.define(m.group(1), m.group(2), wrap(result, width) if width else float(result))
            return None

        m = re.match(r'^(%[-\w.$]+)\s*=\s*getelementptr\s+(?:(?:inbounds|nuw|nusw)\s+)*(.*)$', line)
        if m:
            parts = split_top_level(m.group(2))
            source_type = parts[0].strip()
            base_token = parts[1].split()[-1]
            subs = []
            for part in parts[2:]:
                index_type, token = part.split()[0], part.split()[-1]
                if width_of(index_type) is None:
                    raise RuntimeError(f"{self.name}: a subscript must be an integer: {line}")
                subs.append(self.typed(token, index_type, line))
            if base_token.startswith('@'):
                base = ('array', base_token[1:], [])
            else:
                base = self.value(base_token)
            if self.object is not None and m.group(1).startswith('%gep_'):
                if not self.in_stream(m.group(1), '%gep_'):
                    raise RuntimeError(
                        f"{self.name}: {m.group(1)} is defined in block {self.current_block}: {line}")
            existing = list(base[2])
            if existing:
                # The first index is pointer arithmetic along the last
                # subscript, whatever the address points at: `p + 2` then
                # `[3]` is element 5, not (2, 3); a[1] + i is a[1][i]; a row
                # pointer plus i is row i further on (`*(*(m + i) + j)`).
                # Dropping it whenever the type was an array read the
                # latter as row 0.
                existing[-1] += subs[0]
                subs = subs[1:]
            elif base[0] == 'ptr':
                # A pointer parameter: the pointer itself is the first
                # subscript (`int (*a)[24]` steps rows first), so every
                # index counts.
                pass
            elif source_type.startswith('['):
                # The address of a whole array: the leading index counts
                # whole arrays and must be 0 to stay inside this one.
                if subs and subs[0] != 0:
                    raise RuntimeError(
                        f"{self.name}: the leading subscript {subs[0]} steps past {base[1]}: {line}")
                subs = subs[1:]
            elif base_token.startswith('@') and subs == [0] and base_token[1:] not in self.shapes:
                subs = []		# a scalar object: `@s, i64 0` is the object itself
            self.regs[m.group(1)] = (base[0], base[1], existing + subs)
            return None

        m = re.match(r'^br\s+i1\s+(\S+?),\s*label\s+%([-\w.$]+),\s*label\s+%([-\w.$]+)', line)
        if m:
            return m.group(2) if self.typed(m.group(1), 'i1', line) else m.group(3)

        m = re.match(r'^br\s+label\s+%([-\w.$]+)', line)
        if m:
            return m.group(1)

        m = re.match(r'^switch\s+\S+\s+(\S+?),\s*label\s+%([-\w.$]+)\s*\[(.*)\]', line)
        if m:
            value = self.value(m.group(1))
            for token, label in re.findall(r'\S+\s+(\S+),\s*label\s+%([-\w.$]+)', m.group(3)):
                if literal(token) == value:
                    return label
            return m.group(2)

        m = re.match(r'^ret\s+(\S+)\s+(\S+)$', line)
        if m:
            value = self.typed(m.group(2), m.group(1), line)
            if self.is_datapath:
                # The datapath returns the function's result; the address
                # programs go on to their own `ret void`. Returning twice
                # (a `ret` in a block that runs again) is an error.
                if self.returned is not None:
                    raise RuntimeError(f"{self.name}: returns more than once: {line}")
                self.returned = (m.group(2), value)
                self.returning_block = self.current_block
                return None
            raise Halt(m.group(2), value)
        if line.startswith('ret'):
            if self.is_datapath:
                if self.returned is not None:
                    raise RuntimeError(f"{self.name}: returns more than once: {line}")
                self.returned = (None, None)
                self.returning_block = self.current_block
                return None
            raise Halt()

        raise NotImplementedError(f"{self.name}: {line}")


def run_source(path: str, arrays, initial: Dict[str, int], lazy: set, shapes) -> Dict[str, int]:
    """Interpret the original program; returns its scalar slots."""
    text = hoist_constant_geps(strip_debug(open(path).read()))
    order, blocks = parse_blocks(text)
    interp = Interpreter(arrays, os.path.basename(path))
    interp.stack.update(initial)
    interp.lazy = lazy
    interp.shapes = shapes
    for type_str, reg in parse_params(text):
        if is_pointer_type(type_str):
            interp.regs[reg] = ('ptr', pointer_object_name(reg), [])
        else:
            interp.regs[reg] = initial['@' + scalar_param_name(reg)]
    block, steps = order[0], 0
    try:
        while True:
            steps += 1
            if steps > 50_000_000:
                raise RuntimeError("source did not terminate")
            target = None
            for line in blocks[block]:
                target = interp.execute(line)
                if target:
                    break
            if target is None:
                raise RuntimeError(f"block {block} falls through")
            block = target
    except Halt as halt:
        interp.returned = (halt.register, halt.value)
    return interp


def run_generated(out_dir: str, prefix: str, arrays, initial: Dict[str, int], lazy: set,
                  shapes) -> Dict[str, int]:
    """
    Interpret the AGU programs and the datapath together.

    Within a block, every instruction runs as soon as the registers it
    reads are available: the AGUs' address computations and loads first,
    then the datapath's arithmetic, then whatever waited for it -- the
    stores of computed values, a branch on a computed condition, a
    counter initialised from a computed value. Each AGU program keeps
    its own instruction order. Afterwards every AGU program must have
    chosen the same next block: they are meant to run in lockstep, so a
    program that leaves a loop early or late is an error even if the
    arrays happen to come out right.
    """
    agu_files = sorted(glob.glob(os.path.join(out_dir, f'{prefix}_*_agu.ll')))
    if not agu_files:
        raise RuntimeError(f"no AGU programs in {out_dir}")

    programs = []
    agu_objects = {os.path.basename(path)[len(prefix) + 1:-len('_agu.ll')] for path in agu_files}
    for path in agu_files:
        name = os.path.basename(path)
        order, blocks = parse_blocks(open(path).read())
        interp = Interpreter(arrays, name)
        interp.lazy = lazy
        interp.shapes = shapes
        interp.object = name[len(prefix) + 1:-len('_agu.ll')]
        programs.append((name, order, blocks, interp))

    first_name, order, first_blocks, _ = programs[0]
    for name, _, blocks, _ in programs[1:]:
        if set(blocks) != set(first_blocks):
            raise RuntimeError(
                f"{first_name} and {name} do not have the same blocks: "
                f"{sorted(set(blocks) ^ set(first_blocks))}")

    # Datapath instructions, grouped by block. The file has no labels: it
    # emits one group per block, introduced by a '; block' comment.
    # Instructions before the first comment are the datapath's own
    # preamble: the scalar slots it declares. They run once, up front.
    datapath: Dict[str, List[str]] = {}
    preamble: List[str] = []
    current = None
    counters: set = set()
    counter_levels: Dict[str, List[str]] = {}
    declared: set = set()
    for line in open(os.path.join(out_dir, f'{prefix}_datapath.ll')):
        line = line.strip()
        if not line:
            continue
        label = re.match(r'^;\s*block\s+(\S+)', line)
        if label:
            current = label.group(1)
            continue
        counter = re.match(r'^;\s*counter\s+(\S+)\s*=\s*%i(\d+)\s*$', line)
        if counter:
            counters.add(counter.group(1))
            counter_levels.setdefault(counter.group(1), []).append(counter.group(2))
            continue
        owned = re.match(r'^([%@][-\w.$]+)\s*=\s*(?:alloca|external global)\b', line)
        if owned:
            declared.add(owned.group(1))
        if line.startswith(';') or re.match(r'^@[-\w.$]+\s*=\s*external\b', line):
            continue
        line = line.split(';')[0].strip()
        if current is None:
            preamble.append(line)
        else:
            # A load under an AGU's %load_ name receives that value; a
            # store through an AGU's %gep_ address sends one.
            m = re.match(r'^(%load_[-\w.$]+)\s*=\s*load\s+([^,]+),', line)
            if m:
                line = f"{m.group(1)} = receive {m.group(2).strip()}"
            elif re.match(r'^%[-\w.$]+\s*=\s*load\b.*\s%gep_[-\w.$]+', line):
                # A load through an AGU address under another name would
                # read memory at the datapath's own timing.
                raise RuntimeError(
                    f"the datapath reads memory the address units own, under a name that is "
                    f"not the address unit's %load_ register: {line}")
            m = re.match(r'^store\s+(\S+)\s+(\S+?),\s*\S+\s+(%gep_[-\w.$]+)', line)
            if m:
                line = f"send {m.group(1)} {m.group(2)} {m.group(3)}"
            group = datapath.setdefault(current, [])
            if group and is_terminator(group[-1]):
                raise RuntimeError(f"the datapath's group for block {current}: {line} follows its ret")
            group.append(line)

    unknown = sorted(set(datapath) - set(first_blocks))
    if unknown:
        raise RuntimeError(f"the datapath has groups for blocks no AGU program has: {unknown}")

    dp = Interpreter(arrays, f'{prefix}_datapath.ll')
    dp.stack.update(initial)
    dp.lazy = lazy
    dp.shapes = shapes
    dp.is_datapath = True
    dp.agu_objects = agu_objects
    agu_interps = [interp for _, _, _, interp in programs]
    for interp in agu_interps:
        interp.fallbacks = [other for other in agu_interps if other is not interp] + [dp]
    dp.fallbacks = agu_interps

    for line in preamble:
        dp.execute(line)

    # The registers each program defines in each block. Before a block
    # runs, those are forgotten, so an instruction cannot go ahead on a
    # value left over from the previous iteration: a store of a datapath
    # result, or a compare against another program's load, has to wait
    # until this iteration's value exists.
    def defined_in(lines: List[str]):
        return [m.group(1) for line in lines
                for m in [re.match(r'^(%[-\w.$]+)\s*=', line)] if m]

    defined = {name: {block_id: defined_in(lines) for block_id, lines in blocks.items()}
               for name, _, blocks, _ in programs}
    dp_defined = {block_id: defined_in(lines) for block_id, lines in datapath.items()}

    # The datapath runs like the AGU programs: one instruction at a time,
    # in its own order, each as soon as its operands exist. Running it as
    # a unit could not express a subscript that depends on a value it
    # computes, or a scalar it reads, advances and reads again.
    runners = [(name, blocks, interp) for name, _, blocks, interp in programs]
    runners.append(('datapath', datapath, dp))

    def is_memory(line: str) -> bool:
        return re.match(r'^(store\b|%[-\w.$]+\s*=\s*load\b)', line) is not None

    def run_ready(pending, targets) -> None:
        """
        Run every instruction whose operands are available.

        An AGU program keeps its order. The datapath is a dataflow
        graph: any of its instructions may go as soon as its operands
        exist, except that its own loads and stores keep their order.
        """
        progress = True
        while progress:
            progress = False
            for name, _, interp in runners:
                queue = pending[name]
                if name == 'datapath':
                    index = 0
                    while index < len(queue):
                        line = queue[index]
                        first_memory = next((i for i, l in enumerate(queue) if is_memory(l)), None)
                        ordered = not is_memory(line) or index == first_memory
                        if ordered and interp.can_run(line):
                            queue.pop(index)
                            interp.execute(line)
                            progress = True
                            index = 0
                        else:
                            index += 1
                    continue
                while queue and interp.can_run(queue[0]):
                    line = queue.pop(0)
                    progress = True
                    try:
                        result = interp.execute(line)
                    except Halt:
                        targets[name] = HALTED
                        queue.clear()
                        break
                    if result:
                        targets[name] = result

    block, steps, came_from = order[0], 0, None
    while True:
        steps += 1
        if steps > 50_000_000:
            raise RuntimeError("generated code did not terminate")

        for name, _, _, interp in programs:
            for reg in defined[name].get(block, []):
                interp.regs.pop(reg, None)
            interp.current_block = block
        for reg in dp_defined.get(block, []):
            dp.regs.pop(reg, None)
        # A load is received in the block that loaded it and read there:
        # one kept from an earlier block would be a hoisted load.
        for reg in [reg for reg in dp.regs if reg.startswith('%load_')]:
            dp.regs.pop(reg)
        dp.current_block = block

        pending = {name: list(blocks.get(block, [])) for name, blocks, _ in runners}
        targets: Dict[str, object] = {name: None for name, _, _, _ in programs}
        run_ready(pending, targets)
        stuck = {name: queue[0] for name, queue in pending.items() if queue}
        if stuck:
            raise RuntimeError(f"block {block}: instructions wait on registers nobody defines: {stuck}")
        if +dp.sent:
            raise RuntimeError(
                f"block {block}: the datapath sent values no AGU program stored: {sorted(+dp.sent)}")
        if +dp.unsent:
            raise RuntimeError(
                f"block {block}: AGU programs stored values the datapath never sent: {sorted(+dp.unsent)}")

        if len(set(targets.values())) != 1:
            raise RuntimeError(f"AGU programs diverge after block {block}: {targets}")
        target = next(iter(targets.values()))
        if target is None:
            raise RuntimeError(f"block {block} has no terminator")
        if target is HALTED:
            # The generators end every address program with an epilogue
            # block, `ret:`, entered from the block that returns; the
            # datapath returns in that block, which has the source's ret.
            ended_from = came_from if block == 'ret' and came_from is not None else block
            if dp.returned is None:
                raise RuntimeError(
                    f"the programs end from block {ended_from}, but the datapath never returns "
                    f"(its group with the ret did not run)")
            if dp.returning_block != ended_from:
                raise RuntimeError(
                    f"the datapath returned from block {dp.returning_block}, but the programs "
                    f"end from block {ended_from}")
            dp.counters, dp.declared = counters, declared
            dp.agu_objects = agu_objects
            dp.all_written = {}
            for _, _, _, interp in programs:
                for name, keys in interp.written.items():
                    dp.all_written.setdefault(name, set()).update(keys)
            dp.counter_levels = counter_levels
            dp.agu_stacks = [(interp.stack, interp.counter_order) for _, _, _, interp in programs]
            dp.agu_read_keys = [interp.read_keys for _, _, _, interp in programs]
            return dp
        came_from, block = block, target


def array_shapes(source_text: str) -> Dict[str, List[int]]:
    """Dimensions of each global array, from its declaration."""
    shapes = {}
    for name, decl in re.findall(r'^@([-\w.$]+)\s*=[^\n]*?((?:\[\d+ x )+)', source_text, re.M):
        shapes[name] = [int(n) for n in re.findall(r'\[(\d+) x', decl)]
    return shapes


def scalar_initializers(source_text: str) -> Dict[str, int]:
    """
    Initial values of the global scalars, keyed '@name', and of the
    function's scalar parameters, keyed '@arg_<name>': the nth scalar
    parameter is called with 20 + n, a value any of the test programs'
    bounds and steps make sense for.
    """
    values = {}
    for name, value in re.findall(r'^@([-\w.$]+)\s*=[^\n]*?\b(?:global|constant)\s+(?:i\d+|float|double)\s+(\S+)',
                                  source_text, re.M):
        values['@' + name] = literal(value.rstrip(','))
    # `extern const int K;` declares a scalar whose value is another
    # module's: it gets a fill value, like an input array.
    for name in re.findall(r'^@([-\w.$]+)\s*=[^\n]*?\bexternal\b[^\n]*?\b(?:global|constant)\s+(?:i\d+|float|double)\s*(?:,|$)',
                           source_text, re.M):
        values.setdefault('@' + name, default_value(name, ()))
    position = 0
    for type_str, reg in parse_params(source_text):
        if not is_pointer_type(type_str):
            values['@' + scalar_param_name(reg)] = 20 + position
            position += 1
    return values


def seed(arrays, shapes, initializers=None) -> None:
    """
    Fill the declared inputs with the fixed non-trivial pattern, then
    with their initialisers where the source gives some.
    """
    import itertools
    for name, dims in shapes.items():
        if not dims:
            continue
        for index in itertools.product(*(range(n) for n in dims)):
            arrays[name][index] = default_value(name, index)
    for name, values in (initializers or {}).items():
        arrays.setdefault(name, {}).update(values)


def array_initializers(source_text: str) -> Dict[str, Dict[tuple, object]]:
    """
    {array: {index: value}} for every global array with an explicit
    initialiser (`[4 x i32] [i32 1, i32 2, i32 3, i32 4]`, nested for
    more dimensions; `zeroinitializer` parts stay at zero).
    """
    found: Dict[str, Dict[tuple, object]] = {}
    for line in source_text.splitlines():
        m = re.match(r'^@([-\w.$]+)\s*=[^\n]*?\b(?:global|constant)\s+(\[.*)$', line)
        if not m:
            continue
        rest = m.group(2)
        type_str = leading_type(rest)
        body = rest[len(type_str):].strip()
        values: Dict[tuple, object] = {}
        dims = [int(n) for n in re.findall(r'\[(\d+) x', type_str)]
        if body.startswith('c"'):
            _read_string(body, (), values)
        elif body.startswith('['):
            if 'getelementptr' in body:
                raise NotImplementedError(
                    f"@{m.group(1)}: an initialiser holding an address (a constant getelementptr) "
                    f"is not a value the model carries")
            _read_aggregate(body[:_matching(body, 0) + 1], (), dims, values)
        else:
            continue
        found[m.group(1)] = values
    return found


def _read_string(text: str, prefix: tuple, values: Dict[tuple, object]) -> None:
    """The bytes of a `c"..."` initialiser, `\\xx` escapes decoded."""
    body = text[2:text.index('"', 2)]
    position = 0
    index = 0
    while index < len(body):
        if body[index] == '\\' and body[index + 1:index + 2] == '\\':
            value, index = ord('\\'), index + 2
        elif body[index] == '\\':
            value = int(body[index + 1:index + 3], 16)
            index += 3
        else:
            value = ord(body[index])
            index += 1
        values[prefix + (position,)] = wrap(value, 8)
        position += 1


def _zero_fill(prefix: tuple, dims: List[int], values: Dict[tuple, object]) -> None:
    import itertools
    for index in itertools.product(*(range(n) for n in dims)):
        values[prefix + index] = 0


def _matching(text: str, start: int) -> int:
    """Index of the bracket closing the one at `start`."""
    depth = 0
    for index in range(start, len(text)):
        if text[index] == '[':
            depth += 1
        elif text[index] == ']':
            depth -= 1
            if depth == 0:
                return index
    raise ValueError(f"unbalanced initialiser: {text}")


def _read_aggregate(text: str, prefix: tuple, dims: List[int], values: Dict[tuple, object]) -> None:
    """
    Record every scalar of a `[e0, e1, ...]` initialiser under prefix + (i,);
    a `zeroinitializer` part is written out as zeros, not left to the
    pattern.
    """
    for position, element in enumerate(split_top_level(text[1:-1])):
        element = element.strip()
        body = element[len(leading_type(element)):].strip() if element.startswith('[') else element
        if body == 'zeroinitializer' or element == 'zeroinitializer':
            _zero_fill(prefix + (position,), dims[1:], values)
        elif element.startswith('['):
            # A nested row: `[2 x i32] [i32 1, i32 2]` -- its own initialiser
            # is the bracket group after its type.
            inner_type = leading_type(element)
            inner = element[len(inner_type):].strip()
            if inner.startswith('c"'):
                _read_string(inner, prefix + (position,), values)
            else:
                _read_aggregate(inner[:_matching(inner, 0) + 1], prefix + (position,), dims[1:], values)
        else:
            values[prefix + (position,)] = literal(element.split()[-1])


def main() -> int:
    global FILL_SEED
    if len(sys.argv) == 5:
        FILL_SEED = sys.argv[4]
    elif len(sys.argv) != 4:
        print(__doc__)
        return 2
    source, out_dir, prefix = sys.argv[1:4]

    source_text = hoist_constant_geps(strip_debug(open(source).read()))
    shapes = array_shapes(source_text)
    initial = scalar_initializers(source_text)
    lazy = {pointer_object_name(reg) for type_str, reg in parse_params(source_text)
            if is_pointer_type(type_str)}
    expected = {n: {} for n in shapes}
    actual = {n: {} for n in shapes}
    initializers = array_initializers(source_text)
    seed(expected, shapes, initializers)
    seed(actual, shapes, initializers)
    # A global scalar the loop touches becomes a one-element object in
    # the generated code, addressed with no subscript, so it starts from
    # its initializer there too.
    for slot, value in initial.items():
        actual[slot[1:]] = {(): value}
        expected.setdefault(slot[1:], {})

    try:
        source_run = run_source(source, expected, initial, lazy, shapes)
    except RuntimeError as error:
        if 'is outside the declared' in str(error):
            # A sentinel loop whose fill holds no sentinel: the input is
            # unsuitable, which says nothing about the generated code.
            print(f"SOURCE OUT OF RANGE UNDER THIS FILL: {error}")
            return 3
        raise
    stack = source_run.stack
    dp = run_generated(out_dir, prefix, actual, initial, lazy, shapes)
    generated_stack = dp.stack

    # A scalar the loop touches becomes a memory object named after its
    # slot, so '%6' in the source is '@s6' in the generated code and '@n'
    # is '@n'. Compare those too, otherwise a program with no arrays
    # checks nothing.
    # A local slot may be named (`%sum` -> `@ssum`), so the test is
    # whether the source has such a slot, not whether the name is a
    # number.
    # The object each source slot became, so a sanitised name (`%n.addr`
    # -> `sn_addr`) finds its slot.
    by_object: Dict[str, str] = {}
    for slot in stack:
        if slot.startswith('%'):
            if object_name(slot) in by_object:
                raise RuntimeError(f"{by_object[object_name(slot)]} and {slot} would both be "
                                   f"object {object_name(slot)}; the front end refuses this")
            by_object[object_name(slot)] = slot
    scalar_results = []
    # Every address program streams an object the source has: an
    # array, a pointer parameter's array, or a scalar slot.
    known = set(shapes) | lazy | {slot[1:] for slot in initial} | set(by_object)
    for name in sorted(dp.agu_objects - known):
        scalar_results.append((name, '@' + name, '(no such object in the source)', 'an address program'))
    for name in sorted(set(actual)):
        if '@' + name in stack or '@' + name in initial:
            slot = '@' + name
        elif name in by_object and name not in shapes:
            slot = by_object[name]
        else:
            continue
        if slot in dp.counters:
            continue        # an address unit's register, not memory; the (dropped) pass accounts for it
        want = stack.get(slot, 0)
        # A global scalar is either a memory object (an AGU program
        # streams it, `actual` holds it) or the datapath's own (its stack
        # holds it); both start at the initial value, so the side that
        # moved is the live one.
        got = actual[name].get((), generated_stack.get(slot, 0))
        if slot in initial and generated_stack.get(slot) != initial[slot]:
            if actual[name].get((), initial[slot]) != initial[slot]:
                got = (f'(written by both an address program, {actual[name][()]}, and the '
                       f'datapath, {generated_stack[slot]})')
            else:
                got = generated_stack[slot]
        scalar_results.append((name, slot, want, got))

    # Scalars only the datapath carries (its allocas and the globals it
    # references) live in its own stack, not in a memory object.
    compared = {slot for _, slot, _, _ in scalar_results}
    for slot in sorted(set(generated_stack) & set(stack) - compared):
        scalar_results.append((slot.lstrip('%@'), slot, stack[slot], generated_stack[slot]))

    # Every scalar the source touched must be somewhere on the generated
    # side: a memory object with an address program, a counter an
    # address unit owns, or a scalar the datapath declares. One that is
    # nowhere was dropped, and an intersection of what both sides have
    # would never notice.
    objects = {slot for _, slot, _, _ in scalar_results}
    for slot in sorted(source_run.touched):
        if not isinstance(slot, str) or not slot[:1] in '%@':
            continue
        if slot in objects or slot in dp.counters or slot in dp.declared:
            continue
        if isinstance(stack.get(slot), tuple):
            continue        # a pointer parameter's spill slot: the object is the array
        if slot.startswith('%') and object_name(slot) in actual:
            continue
        scalar_results.append((slot.lstrip('%@'), slot, stack.get(slot, 0), '(dropped)'))

    # An array reached by pointer has no extent: the generated programs
    # may read only what the source read or wrote, else an extra stream
    # (an off-by-one past the buffer) would go unseen.
    for name in sorted(lazy):
        touched = source_run.read_keys.get(name, set()) | source_run.written.get(name, set())
        extra = set()
        for agu_stack_holder in dp.agu_read_keys:
            extra |= agu_stack_holder.get(name, set()) - touched
        if extra:
            sample = sorted(extra)[:3]
            scalar_results.append((name, '@' + name, 'reads within the source\'s',
                                   f'reads {len(extra)} element(s) the source never touched, e.g. {sample}'))

    # The value the source returns is the one the datapath's own `ret`
    # returns, in the block that returns (a stale definition elsewhere
    # does not count: only that block's group has the `ret`).
    if source_run.returned and source_run.returned[0] is not None:
        register, value = source_run.returned
        got = dp.returned[1] if dp.returned and dp.returned[0] is not None else '(the datapath returns nothing)'
        scalar_results.append(('ret ' + register, register, value, got))
    elif dp.returned is not None and dp.returned[0] is not None:
        scalar_results.append(('ret', 'void', '(nothing)', dp.returned[1]))

    # A `; counter` line claims an address unit owns the slot: some
    # address program must hold %i<level>_ptr, and its final value must
    # be the source's. The comment alone used to exempt the slot.
    for slot, levels in dp.counter_levels.items():
        if slot not in stack:
            scalar_results.append(('counter ' + slot.lstrip('%@'), slot, '(no such slot)', 'claimed'))
            continue
        held = {}
        for level in levels:
            for agu_stack, order in dp.agu_stacks:
                if f'%i{level}_ptr' in agu_stack:
                    held[level] = (order.get(f'%i{level}_ptr', -1), agu_stack[f'%i{level}_ptr'])
        if not held:
            scalar_results.append(('counter ' + slot.lstrip('%@'), slot, stack[slot],
                                   '(no address program keeps it)'))
            continue
        # Two loops on one slot: the loop whose address unit wrote the
        # counter last is the one whose value the slot holds at the end.
        last = max(held.values(), key=lambda pair: pair[0])[1]
        if stack[slot] != last:
            scalar_results.append(('counter ' + slot.lstrip('%@'), slot, stack[slot], last))

    claimed = {level for levels in dp.counter_levels.values() for level in levels}
    for agu_stack, _ in dp.agu_stacks:
        for held in sorted(agu_stack):
            kept = re.fullmatch(r'%i(\d+)_ptr', held)
            if kept and kept.group(1) not in claimed:
                scalar_results.append(('counter %i' + kept.group(1), held, 'a ; counter line',
                                       '(an address program keeps it and no ; counter line claims it)'))
                claimed.add(kept.group(1))
    for slot in sorted(dp.counters & dp.declared):
        scalar_results.append(('counter ' + slot.lstrip('%@'), slot, 'one owner',
                               '(an address unit keeps it and the datapath declares it)'))
    for slot in sorted(dp.counters):
        if object_name(slot) in dp.agu_objects:
            scalar_results.append(('counter ' + slot.lstrip('%@'), slot, 'one owner',
                                   '(an address unit keeps it and another streams it as an object)'))
    for name, slot, _, _ in list(scalar_results):
        if slot in dp.declared and name in dp.agu_objects:
            scalar_results.append((name, slot, 'one owner',
                                   '(an address program streams it and the datapath declares it)'))

    scalar_names = {r[0] for r in scalar_results}
    names = sorted((set(expected) | set(actual)) - scalar_names)
    print(f"  arrays: {', '.join(names)}")
    ok = True
    for name in names:
        want, got = expected.get(name, {}), actual.get(name, {})
        keys = set(want) | set(got)
        if name in lazy:
            # An array reached by pointer is filled as it is read, so a
            # read one side did not make is no difference: only what was
            # written counts, and what the source wrote must be there.
            keys = source_run.written.get(name, set()) | dp.all_written.get(name, set())
        # An element one side wrote and the other left alone holds, on
        # that other side, what it was filled with: the pattern value for
        # an array reached by pointer, 0 for a declared one. A fallback
        # of 0 for both let a store of 0 be dropped from both sides.
        fill = (lambda k: default_value(name, k)) if name in lazy else (lambda k: 0)
        wrong = [k for k in keys if want.get(k, fill(k)) != got.get(k, fill(k))]
        if wrong:
            ok = False
            sample = sorted(wrong)[:3]
            print(f"  FAIL {name}: {len(wrong)} of {len(keys)} elements differ")
            for k in sample:
                print(f"       {name}{list(k)}: source={want.get(k, fill(k))} generated={got.get(k, fill(k))}")
        else:
            print(f"  ok   {name}: {len(keys)} elements match")

    for name, slot, want, got in scalar_results:
        if want == got:
            print(f"  ok   {name}: matches source {slot} ({want})")
        else:
            ok = False
            print(f"  FAIL {name}: source {slot}={want} generated={got}")

    print()
    print("algorithms match" if ok else "ALGORITHMS DIFFER")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
