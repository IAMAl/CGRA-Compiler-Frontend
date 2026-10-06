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
Rewrites that make clang's output uniform before anything parses it.

clang folds an address with literal subscripts into a constant
expression inside the instruction that uses it:

    %0 = load i32, i32* getelementptr inbounds ([4 x i32], [4 x i32]* @a, i64 0, i64 3)
    %1 = getelementptr inbounds [32 x i32], [32 x i32]* getelementptr inbounds (
             [2 x [32 x i32]], [2 x [32 x i32]]* @a, i64 0, i64 2), i64 0, i64 %i

`hoist_constant_geps` turns each such expression into a getelementptr
instruction of its own (`%cgep0 = getelementptr inbounds ...`, with
the flags the expression had) just before the line, innermost first, so every address is a register and
every consumer -- the parser, the analysis, the verifier -- sees the
same instruction shape whether the subscript was literal or not. Only
instructions (indented lines) are rewritten; a global's initialiser may
hold such an expression too, and there it has to stay.
"""
import re
from typing import List, Tuple

_CONST_GEP = re.compile(r'getelementptr\s+(?P<flags>(?:(?:inbounds|nuw|nusw|inrange\([^)]*\))\s+)*)\(')
_METADATA_TAIL = re.compile(r'(?:,\s*!\w[\w.]*\s+!\S+)+\s*$')
_DEBUG_CALL = re.compile(r'^\s*(?:(?:tail\s+)?call\s+void\s+@llvm\.dbg\.|#dbg_)')


def strip_debug(text: str) -> str:
	"""
	The text without what `clang -g` adds inside a function: `, !dbg !12`
	tails on instructions (and `!llvm.loop !6` on branches), and the
	`llvm.dbg.declare`/`value` calls -- or, from LLVM 19, the `#dbg_declare`
	records -- that describe variables. Neither
	says anything about the computation, and both broke the parsing of
	the instruction they were attached to.
	"""
	out: List[str] = []
	for line in text.split('\n'):
		if not line[:1].isspace():
			out.append(line)
			continue
		if _DEBUG_CALL.match(line):
			continue
		out.append(_METADATA_TAIL.sub('', line))
	return '\n'.join(out)


def natural_alignment(type_str: str) -> int:
	"""The alignment clang gives a scalar of this type; 4 when unsure."""
	match = re.fullmatch(r'i(\d+)', type_str)
	if match:
		return max(1, min(8, (int(match.group(1)) + 7) // 8))
	return {'double': 8, 'float': 4, 'half': 2}.get(type_str, 8 if type_str.endswith('*') or type_str == 'ptr' else 4)


def bracket_depth(token: str) -> int:
	"""Net number of brackets a token opens."""
	return sum(token.count(c) for c in '[{<(') - sum(token.count(c) for c in ']}>)')


def leading_type(text: str) -> str:
	"""
	The LLVM type a declaration or operand starts with.

	`[2 x [2 x i32]] [[2 x i32] [i32 1, i32 2], ...` starts with the
	array type and continues with its initialiser; `i32 5, align 4`
	with `i32`; `{ i32, i32 }* null` with the struct pointer. The type
	ends where its brackets are balanced, so an initialiser is never
	taken for extra dimensions.
	"""
	taken: List[str] = []
	depth = 0
	tokens = text.split()
	for index, token in enumerate(tokens):
		taken.append(token)
		depth += bracket_depth(token)
		if depth <= 0:
			# A function type carries its argument list: `void (i32)*`.
			if index + 1 < len(tokens) and tokens[index + 1].startswith('('):
				continue
			break
	return ' '.join(taken).rstrip(',')


def split_top_level(text: str, separator: str = ',') -> List[str]:
	"""Split at separators outside every bracket pair."""
	parts: List[str] = []
	depth = 0
	current: List[str] = []
	for char in text:
		if char in '([{<':
			depth += 1
		elif char in ')]}>':
			depth -= 1
		if char == separator and depth == 0:
			parts.append(''.join(current).strip())
			current = []
		else:
			current.append(char)
	tail = ''.join(current).strip()
	if tail or parts:
		parts.append(tail)
	return parts


_GLOBAL_ARRAY = re.compile(r'^@(?P<name>[-\w.$]+)\s*=.*?\b(?:global|constant)\s+(?P<rest>\[.*)$')
_BARE_GLOBAL = re.compile(
	r'^(?P<head>\s*(?:%[-\w.$]+\s*=\s*)?(?:load|store)\b.*?,?\s)(?P<ptype>ptr|\S+\*)\s+@(?P<name>[-\w.$]+)(?P<tail>\s*(?:,.*)?)$')


def hoist_constant_geps(text: str) -> str:
	"""
	The text with constant getelementptr expressions made instructions,
	and a global array used bare as a load or store address (`a[0]` with
	opaque pointers: `load i32, ptr @a`) addressed as its first element
	through a getelementptr of its own, so every array access has one
	shape.
	"""
	arrays = {}
	for line in text.split('\n'):
		match = _GLOBAL_ARRAY.match(line)
		if match:
			array_type = leading_type(match.group('rest'))
			# `@p = global [4 x i32]* @a` starts with a bracket too, but
			# holds an address, not an array: a bare `@p` is the pointer.
			if not array_type.endswith('*'):
				arrays[match.group('name')] = array_type
	out: List[str] = []
	# The hoisted registers are named %cgep<n>; a source that kept its
	# value names may already use such a name, and defining it twice
	# silently changed which store went where.
	counter = _FreshNames(text)
	for line in text.split('\n'):
		if not line[:1].isspace():
			out.append(line)
			continue
		hoisted, line = _hoist_in(line, counter)
		bare = _BARE_GLOBAL.match(line)
		if bare and bare.group('name') in arrays:
			array_type = arrays[bare.group('name')]
			depth = array_type.count(' x ')
			reg = counter.take()
			pointer = 'ptr' if bare.group('ptype') == 'ptr' else array_type + '*'
			hoisted.append(f"  {reg} = getelementptr inbounds {array_type}, {pointer} @{bare.group('name')}, "
						   + ', '.join(['i64 0'] * (depth + 1)))
			line = f"{bare.group('head')}{bare.group('ptype')} {reg}{bare.group('tail')}"
		out.extend(hoisted)
		out.append(line)
	return '\n'.join(out)


class _FreshNames:
	"""%cgep<n> names, skipping any the text already uses."""

	def __init__(self, text: str):
		self.used = set(re.findall(r'%cgep\d+\b', text))
		self.next = 0

	def take(self) -> str:
		while f"%cgep{self.next}" in self.used:
			self.next += 1
		name = f"%cgep{self.next}"
		self.next += 1
		return name


def _hoist_in(text: str, counter: '_FreshNames') -> Tuple[List[str], str]:
	"""(instructions to emit first, the text with each expression replaced)."""
	hoisted: List[str] = []
	while True:
		match = _CONST_GEP.search(text)
		if not match:
			return hoisted, text
		start = match.end() - 1
		depth = 0
		end = None
		for index in range(start, len(text)):
			if text[index] == '(':
				depth += 1
			elif text[index] == ')':
				depth -= 1
				if depth == 0:
					end = index
					break
		if end is None:
			raise ValueError(f"unbalanced constant expression: {text.strip()}")
		inner_hoisted, inner = _hoist_in(text[start + 1:end], counter)
		hoisted.extend(inner_hoisted)
		reg = counter.take()
		flags = match.group('flags').strip()
		hoisted.append(f"  {reg} = getelementptr {flags + ' ' if flags else ''}{inner.strip()}")
		text = text[:match.start()] + reg + text[end + 1:]
