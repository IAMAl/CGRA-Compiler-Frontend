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
Facts read straight out of the LLVM IR.

The node lists produced by Gen_AM flatten a getelementptr chain into
loose operand columns, which is enough to know *that* an array is
touched but not enough to say, for one access:

  * which dimension each index belongs to (the chain order is the
    dimension order, outermost first),
  * how many separate accesses to the same array a block performs
    (loop unrolling produces several),
  * what expression each subscript is (`a[i][k+1]`, `b[(k+j)%n][j]`,
    `c[idx[k]]`).

All three are unambiguous in the IR itself, so this module parses the
merged IR and hands the generators a canonical access table. The same
source also says how each loop counter is initialised, compared and
advanced, how every block ends, and what every array and scalar slot is
declared as, so those are read here too.

Memory objects are named after what they are: a global array keeps its
name, a global scalar `@n` becomes `n`, a scalar local `%5` becomes `s5`,
a local array `%t` becomes `lt`, and an array passed in by pointer as
parameter `%a` becomes `ptr_a`.
"""
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import utils.IRParser as irparser
from utils.IRNormalize import bracket_depth, leading_type, split_top_level, strip_debug
from utils.Naming import local_array_name, object_name, pointer_object_name, scalar_param_name


DEBUG = False


# LLVM local names: '%' then name characters. Matching \S+ instead would
# swallow the trailing comma of 'i32* %28, align 4'.
_REG = r'%[-\w.$]+'
_PTR = r'[%@][-\w.$]+'
_OPERAND = r'[-+\w.$%@]+'

_GEP = re.compile(rf'^\s*(?P<dst>{_REG})\s*=\s*getelementptr\s+(?:(?:inbounds|nuw|nusw)\s+)*(?P<rest>.*)$')
_CAST = re.compile(rf'^\s*(?P<dst>{_REG})\s*=\s*(?P<op>sext|zext|trunc)\s+(?:(?:nneg|nuw|nsw)\s+)*(?P<from>\S+)\s+(?P<src>{_OPERAND})\s+to\s+(?P<to>\S+)')
# A type may carry a function signature with commas of its own
# (`void (i32, i32)*`), hence the parenthesised alternative.
_TYPE = r'(?:\([^)]*\)|[^,])+?'
_LOAD = re.compile(
	rf'^\s*(?P<dst>{_REG})\s*=\s*load\s+(?:volatile\s+)?(?P<type>{_TYPE})\s*,\s*{_TYPE}\s+(?P<ptr>{_PTR})')
_STORE = re.compile(
	rf'^\s*store\s+(?:volatile\s+)?(?P<type>{_TYPE})\s+(?P<value>{_OPERAND})\s*,\s*{_TYPE}\s+(?P<ptr>{_PTR})')
_ALLOCA = re.compile(rf'^\s*(?P<dst>{_REG})\s*=\s*alloca\s+(?P<type>.+?)\s*(?:,|$)')
_ICMP = re.compile(
	rf'^\s*(?P<dst>{_REG})\s*=\s*icmp\s+(?:samesign\s+)?(?P<pred>\w+)\s+(?P<type>\S+)\s+(?P<lhs>{_OPERAND})\s*,\s*(?P<rhs>{_OPERAND})')
_BR_COND = re.compile(
	rf'^\s*br\s+i1\s+(?P<cond>{_REG})\s*,\s*label\s+%(?P<taken>[-\w.$]+)\s*,\s*label\s+%(?P<not_taken>[-\w.$]+)')
_JMP = re.compile(r'^\s*br\s+label\s+%(?P<target>[-\w.$]+)')
_SWITCH = re.compile(
	rf'^\s*switch\s+(?P<type>\S+)\s+(?P<value>{_OPERAND})\s*,\s*label\s+%(?P<default>[-\w.$]+)\s*\[(?P<cases>.*)\]')
_CASE = re.compile(r'\S+\s+(?P<literal>-?\d+|true|false)\s*,\s*label\s+%(?P<label>[-\w.$]+)')
_RET = re.compile(r'^\s*ret\b')
# Instructions that treat an address as a value: nothing in the
# generated programs carries one.
_POINTER_VALUE = re.compile(
	rf'^\s*(?P<dst>{_REG})\s*=\s*(?P<op>ptrtoint|inttoptr|bitcast|addrspacecast)\b')
_BINOP = re.compile(
	rf'^\s*(?P<dst>{_REG})\s*=\s*(?P<op>add|sub|mul|sdiv|udiv|srem|urem|shl|ashr|lshr|and|or|xor)\s+'
	rf'(?:nsw\s+|nuw\s+|exact\s+|disjoint\s+|nneg\s+|fast\s+|nnan\s+|ninf\s+|nsz\s+|arcp\s+|contract\s+|afn\s+|reassoc\s+)*'
	rf'(?P<type>\S+)\s+(?P<lhs>{_OPERAND})\s*,\s*(?P<rhs>{_OPERAND})')
# @a = dso_local global [32 x [32 x i32]] zeroinitializer, align 16
_GLOBAL = re.compile(r'^@(?P<name>[-\w.$]+)\s*=.*?\b(?:global|constant)\s+(?P<rest>.+)$')
_DEFINE = re.compile(r'^define\b.*\s@(?P<name>[-\w.$]+)\s*\(')

# Predicate with the counter moved from the right operand to the left.
_SWAPPED = {'slt': 'sgt', 'sgt': 'slt', 'sle': 'sge', 'sge': 'sle',
	'ult': 'ugt', 'ugt': 'ult', 'ule': 'uge', 'uge': 'ule', 'eq': 'eq', 'ne': 'ne'}
# Predicate that holds when the original does not.
_INVERTED = {'slt': 'sge', 'sge': 'slt', 'sle': 'sgt', 'sgt': 'sle',
	'ult': 'uge', 'uge': 'ult', 'ule': 'ugt', 'ugt': 'ule', 'eq': 'ne', 'ne': 'eq'}


@dataclass
class IndexExpr:
	"""
	A subscript expression.

	kind is 'lit' (value), 'counter' (slot, load_reg: a loop counter
	loaded from its alloca), 'value' (reg: a register the address unit
	takes as it is -- a value loaded from memory, or one the datapath
	computes), 'op' (op, args: a binary operation on two of these) or
	'cast' (op 'zext' or 'trunc', args: one of these; `type` the target).
	A `sext` is not kept: widening a signed value is what the address
	unit does itself when it needs a wider operand. `type` is the LLVM
	type a 'value', 'op' or 'cast' node has in the source, so the
	address unit computes it at that width; a counter's type is its
	slot's.
	"""
	kind: str
	value: int = 0
	slot: Optional[str] = None
	load_reg: Optional[str] = None
	reg: Optional[str] = None
	op: Optional[str] = None
	args: List['IndexExpr'] = field(default_factory=list)
	type: Optional[str] = None


@dataclass
class AccessDim:
	"""
	One subscript of an array access.

	`expr` is the subscript's expression. The common shapes are kept
	handy: a literal (`is_constant`, value in `offset`), and a loop
	counter plus a constant (`base_reg` the counter's alloca, `load_reg`
	the register it was loaded into, `offset` the constant, `level` the
	loop level driving it). Anything else is evaluated from `expr`.
	"""
	expr: IndexExpr
	base_reg: Optional[str] = None
	offset: int = 0
	level: Optional[str] = None
	load_reg: Optional[str] = None

	@property
	def is_constant(self) -> bool:
		return self.expr.kind == 'lit'

	@property
	def is_simple(self) -> bool:
		"""Counter plus constant, the shape with a dedicated register name."""
		return self.base_reg is not None


@dataclass
class ScalarAccess:
	"""
	A load from, or store to, a scalar local or global.

	Scalars have no address stream, so the AGU has nothing to say about
	them; the datapath has to carry them itself. Loop counters are scalars
	too, but the AGU owns those, so callers filter them out by slot.
	"""
	slot: str				# the alloca or global holding the value
	block: str
	kind: str				# 'load' or 'store'
	value_reg: str			# register loaded into, or stored from
	position: int = 0		# line index within the block


@dataclass
class ArrayAccess:
	"""A single load from, or store to, one array."""
	array: str
	block: str
	kind: str				# 'load' or 'store'
	index: int				# nth address stream to this array in this block
	value_reg: str			# register loaded into, or stored from
	ptr_reg: str			# terminal getelementptr result
	dims: List[AccessDim] = field(default_factory=list)	# outermost first
	scalar: bool = False	# a scalar promoted to a memory object
	ordinal: int = 0		# nth load of this stream in this block
	position: int = 0		# line index within the block, for emission order

	def suffix(self) -> str:
		"""Name suffix identifying this stream: '<block>_<index>'."""
		return f"{self.block}_{self.index}"

	def load_name(self) -> str:
		"""
		The register this load's value has in the generated programs.

		A stream loaded twice in one block -- a scalar read, written and
		read again -- gets one register per load.
		"""
		name = f"%load_{self.array}_{self.suffix()}"
		return name if self.ordinal == 0 else f"{name}_{self.ordinal}"


class IRSource:
	"""
	The merged IR, parsed once and shared by every analysis.

	`blocks` maps each basic block to its instruction lines, in order;
	`params` lists the function's parameters as (type, register).
	"""

	def __init__(self, r_path: str, base_name: str):
		self.path = os.path.join(r_path, f"{base_name}.ll")
		with open(self.path, 'r') as f:
			self.text = f.read()
		prog = irparser.IR_Parser(r_path, f"{base_name}.ll")
		if prog is None:
			raise RuntimeError(f"could not parse {self.path}")
		defined = sum(1 for line in self.text.splitlines() if _DEFINE.match(line))
		if len(prog.funcs) > 1 or defined > 1:
			raise NotImplementedError(
				f"{self.path}: {max(defined, len(prog.funcs))} functions are defined; "
				f"the front end takes one function per module (its blocks would "
				f"otherwise share names)")
		self.blocks: Dict[str, List[str]] = {}
		for func in prog.funcs:
			for bblock in func.bblocks:
				block_id = str(bblock.name).strip()
				if block_id in self.blocks:
					raise NotImplementedError(
						f"{self.path}: two blocks are named {block_id} (an unlabelled first "
						f"block is called entry; a later block may not be)")
				if block_id == 'ret':
					raise NotImplementedError(
						f"{self.path}: a block is labelled ret, the name the generated address "
						f"programs give their final block; rename it")
				# The merge already normalised the file; stripping again costs
				# nothing and keeps gen_prog.py usable on IR that skipped it.
				self.blocks[block_id] = [strip_debug(instr.nemonic or '') for instr in bblock.instrs]

		for block_id, lines in self.blocks.items():
			for line in lines:
				if re.match(rf'^\s*{_REG}\s*=\s*phi\b', line):
					raise NotImplementedError(
						f"block {block_id}: phi nodes are not supported (at -O0 clang emits "
						f"one for `?:`, `&&` and `||`; write those as if statements): "
						f"{line.strip()}")
				if re.search(r'<\s*\d+\s+x\s+', line):
					raise NotImplementedError(
						f"block {block_id}: vector types are not supported: {line.strip()}")
				pointer_cmp = _ICMP.match(line)
				if pointer_cmp and _is_pointer_type(pointer_cmp.group('type')):
					raise NotImplementedError(
						f"block {block_id}: an address is compared as a value; the generated "
						f"programs carry no addresses: {line.strip()}")
				if _POINTER_VALUE.match(line):
					raise NotImplementedError(
						f"block {block_id}: {_POINTER_VALUE.match(line).group('op')} turns an "
						f"address into a value; the generated programs carry no addresses: "
						f"{line.strip()}")
				pointer_select = re.match(rf'^\s*{_REG}\s*=\s*select\s+i1\s+{_OPERAND}\s*,\s*(?P<type>\S+)', line)
				if pointer_select and _is_pointer_type(pointer_select.group('type')):
					raise NotImplementedError(
						f"block {block_id}: a select between addresses cannot be carried: {line.strip()}")
				if re.match(rf'^\s*(?:{_REG}\s*=\s*)?(?:load|store)\s+atomic\b', line):
					raise NotImplementedError(
						f"block {block_id}: atomic memory operations are not supported: {line.strip()}")
				aggregate = re.match(rf'^\s*(?:{_REG}\s*=\s*)?(?:load|store)\s+(?:volatile\s+)?(?P<rest>[{{\[].*)', line)
				# `store [24 x i32]* %a, [24 x i32]** %a.addr` spills a pointer to
				# an array (`int (*a)[24]`), not an aggregate.
				if aggregate and not _is_pointer_type(leading_type(aggregate.group('rest'))):
					raise NotImplementedError(
						f"block {block_id}: an aggregate is loaded or stored whole; only scalars "
						f"and their arrays are supported: {line.strip()}")
				if (re.match(rf'^\s*(?:{_REG}\s*=\s*)?(?:load|store)\b', line)
						and not _LOAD.match(line) and not _STORE.match(line)):
					raise NotImplementedError(
						f"block {block_id}: memory operand is not a register or a global "
						f"(a constant expression?): {line.strip()}")

		# A value is used where it is defined. clang keeps every variable
		# in an alloca at -O0, so only a temporary of one expression is an
		# SSA value, and that stays in its block; a value crossing blocks
		# has no name the generated programs would give it (its load
		# is named after the block it happened in).
		defined_in: Dict[str, str] = {}
		slots = set()
		for block_id, lines in self.blocks.items():
			for line in lines:
				match = re.match(rf'^\s*(?P<dst>{_REG})\s*=\s*(?P<op>\w+)', line)
				if match:
					defined_in[match.group('dst')] = block_id
					if match.group('op') == 'alloca':
						slots.add(match.group('dst'))
		for block_id, lines in self.blocks.items():
			for line in lines:
				body = re.sub(r'label\s+%[-\w.$]+', '', line.split('=', 1)[-1] if re.match(rf'^\s*{_REG}\s*=', line) else line)
				for reg in re.findall(rf'{_REG}', body):
					if reg in defined_in and reg not in slots and defined_in[reg] != block_id:
						raise NotImplementedError(
							f"block {block_id}: {reg} is defined in block {defined_in[reg]} and used "
							f"here; a value that crosses blocks has no register in the generated "
							f"programs (at -O0 clang keeps such values in allocas): {line.strip()}")

		self.params: List[tuple] = []
		for line in self.text.splitlines():
			params = define_params(line)
			if params is not None:
				for param in params:
					parsed = split_param(param)
					if parsed:
						self.params.append(parsed)
				break

		# A scalar parameter is an input the generated programs read from
		# a global of its own, `@arg_<name>`. Making the parameter a load
		# of that global at the top of the entry block lets every later
		# analysis treat it as any other scalar.
		self.scalar_params: List[tuple] = [(type_str, reg) for type_str, reg in self.params
			if not _is_pointer_type(type_str)]
		if self.scalar_params and self.blocks:
			entry = next(iter(self.blocks))
			self.blocks[entry] = [
				f"  {reg} = load {type_str}, {type_str}* @{scalar_param_name(reg)}, align 4"
				for type_str, reg in self.scalar_params] + self.blocks[entry]

		# The declared type of every global, and the objects the pointer
		# parameters name: both are properties of the source, read once
		# here rather than by whichever pass happened to need them first.
		self.global_types: Dict[str, str] = {}
		for line in self.text.splitlines():
			match = _GLOBAL.match(line)
			if match:
				self.global_types[match.group('name')] = leading_type(match.group('rest'))
		self.pointer_objects: Dict[str, str] = collect_pointer_objects(self)

	def lines(self, block_id: str) -> List[str]:
		return self.blocks.get(str(block_id), [])


def dims_of(type_str: str) -> List[int]:
	return [int(n) for n in re.findall(r'\[(\d+) x', type_str)]


def element_of(type_str: str) -> str:
	element = re.search(r'x\s+([A-Za-z_][A-Za-z0-9_]*\*?)\s*\]', type_str)
	return element.group(1) if element else type_str.split()[0]


def _is_pointer_type(type_str: str) -> bool:
	return type_str.strip().endswith('*') or type_str.strip() == 'ptr'


def define_params(line: str) -> Optional[List[str]]:
	"""
	The parameters of a `define` line, split at top-level commas, or
	None for any other line. A function-pointer parameter
	(`void (i32, i32)* %fp`) has parentheses and commas of its own,
	which `[^)]*` used to stop at.
	"""
	match = _DEFINE.match(line)
	if not match:
		return None
	start = match.end() - 1
	depth = 0
	for index in range(start, len(line)):
		if line[index] == '(':
			depth += 1
		elif line[index] == ')':
			depth -= 1
			if depth == 0:
				return split_top_level(line[start + 1:index])
	raise ValueError(f"unbalanced parameter list: {line.strip()}")


def split_param(param: str) -> Optional[tuple]:
	"""
	(type, register) of one parameter of a `define`, or None.

	clang writes `i32 noundef %n`, `ptr noundef %a`, `i32* nocapture
	readonly align 4 %p`: the type comes first and attributes follow it.
	Taking everything before the name as the type made `noundef` part of
	it, so no parameter was a pointer and no scalar parameter's load
	could be parsed. The type is the first token, extended while its
	brackets are open (`[4 x i32]*`, `{ i32, i32 }*`) or a function
	type's argument list follows (`void (i32)*`).
	"""
	tokens = param.split()
	if len(tokens) < 2 or not tokens[-1].startswith('%'):
		return None
	type_tokens = [tokens[0]]
	depth = bracket_depth(tokens[0])
	k = 1
	while k < len(tokens) - 1 and (depth > 0 or tokens[k].startswith('(')):
		type_tokens.append(tokens[k])
		depth += bracket_depth(tokens[k])
		k += 1
	return ' '.join(type_tokens), tokens[-1]


def collect_array_declarations(ir: IRSource):
	"""
	Dimensions and element type of every global, from its declaration.

	Returns ({name: [dim, ...]}, {name: element type}). A scalar global
	has no dimensions; the function's scalar parameters count as scalar
	globals `arg_<name>`.
	"""
	dims: Dict[str, List[int]] = {}
	element_types: Dict[str, str] = {}
	for name, type_str in ir.global_types.items():
		if _is_pointer_type(type_str):
			# A global holding an address (`int *p = a;` at file scope)
			# is a pointer the model cannot name; taken for an array of
			# its pointee's shape it produced addresses into nothing.
			raise NotImplementedError(
				f"global @{name} holds an address ({type_str}); only arrays passed as "
				f"parameters and global arrays are memory objects")
		dims[name] = dims_of(type_str)
		element_types[name] = element_of(type_str)
		if element_types[name][:1] in '%{<' or element_types[name].startswith('['):
			raise NotImplementedError(
				f"global @{name} holds {type_str}: only arrays of scalars and scalars are "
				f"memory objects the address units can stream")
	for type_str, reg in ir.scalar_params:
		if scalar_param_name(reg) in dims:
			raise NotImplementedError(
				f"global @{scalar_param_name(reg)} has the name the generated programs give "
				f"parameter {reg}'s input; rename one of them")
		dims[scalar_param_name(reg)] = []
		element_types[scalar_param_name(reg)] = type_str
	return dims, element_types


def collect_slot_types(ir: IRSource, declarations=None) -> Dict[str, str]:
	"""
	{slot: declared type} for every local (alloca) and global scalar.

	A local array's slot carries its array type; its element type and
	dimensions are read from that.
	"""
	types: Dict[str, str] = {}
	for lines in ir.blocks.values():
		for line in lines:
			match = _ALLOCA.match(line)
			if match:
				types[match.group('dst')] = match.group('type').strip()
	global_dims, global_elements = declarations or collect_array_declarations(ir)
	for name, dims in global_dims.items():
		if not dims:
			types['@' + name] = global_elements[name]
	return types


def collect_pointer_objects(ir: IRSource) -> Dict[str, str]:
	"""
	{register or slot: object name} for arrays passed in by pointer.

	A pointer parameter `%a` is an array whose extent the function does
	not know. At -O0 it is spilled to `%a.addr` in the entry block and
	reloaded before every use, so both the parameter and its slot name
	the object.
	"""
	objects: Dict[str, str] = {}
	params = set()
	for type_str, reg in ir.params:
		if _is_pointer_type(type_str):
			objects[reg] = pointer_object_name(reg)
			params.add(reg)
	slot_of: Dict[str, str] = {}
	if objects:
		for block_id, lines in ir.blocks.items():
			for line in lines:
				store = _STORE.match(line)
				if not (store and store.group('value') in params and store.group('ptr').startswith('%')):
					continue
				value, slot = store.group('value'), store.group('ptr')
				# One slot per parameter and one parameter per slot: a
				# parameter spilled twice, or two parameters spilled to
				# one slot (`b = a`), made the slot an alias the address
				# programs would not see.
				if slot_of.get(value, slot) != slot or objects.get(slot, objects[value]) != objects[value]:
					raise NotImplementedError(
						f"block {block_id}: {value} is stored to {slot}, which is not its own "
						f"spill slot; a pointer parameter has one slot and a slot holds one "
						f"parameter: {line.strip()}")
				slot_of[value] = slot
				objects[slot] = objects[value]

	# Every other pointer-valued load or store is a pointer the model
	# cannot name: a re-assigned parameter (`a = a + 1`), a pointer
	# copied into a local (`int *q = a`), a global pointer. Dropping the
	# store or naming a scalar after the register produced wrong code
	# without a word.
	for block_id, lines in ir.blocks.items():
		for line in lines:
			store = _STORE.match(line)
			if store and _is_pointer_type(store.group('type').strip()):
				if store.group('ptr') not in objects or store.group('value') not in params:
					raise NotImplementedError(
						f"block {block_id}: a pointer is stored somewhere other than its "
						f"parameter's own slot; only arrays passed as parameters and "
						f"indexed in place are supported: {line.strip()}")
			load = _LOAD.match(line)
			if load and _is_pointer_type(load.group('type').strip()) and load.group('ptr') not in objects:
				raise NotImplementedError(
					f"block {block_id}: a pointer is loaded from {load.group('ptr')}, which is "
					f"not a pointer parameter's slot: {line.strip()}")
	return objects


def _pointer_holders(ir: IRSource, lines: List[str], pointer_objects: Dict[str, str]) -> Dict[str, str]:
	"""
	{register: object} for the registers that hold a pointer parameter's
	address in this block: the parameter itself, and what a load from
	its spill slot produces. The slot is not one: a load or store on it
	moves the address, not an element.
	"""
	holders = {reg: pointer_objects[reg] for _, reg in ir.params if reg in pointer_objects}
	for line in lines:
		load = _LOAD.match(line)
		if load and load.group('ptr') in pointer_objects:
			holders[load.group('dst')] = pointer_objects[load.group('ptr')]
	return holders


def _resolve_index(reg: str, defs: Dict[str, str], counter_slots, after_update,
			type_hint: Optional[str] = None) -> IndexExpr:
	"""
	The expression a getelementptr subscript computes; 'cast' nodes carry
	the cast's target type, 'value' and 'op' nodes the type they have.

	A sext is transparent and a zext or trunc becomes a 'cast' node; a
	binary operation becomes an 'op' node; a load from a loop counter's
	alloca is the counter (unless it follows the latch's update or the
	counter's initialisation, when it is that value, named by the
	generators); any other register is taken as a value the address unit
	receives by name. `type_hint` is the type the register has where it
	is used, kept on 'value' and 'op' nodes so the address unit computes
	at the source's width rather than assuming i32.
	"""
	if not reg.startswith('%'):
		return IndexExpr(kind='lit', value=int(reg))

	line = defs.get(reg)
	if line is None:
		return IndexExpr(kind='value', reg=reg, type=type_hint)

	cast = _CAST.match(line)
	if cast:
		inner = _resolve_index(cast.group('src'), defs, counter_slots, after_update, cast.group('from'))
		if cast.group('op') == 'sext':
			return inner
		# A zext or trunc changes the value: an unsigned char index
		# widened with sext would go negative.
		return IndexExpr(kind='cast', op=cast.group('op'), type=cast.group('to'), args=[inner])

	binop = _BINOP.match(line)
	if binop:
		type_str = binop.group('type')
		return IndexExpr(kind='op', op=binop.group('op'), type=type_str, args=[
			_resolve_index(binop.group('lhs'), defs, counter_slots, after_update, type_str),
			_resolve_index(binop.group('rhs'), defs, counter_slots, after_update, type_str)])

	load = _LOAD.match(line)
	if load and load.group('ptr') in counter_slots and load.group('dst') not in after_update:
		return IndexExpr(kind='counter', slot=load.group('ptr'), load_reg=load.group('dst'),
			type=load.group('type').strip())

	if load and load.group('dst') in after_update and not after_update[load.group('dst')].startswith('%'):
		return IndexExpr(kind='lit', value=int(after_update[load.group('dst')]))
	return IndexExpr(kind='value', reg=reg, type=load.group('type').strip() if load else type_hint)


def _same_width(expr: IndexExpr) -> bool:
	"""
	Whether an add/sub is computed at its counter operand's own type.

	`signed char i; a[i + 100]` adds at i32 after widening i; folding it
	to `%i1 + 100` computed the sum at i8 and wrapped. Such an expression
	is left whole, so the address unit widens first.
	"""
	return all(arg.kind != 'counter' or arg.type is None or arg.type == expr.type
		for arg in expr.args)


def _dim_from(expr: IndexExpr) -> AccessDim:
	"""Fill in the handy fields for the common subscript shapes."""
	if expr.kind == 'lit':
		return AccessDim(expr=expr, offset=expr.value)
	if expr.kind == 'counter':
		return AccessDim(expr=expr, base_reg=expr.slot, load_reg=expr.load_reg)
	if expr.kind == 'op' and expr.op in ('add', 'sub') and _same_width(expr):
		left, right = expr.args
		if left.kind == 'counter' and right.kind == 'lit':
			offset = right.value if expr.op == 'add' else -right.value
			return AccessDim(expr=expr, base_reg=left.slot, load_reg=left.load_reg, offset=offset)
		if expr.op == 'add' and right.kind == 'counter' and left.kind == 'lit':
			return AccessDim(expr=expr, base_reg=right.slot, load_reg=right.load_reg, offset=left.value)
	return AccessDim(expr=expr)


def promote_loop_scalars(scalar_accesses: Dict[str, List[ScalarAccess]],
			array_accesses: Dict[str, Dict[str, List[ArrayAccess]]],
			loop_blocks, counters) -> None:
	"""
	Move scalars the loop touches into the array access table, in place.

	A load or store inside a loop is streamed memory traffic, so the AGU
	owns it. A scalar only touched outside every loop stays with the
	datapath. One that is touched in both places is owned by the AGU
	throughout, because a single object cannot be addressed by both.

	Loop counters are excluded: the AGU already carries those as
	%i<level>.
	"""
	streamed = {access.slot
			for block_id, entries in scalar_accesses.items() if block_id in loop_blocks
			for access in entries if access.slot not in counters}
	if not streamed:
		return

	for block_id in list(scalar_accesses):
		keep = []
		streams: Dict[str, int] = {}
		loads: Dict[str, int] = {}
		for access in scalar_accesses[block_id]:
			if access.slot not in streamed:
				keep.append(access)
				continue
			name = object_name(access.slot)
			# A scalar object has one address, so one stream per block:
			# stream 0. Numbering scalars through one counter per block
			# gave the second scalar's only stream the number 1.
			index = streams.setdefault(access.slot, 0)
			ordinal = 0
			if access.kind == 'load':
				ordinal = loads.get(access.slot, 0)
				loads[access.slot] = ordinal + 1
			array_accesses.setdefault(block_id, {}).setdefault(name, []).append(
				ArrayAccess(array=name, block=block_id, kind=access.kind,
					index=index, value_reg=access.value_reg,
					ptr_reg=access.slot, dims=[], scalar=True, ordinal=ordinal,
					position=access.position))
		if keep:
			scalar_accesses[block_id] = keep
		else:
			del scalar_accesses[block_id]


def collect_scalar_accesses(ir: IRSource, pointer_objects: Dict[str, str]) -> Dict[str, List[ScalarAccess]]:
	"""
	Build {block_id: [ScalarAccess, ...]} for loads and stores of scalars.

	A pointer that no getelementptr produced is an alloca or a global, so
	the access is scalar -- unless the slot holds a pointer parameter,
	whose loads and stores only shuffle the array's address about.
	"""
	accesses: Dict[str, List[ScalarAccess]] = {}
	# Every address a load or store may use: a slot, a global, the
	# result of a getelementptr, or a register holding a pointer
	# parameter. Anything else (a pointer a call returned, a pointer read
	# from a struct) names no memory object, and treating it as a scalar
	# slot invented one.
	slots = {match.group('dst') for lines in ir.blocks.values() for line in lines
		for match in [_ALLOCA.match(line)] if match}
	for block_id, lines in ir.blocks.items():
		gep_results = set()
		found: List[ScalarAccess] = []
		# Registers holding a pointer parameter's address: a load or
		# store through one is `*p`, an element of that object, not a
		# scalar of its own.
		holders = _pointer_holders(ir, lines, pointer_objects)
		not_scalar = set(pointer_objects) | set(holders)

		def check_address(ptr: str) -> None:
			# Callers pass only what is neither a getelementptr result nor
			# a pointer holder; a register that is no slot either names
			# nothing.
			if ptr.startswith('%') and ptr not in slots:
				raise NotImplementedError(
					f"block {block_id}: {ptr} is used as an address but is neither a local, a "
					f"global, a getelementptr result nor a pointer parameter; the generated "
					f"programs address only named memory objects")

		for position, line in enumerate(lines):
			gep = _GEP.match(line)
			if gep:
				gep_results.add(gep.group('dst'))
				continue

			load = _LOAD.match(line)
			if load and load.group('ptr') not in gep_results and load.group('ptr') not in not_scalar:
				check_address(load.group('ptr'))
				found.append(ScalarAccess(slot=load.group('ptr'), block=block_id,
					kind='load', value_reg=load.group('dst'), position=position))
				continue

			store = _STORE.match(line)
			if store and store.group('ptr') not in gep_results and store.group('ptr') not in not_scalar:
				check_address(store.group('ptr'))
				found.append(ScalarAccess(slot=store.group('ptr'), block=block_id,
					kind='store', value_reg=store.group('value'), position=position))

		if found:
			accesses[block_id] = found

	return accesses


def _step_into(type_str: str) -> str:
	"""The element type of an array type: `[4 x [3 x i32]]` -> `[3 x i32]`."""
	match = re.fullmatch(r'\[\s*\d+\s+x\s+(.*)\]', type_str.strip())
	if not match:
		raise NotImplementedError(f"{type_str} is not an array type")
	return match.group(1).strip()


def _same_object(block_id: str, line: str, name: str, declared: str, source_type: str) -> None:
	"""A getelementptr into an array must name the array's own type."""
	if declared and declared.strip() != source_type:
		raise NotImplementedError(
			f"block {block_id}: {line.strip()} steps through {name} ({declared}) as a "
			f"{source_type}; an object is only addressed as its declared type")


def _drop_leading_zero(block_id: str, line: str, name: str, indices: List[str], index_types: List[str]):
	"""
	The indices after the leading one, which must be the literal 0.

	The first index of a getelementptr on an array counts whole arrays:
	`getelementptr [8 x i32], ptr @a, i64 1, ...` is past @a. It used to
	be dropped whatever it was, which read `(m + i)[0][j]` as m[0][j].
	"""
	if not indices or indices[0] != '0':
		raise NotImplementedError(
			f"block {block_id}: {line.strip()} steps past {name}: the leading subscript "
			f"{indices[0] if indices else '(none)'} counts whole objects and must be 0")
	return indices[1:], index_types[1:]


def _offset_expr(last: IndexExpr, step: IndexExpr, type_str: str) -> IndexExpr:
	"""`last + step`, with a literal 0 on either side folded away."""
	if last.kind == 'lit' and last.value == 0:
		return step
	if step.kind == 'lit' and step.value == 0:
		return last
	return IndexExpr(kind='op', op='add', type=type_str, args=[last, step])


def collect_array_accesses(ir: IRSource, index_reg_to_loop_level: Dict[str, str],
			slot_types: Dict[str, str], pointer_objects: Dict[str, str],
			after_update: Dict[str, str], array_types: Dict[str, str] = None):
	"""
	Build {block_id: {array_name: [ArrayAccess, ...]}} from the merged IR,
	together with {object: source type} for the arrays reached by pointer.

	Accesses are numbered in source order within each (block, array), so
	the AGU and the datapath can agree on a register name for each one
	without either having to re-derive the ordering. A getelementptr on a
	global roots an access to it; one on a local array (an alloca of array
	type) roots an access to the object named after that slot; one on a
	pointer parameter roots an access to `ptr_<param>`, whose subscripts
	all count because the pointer itself is the first index.
	"""
	accesses: Dict[str, Dict[str, List[ArrayAccess]]] = {}
	pointer_types: Dict[str, str] = {}
	counter_slots = set(index_reg_to_loop_level)
	array_types = array_types or {}

	for block_id, lines in ir.blocks.items():
		defs: Dict[str, str] = {}		# register -> defining source line
		gep_array: Dict[str, str] = {}	# gep result -> array name
		gep_dims: Dict[str, List[AccessDim]] = {}	# gep result -> subscripts
		gep_type: Dict[str, str] = {}	# gep result -> the type it points at
		per_array: Dict[str, List[ArrayAccess]] = {}
		# One index per *address stream*, keyed by the terminal
		# getelementptr. A read-modify-write of the same element is one
		# stream, so its load and store share a number and the AGU
		# computes the address once.
		stream_index: Dict[str, Dict[str, int]] = {}
		load_count: Dict[str, int] = {}
		# `*p` on a pointer parameter: no getelementptr, the pointer
		# itself is the address, so it is element 0 of the object.
		holders = _pointer_holders(ir, lines, pointer_objects)

		def index_for(array: str, ptr: str) -> int:
			streams = stream_index.setdefault(array, {})
			return streams.setdefault(ptr, len(streams))

		def dereference(ptr: str, type_str: str) -> None:
			name = holders[ptr]
			gep_array[ptr] = name
			gep_dims[ptr] = [_dim_from(IndexExpr(kind='lit', value=0))]
			gep_type[ptr] = type_str.strip()
			pointer_types.setdefault(name, type_str.strip())

		def at_element_type(kind: str, ptr: str, type_str: str) -> None:
			# The address units load and store whole elements: an access
			# at another type (`*(int *)&a64[i]`, opaque pointers) would
			# read part of one, and used to be emitted at the element's
			# type without a word.
			if type_str.strip() != gep_type[ptr]:
				raise NotImplementedError(
					f"block {block_id}: {line.strip()} {kind}s a {type_str.strip()} where "
					f"{gep_array[ptr]} holds {gep_type[ptr]}; an element is accessed as its own type")

		for position, line in enumerate(lines):
			gep = _GEP.match(line)
			if gep:
				dst = gep.group('dst')
				parts = split_top_level(gep.group('rest'))
				source_type = parts[0].strip()
				base = parts[1].split()[-1]
				indices = [part.split()[-1] for part in parts[2:]]
				index_types = [part.split()[0] for part in parts[2:]]

				if base.startswith('@'):
					gep_array[dst] = base[1:]
					gep_dims[dst] = []
					declared = array_types.get(base[1:], '')
					if source_type.startswith('['):
						_same_object(block_id, line, base[1:], declared, source_type)
						indices, index_types = _drop_leading_zero(block_id, line, base[1:], indices, index_types)
						stepped_indices = indices
					else:
						# `*(a + i)` with the decay folded away: an offset in
						# elements from the first. Only a one-dimensional
						# array keeps a flat offset a subscript; a byte
						# offset (`getelementptr i8, ptr @a, i64 12`) or a
						# flattened matrix would need dividing.
						stepped_indices = indices[1:]
						if declared.count(' x ') != 1 or element_of(declared) != source_type:
							raise NotImplementedError(
								f"block {block_id}: {line.strip()} steps through @{base[1:]} "
								f"({declared}) in units of {source_type}; only a one-dimensional "
								f"array indexed by its element type can be addressed this way")
				elif base in gep_array:
					gep_array[dst] = gep_array[base]
					gep_dims[dst] = list(gep_dims[base])
					# A getelementptr on an address steps in units of the type it
					# names, which must be what the address points at: stepping a
					# row pointer in elements, or an element pointer in rows,
					# would reinterpret the object.
					if source_type != gep_type[base]:
						raise NotImplementedError(
							f"block {block_id}: {line.strip()} steps through {gep_array[base]} in units "
							f"of {source_type}, but {base} points at a {gep_type[base]}")
					if gep_dims[dst]:
						# Pointer arithmetic, `(p + i)[m]`: the first index moves
						# along the last subscript, whether p is an element
						# pointer or a row pointer (`*(*(a + i) + j)`). Only a
						# literal 0 -- clang's usual leading index -- adds nothing.
						if indices[0] != '0':
							step = _resolve_index(indices[0], defs, counter_slots, after_update, index_types[0])
							last = gep_dims[dst].pop()
							gep_dims[dst].append(_dim_from(_offset_expr(last.expr, step, index_types[0])))
						indices, index_types = indices[1:], index_types[1:]
						stepped_indices = indices
					else:
						# An address of the whole object: the leading index
						# counts whole objects and must be 0 to stay in this one.
						indices, index_types = _drop_leading_zero(block_id, line, gep_array[base], indices, index_types)
						stepped_indices = indices
				elif slot_types.get(base, '').startswith('['):
					gep_array[dst] = local_array_name(base)
					gep_dims[dst] = []
					_same_object(block_id, line, local_array_name(base), slot_types[base], source_type)
					indices, index_types = _drop_leading_zero(block_id, line, local_array_name(base), indices, index_types)
					stepped_indices = indices
				else:
					holder = defs.get(base, '')
					load = _LOAD.match(holder)
					if base in pointer_objects:
						name = pointer_objects[base]
					elif load and load.group('ptr') in pointer_objects:
						name = pointer_objects[load.group('ptr')]
					else:
						raise NotImplementedError(
							f"getelementptr on a pointer that is not an array: {line.strip()}")
					if source_type[:1] in '%{':
						raise NotImplementedError(
							f"block {block_id}: {base} points to a structure ({source_type}); only "
							f"arrays of scalars are memory objects the address units stream: {line.strip()}")
					gep_array[dst] = name
					gep_dims[dst] = []
					pointer_types.setdefault(name, source_type)
					stepped_indices = indices[1:]
				# What the result points at: the type the getelementptr names,
				# stepped into once per remaining subscript. Too many subscripts
				# would step into a scalar.
				pointee = source_type
				for _ in stepped_indices:
					if not pointee.startswith('['):
						raise NotImplementedError(
							f"block {block_id}: {line.strip()} has more subscripts than {gep_array[dst]} has dimensions")
					pointee = _step_into(pointee)
				gep_type[dst] = pointee
				gep_dims[dst] += [
					_dim_from(_resolve_index(index, defs, counter_slots, after_update, type_str))
					for index, type_str in zip(indices, index_types)]
				defs[dst] = line
				continue

			load = _LOAD.match(line)
			if load and load.group('ptr') in holders and load.group('ptr') not in gep_array:
				dereference(load.group('ptr'), load.group('type'))
			if load and load.group('ptr') in gep_array:
				ptr = load.group('ptr')
				array = gep_array[ptr]
				at_element_type('load', ptr, load.group('type'))
				ordinal = load_count.get(ptr, 0)
				load_count[ptr] = ordinal + 1
				per_array.setdefault(array, []).append(ArrayAccess(
					array=array, block=block_id, kind='load',
					index=index_for(array, ptr), value_reg=load.group('dst'),
					ptr_reg=ptr, dims=list(gep_dims[ptr]), ordinal=ordinal, position=position))
				defs[load.group('dst')] = line
				continue

			store = _STORE.match(line)
			if store and store.group('ptr') in holders and store.group('ptr') not in gep_array:
				dereference(store.group('ptr'), store.group('type'))
			if store and store.group('ptr') in gep_array:
				ptr = store.group('ptr')
				array = gep_array[ptr]
				at_element_type('store', ptr, store.group('type'))
				per_array.setdefault(array, []).append(ArrayAccess(
					array=array, block=block_id, kind='store',
					index=index_for(array, ptr), value_reg=store.group('value'),
					ptr_reg=ptr, dims=list(gep_dims[ptr]), position=position))
				continue

			match = re.match(rf'^\s*(?P<dst>{_REG})\s*=', line)
			if match:
				defs[match.group('dst')] = line

		if per_array:
			# Attach the loop level each counter subscript is driven by.
			# The level belongs to the load, not the slot: two loops in
			# sequence can share a counter variable, and the load says
			# which one this is.
			for entries in per_array.values():
				for access in entries:
					for dim in access.dims:
						if dim.base_reg is not None:
							dim.level = (index_reg_to_loop_level.get(dim.load_reg)
								or index_reg_to_loop_level.get(dim.base_reg))
			accesses[block_id] = per_array

	if DEBUG:
		for block_id, arrays in sorted(accesses.items()):
			for array, entries in sorted(arrays.items()):
				for access in entries:
					dims = [(d.level, d.base_reg, d.offset, d.expr.kind) for d in access.dims]
					print(f"  block {block_id} {array}[{access.index}] "
						f"{access.kind} {access.value_reg} dims={dims}")

	return accesses, pointer_types


def collect_terminators(ir: IRSource) -> Dict[str, Dict]:
	"""
	How every block ends.

	{'kind': 'cond', 'cond', 'taken', 'not_taken'} for a conditional
	branch, {'kind': 'jump', 'target'}, {'kind': 'switch', 'type',
	'value', 'default', 'cases': [(literal, label), ...]} or
	{'kind': 'ret', 'type', 'value'} ('value' None for `ret void`).
	"""
	terminators: Dict[str, Dict] = {}
	for block_id, lines in ir.blocks.items():
		if not lines:
			raise NotImplementedError(f"block {block_id} is empty")
		last = lines[-1]
		cond = _BR_COND.match(last)
		if cond:
			terminators[block_id] = {'kind': 'cond', 'cond': cond.group('cond'),
				'taken': cond.group('taken'), 'not_taken': cond.group('not_taken')}
			continue
		jump = _JMP.match(last)
		if jump:
			terminators[block_id] = {'kind': 'jump', 'target': jump.group('target')}
			continue
		switch = _SWITCH.match(last)
		if switch:
			terminators[block_id] = {'kind': 'switch', 'type': switch.group('type'),
				'value': switch.group('value'), 'default': switch.group('default'),
				'cases': [(c.group('literal'), c.group('label'))
					for c in _CASE.finditer(switch.group('cases'))]}
			continue
		if last.strip().startswith('unreachable'):
			raise NotImplementedError(
				f"block {block_id} ends in unreachable; the generated programs have no such "
				f"end (clang emits it after a call to a noreturn function)")
		if _RET.match(last):
			returned = re.match(rf'^\s*ret\s+(?P<type>\S+)\s+(?P<value>{_OPERAND})\s*$', last)
			if returned is None and not re.match(r'^\s*ret\s+void\s*$', last):
				raise NotImplementedError(
					f"block {block_id}: only a scalar or nothing can be returned: {last.strip()}")
			if returned and _is_pointer_type(returned.group('type')):
				raise NotImplementedError(
					f"block {block_id}: an address cannot be returned; the generated programs "
					f"carry no addresses: {last.strip()}")
			terminators[block_id] = {'kind': 'ret',
				'type': returned.group('type') if returned else 'void',
				'value': returned.group('value') if returned else None}
			continue
		raise NotImplementedError(f"block {block_id} ends in an unsupported way: {last.strip()}")
	return terminators


def _self_updates(ir: IRSource, block: str) -> Dict[str, List]:
	"""
	{slot: [opcode, operands]} for every `slot = slot <op> x` a block ends
	with, the loaded slot written as '%counter'. A store of anything else
	maps the slot to None.
	"""
	loads: Dict[str, str] = {}
	defs: Dict[str, str] = {}
	updates: Dict[str, Optional[List]] = {}
	addresses = set()
	holders = _pointer_holders(ir, ir.lines(block), ir.pointer_objects)
	for line in ir.lines(block):
		load = _LOAD.match(line)
		if load:
			loads[load.group('dst')] = load.group('ptr')
		match = re.match(rf'^\s*(?P<dst>{_REG})\s*=', line)
		if match:
			defs[match.group('dst')] = line
		gep = _GEP.match(line)
		if gep:
			addresses.add(gep.group('dst'))
		store = _STORE.match(line)
		if not store:
			continue
		slot = store.group('ptr')
		if slot in addresses or slot in loads or slot in holders:
			continue		# an array element, or `*p`: not a scalar slot
		if slot in updates:
			# `k++; ...; k++;` in one block: a single step cannot say
			# it, and keeping the last store halved the stride.
			updates[slot] = None
			continue
		update = _BINOP.match(defs.get(store.group('value'), ''))
		if update is None:
			updates[slot] = None
			continue
		operands = []
		for operand in (update.group('lhs'), update.group('rhs')):
			operands.append('%counter' if loads.get(operand) == slot else operand)
		updates[slot] = [update.group('op'), operands] if '%counter' in operands else None
	return updates


def describe_loop(ir: IRSource, header: str, members, predecessors: Dict[str, List[str]],
			other_loops=()) -> Dict[str, object]:
	"""
	Read one loop's counter from the IR.

	A counter is a slot that a latch advances with `slot = slot <op> x`
	and that nothing else inside the loop stores. If the header compares
	such a slot, the AGU runs the compare itself (predicate normalised so
	the counter is on the left and the loop continues while it holds);
	otherwise the header decides on the value the datapath computes, as
	an `if` does, and the counter -- if there is one -- only drives
	addresses. Bounds, initial values and steps may be literals or
	registers.
	"""
	members = set(members)
	latches = [b for b in predecessors.get(header, []) if b in members]
	if not latches:
		raise NotImplementedError(f"loop header {header} has no back edge")

	updates = {latch: _self_updates(ir, latch) for latch in latches}
	stored_elsewhere = set()
	for block in members:
		if block in latches:
			continue
		for line in ir.lines(block):
			store = _STORE.match(line)
			if store:
				stored_elsewhere.add(store.group('ptr'))
	candidates: List[str] = []
	for latch in latches:
		for slot, step in updates[latch].items():
			# A global is memory the rest of the program sees: keeping it
			# in an address unit's register would leave the global stale.
			if step is not None and slot not in stored_elsewhere and slot not in candidates \
					and not slot.startswith('@'):
				candidates.append(slot)
			elif step is not None and slot in stored_elsewhere and slot not in candidates \
					and not slot.startswith('@'):
				# `if (...) i = i + 1;` in the body as well as `i++` in the
				# latch: the variable is not a counter the address unit
				# can carry. It is streamed as a scalar, correctly; said
				# here, as the header-update case is.
				print(f"Note: loop {header} advances {slot} in its latch but also stores it in "
					f"its body; it is streamed as a scalar, not carried as a counter")
	if not candidates and header not in latches:
		# `do { ...; j++; } while (j < n)`: the step is in the header and
		# the compare in the latch. The address unit reloads a counter
		# only at the header, so a value advanced there would be stale in
		# the latch; the slot is streamed as a scalar instead, which is
		# correct but worth knowing.
		stored_in_body = {store.group('ptr') for block in members if block not in latches and block != header
			for line in ir.lines(block) for store in [_STORE.match(line)] if store}
		for slot, step in _self_updates(ir, header).items():
			if step is not None and slot not in stored_in_body and not slot.startswith('@'):
				print(f"Note: loop {header} advances {slot} in its header rather than a latch; "
					f"it is streamed as a scalar, not carried as a counter")
	# A variable advanced by `j++` in a body block that is not a latch
	# (`j++; if (j >= n) break; if (b[j]) continue;`) is not a counter
	# either: said here, as the header-update case is.
	for block in members:
		if block in latches or block == header:
			continue
		for slot, step in _self_updates(ir, block).items():
			if step is not None and slot not in candidates and not slot.startswith('@') \
					and not any(updates[latch].get(slot) for latch in latches):
				print(f"Note: loop {header} advances {slot} in block {block}, which is not a latch; "
					f"it is streamed as a scalar, not carried as a counter")
	for latch in latches:
		for slot, step in updates[latch].items():
			if step is None and slot in candidates:
				candidates.remove(slot)		# a latch overwrites it outright

	# The header's compare and branch. The AGU performs the compare
	# itself only when the header decides between the loop and its exit
	# on a counter; a header that jumps on, switches, or branches between
	# two blocks of the loop is left to the datapath's condition.
	loads: Dict[str, str] = {}
	load_line: Dict[str, int] = {}
	casts: Dict[str, tuple] = {}
	compare = None
	branch = None
	for number, line in enumerate(ir.lines(header)):
		load = _LOAD.match(line)
		if load:
			loads[load.group('dst')] = load.group('ptr')
			load_line[load.group('dst')] = number
		cast = _CAST.match(line)
		if cast:
			casts[cast.group('dst')] = (cast.group('src'), cast.group('op'), cast.group('from'), cast.group('to'))
		cmp = _ICMP.match(line)
		if cmp:
			compare = cmp
		br = _BR_COND.match(line)
		if br:
			branch = br

	def uncast(reg: str) -> str:
		# `icmp slt i64 %sext, %n` compares the counter through a cast.
		while reg in casts:
			reg = casts[reg][0]
		return reg

	def cast_chain(reg: str) -> List[tuple]:
		# The casts between the counter's load and the compare, in the
		# order they are applied; the AGU repeats them exactly.
		chain = []
		while reg in casts:
			src, op, from_type, to_type = casts[reg]
			chain.append((op, from_type, to_type))
			reg = src
		return list(reversed(chain))

	decides = False
	taken = not_taken = None
	if branch is not None:
		taken, not_taken = branch.group('taken'), branch.group('not_taken')
		decides = (taken in members) != (not_taken in members)

	counter_reg = None
	if decides and compare is not None and branch.group('cond') == compare.group('dst'):
		for operand in (compare.group('lhs'), compare.group('rhs')):
			if uncast(operand) in loads and loads[uncast(operand)] in candidates:
				counter_reg = operand
				break

	result: Dict[str, object] = {
		'counter_slot': None, 'init': None, 'init_block': None,
		'predicate': 'slt', 'bound': None, 'compare_on_counter': counter_reg is not None,
		'compare_type': compare.group('type') if counter_reg is not None else 'i32',
		'compare_casts': cast_chain(counter_reg) if counter_reg is not None else [],
		'compare_after_update': False,
		'body_entry': (taken if taken in members else not_taken) if decides else None,
		'exit_target': (not_taken if taken in members else taken) if decides else None,
		'latches': {latch: None for latch in latches},
	}

	if counter_reg is not None:
		slot = loads[uncast(counter_reg)]
		pred = compare.group('pred')
		lhs, rhs = compare.group('lhs'), compare.group('rhs')
		bound = rhs if counter_reg == lhs else lhs
		if counter_reg == rhs:
			pred = _SWAPPED[pred]
		if taken not in members:
			pred = _INVERTED[pred]		# the loop runs while the compare fails
		result['predicate'] = pred
		result['bound'] = bound
	else:
		# Nothing compares a candidate: the counter, if any, is the one
		# that drives an address. Taking the first self-updated slot
		# made an accumulator (`acc += ...`) the counter of a loop whose
		# real counter was compared through a cast.
		addressing = [c for c in candidates if _drives_address(ir, members, c)]
		if len(addressing) == 1 or (not addressing and len(candidates) == 1):
			slot = (addressing or candidates)[0]
		else:
			return result

	result['counter_slot'] = slot
	result['latches'] = {latch: updates[latch].get(slot) for latch in latches}
	# Where each latch stores the advanced counter: the address streams
	# of that block are emitted around it in source order.
	result['update_positions'] = {}
	for latch in latches:
		if updates[latch].get(slot):
			result['update_positions'][latch] = max(
				n for n, line in enumerate(ir.lines(latch))
				if _STORE.match(line) and _STORE.match(line).group('ptr') == slot)

	# The initial value: the store to the slot nearest before the header,
	# looked for backwards through the blocks outside the loop.
	init = None
	init_block = None
	frontier = [b for b in predecessors.get(header, []) if b not in members]
	visited = set()
	while frontier and init is None:
		block = frontier.pop(0)
		if block in visited:
			continue
		visited.add(block)
		for number, line in reversed(list(enumerate(ir.lines(block)))):
			store = _STORE.match(line)
			if store and store.group('ptr') == slot:
				init = store.group('value')
				init_block = block
				result['init_position'] = number
				break
		if init is None:
			frontier.extend(b for b in predecessors.get(block, []) if b not in members)
	if init is None:
		raise NotImplementedError(
			f"loop header {header}: no store initialising counter {slot} before the loop")
	# The store found must be the one the loop starts from: no block of
	# another loop that stores the slot may lie between it and the
	# header. `for (i = 0; ...) ...; for (; i < n; i++) ...` has the
	# second loop start from the first one's final value, and walking
	# on to the first loop's `i = 0` restarted the count.
	foreign = set(other_loops) - members
	reach = set()
	frontier = [b for b in predecessors.get(header, []) if b not in members and b != init_block]
	while frontier:
		block = frontier.pop()
		if block in reach or block == init_block:
			continue
		reach.add(block)
		frontier.extend(b for b in predecessors.get(block, []) if b not in members)
	for block in sorted(reach & foreign):
		if any(_STORE.match(line) and _STORE.match(line).group('ptr') == slot for line in ir.lines(block)):
			raise NotImplementedError(
				f"loop header {header}: counter {slot} is not initialised before the loop; "
				f"it carries the final value of the loop through {block} (initialise it "
				f"explicitly before the loop)")
	if init_block in foreign:
		# The store is another loop's latch update: it initialises this
		# loop only if that loop cannot be left before it (`for (;;) {
		# if (a[k]) break; k++; if (k >= m) break; }` can), else the
		# slot holds whatever the latch last stored, or nothing.
		successors = _successors_of(predecessors)
		entry = next(iter(ir.blocks))
		if not _dominates(successors, entry, init_block, header):
			raise NotImplementedError(
				f"loop header {header}: counter {slot} is initialised only by the update in "
				f"{init_block}, a latch of another loop that can be left before it; "
				f"initialise the counter explicitly before this loop")
	result['init'] = init
	result['init_block'] = init_block

	if counter_reg is not None and header in latches and updates[header].get(slot):
		# A single-block loop: does the compare read the counter before
		# or after the latch's update?
		store_at = max(n for n, line in enumerate(ir.lines(header))
			if _STORE.match(line) and _STORE.match(line).group('ptr') == slot)
		result['compare_after_update'] = load_line[uncast(counter_reg)] > store_at

	return result


def _drives_address(ir: IRSource, members, slot: str) -> bool:
	"""Whether a getelementptr inside the loop subscripts with this slot."""
	for block in members:
		defs: Dict[str, str] = {}
		for line in ir.lines(block):
			gep = _GEP.match(line)
			if gep:
				for part in split_top_level(gep.group('rest'))[2:]:
					pending = [_resolve_index(part.split()[-1], defs, {slot}, {})]
					while pending:
						expr = pending.pop()
						if expr.kind == 'counter':
							return True
						pending.extend(expr.args)
			match = re.match(rf'^\s*(?P<dst>{_REG})\s*=', line)
			if match:
				defs[match.group('dst')] = line
	return False


def check_counter_ownership(ir: IRSource, loop_levels, cfg=None) -> None:
	"""
	Refuse a store to a loop counter that is neither its initialisation
	nor a latch update.

	The AGU owns a counter from the store that initialises it to the
	last latch that advances it, and the datapath does not carry the
	slot at all; an `i = i * 2` after the loop, or an assignment before
	it other than the initialisation, would be dropped without a word.
	A store every path to the initialisation passes through first
	(`int k = 0;` at the declaration, `k = 0;` again before the loop) is
	dead by then and is allowed; a read between the two is refused as a
	read before the loop.
	"""
	allowed = set()
	slots = set()
	inits: Dict[str, List[tuple]] = {}
	for info in loop_levels.values():
		if not info.counter_slot:
			continue
		slots.add(info.counter_slot)
		allowed.add((info.init_block, info.counter_slot))
		inits.setdefault(info.counter_slot, []).append((info.init_block, set(info.nodes)))
		for latch, step in info.latches.items():
			if step:
				allowed.add((latch, info.counter_slot))
	successors = {block: list(info['successors']) for block, info in cfg.items()} if cfg else {}
	entry = next(iter(ir.blocks), None)
	for block, lines in ir.blocks.items():
		for line in lines:
			store = _STORE.match(line)
			if store and store.group('ptr') in slots and (block, store.group('ptr')) not in allowed:
				if cfg and all(block not in members and _dominates(successors, entry, block, init_block)
						for init_block, members in inits[store.group('ptr')]):
					continue
				raise NotImplementedError(
					f"block {block}: {store.group('ptr')} is a loop counter, which the "
					f"address unit owns, but is also assigned here (a counter initialised in "
					f"two places, as by if/else, is not supported: initialise it once): {line.strip()}")


def advanced_register_name(level: str, info, latch: str) -> str:
	"""
	The register holding a counter after a latch advanced it: %i<level>_next
	for the loop's primary latch, %i<level>_next_<block> for another.
	"""
	return f"%i{level}_next" if latch == info.exit else f"%i{level}_next_{latch}"


def _stores_slot(ir: IRSource, block: str, slot: str) -> bool:
	return any(_STORE.match(line) and _STORE.match(line).group('ptr') == slot
		for line in ir.lines(block))


def _successors_of(predecessors: Dict[str, List[str]]) -> Dict[str, List[str]]:
	successors: Dict[str, List[str]] = {}
	for block, preds in predecessors.items():
		successors.setdefault(block, [])
		for pred in preds:
			successors.setdefault(pred, []).append(block)
	return successors


def _dominates(successors: Dict[str, List[str]], entry: str, block: str, target: str) -> bool:
	"""Whether every path from the entry to `target` passes through `block`."""
	if block == target:
		return True
	seen = {entry}
	work = [entry]
	while work:
		current = work.pop()
		if current == block:
			continue
		if current == target:
			return False
		for successor in successors.get(current, []):
			if successor not in seen:
				seen.add(successor)
				work.append(successor)
	return True


def _tag_level(tag: str) -> str:
	return re.match(r'(?:%i|init:)(\d+)', tag).group(1)


def counter_level_for(loop_levels, by_slot, position, slot: str, block: str) -> str:
	"""
	The loop whose counter a load of `slot` in `block` is: the innermost
	of the loops on that slot containing the block, or, outside them,
	the last one whose header precedes the block.
	"""
	candidates = by_slot[slot]
	containing = [lvl for lvl in candidates if block in loop_levels[lvl].nodes]
	if containing:
		return min(containing, key=lambda lvl: len(loop_levels[lvl].nodes))
	before = [lvl for lvl in candidates
		if position.get(loop_levels[lvl].header, -1) <= position.get(block, -1)]
	if before:
		return max(before, key=lambda lvl: position.get(loop_levels[lvl].header, -1))
	raise NotImplementedError(
		f"block {block} reads loop counter {slot} before any loop that advances it "
		f"has run; the address unit holds no value for it there (read it after the "
		f"loop, or keep the value in another variable)")


def _counter_phases(ir: IRSource, slot: str, levels: List[str], loop_levels, cfg, position,
			reloads: Dict[str, List[str]], entry_names: Dict[tuple, str]) -> Dict[str, str]:
	"""
	{load register: name} for the loads of a counter slot in blocks the
	counter enters with a value other than the one its loop's header
	loaded, and, in `entry_names`, {(level, block): name} for the value
	the counter has on entry to every block reached at all.

	Along every edge out of a block the counter is one of: what a
	header loaded (%i<level>), what a latch advanced (%i<level>_next or
	%i<level>_next_<latch>), or what an initialising store put in the
	slot (init:<level>). Tags are propagated forward over the control
	flow graph, stopping at the headers of the loops on this slot (they
	reload it) and at any other store to it. A block whose incoming
	tags agree on a value other than the header's reads that value:
	`for (;;) { ...; k++; if (k >= n) break; }` leaves from the latch
	after the update, so the block after the loop reads %i<level>_next
	(naming it %i<level>, the header's load, read the previous
	iteration's value), and `k++; if (a[k] > 0) continue; c[k] = 1;`
	reads the advanced value in a body block. A block whose incoming
	tags disagree -- left before and after the update, or reached both
	by skipping the loop (init) and by leaving it -- reads the slot
	again on entry, as %i<level>_at_<block>; the address unit keeps the
	slot current, so the reload is right whichever way it came, and
	those blocks are listed in `reloads`. Tags from two different loops
	on one slot cannot be reconciled (the address unit keeps one slot
	per loop) and are refused.

	The name on entry matters for a latch too: its update must add to
	the value the block was entered with, not to the header's load.
	"""
	headers = {loop_levels[lvl].header: lvl for lvl in levels}
	inits = {loop_levels[lvl].init_block: lvl for lvl in levels}
	by_slot = {slot: levels}

	def carried(block: str):
		"""The tag every edge out of `block` carries, or None to pass on."""
		for lvl in levels:
			if loop_levels[lvl].latches.get(block):
				return advanced_register_name(lvl, loop_levels[lvl], block)
		if block in headers:
			return f"%i{headers[block]}"
		if block in inits:
			return f"init:{inits[block]}"
		if _stores_slot(ir, block, slot):
			return 'stop'		# a store the ownership check refuses, or a dead one before the init
		return None

	tags: Dict[str, set] = {block: set() for block in cfg}
	work = list(cfg)
	while work:
		block = work.pop()
		out = carried(block)
		if out == 'stop':
			continue
		outgoing = {out} if out else tags[block]
		for successor in cfg[block]['successors']:
			if successor in headers or successor not in tags:
				continue
			if not outgoing <= tags[successor]:
				tags[successor] |= outgoing
				work.append(successor)

	mapping: Dict[str, str] = {}
	for block, incoming in tags.items():
		if not incoming:
			continue
		loads = []
		for line in ir.lines(block):
			store = _STORE.match(line)
			if store and store.group('ptr') == slot:
				break		# what follows the store is named by the latch or init rule
			load = _LOAD.match(line)
			if load and load.group('ptr') == slot:
				loads.append(load.group('dst'))
		if not loads:
			continue		# nothing here reads the counter; the tags just pass through
		arriving = {_tag_level(tag) for tag in incoming}
		if len(arriving) > 1:
			# Values of two loops on one variable meet here (a `goto` out
			# of the first loop past the second). The loops on a variable
			# share one slot in the address units, as they share one
			# variable in the source, and that slot always holds what the
			# path taken last stored: the block reads it again.
			canonical = min(levels, key=int)
			name = f"%i{canonical}_at_{block}"
			reloads.setdefault(block, []).append(canonical)
			for lvl in arriving:
				entry_names[(lvl, block)] = name
			for reg in loads:
				mapping[reg] = name
			continue
		level = arriving.pop()
		try:
			natural = counter_level_for(loop_levels, by_slot, position, slot, block)
		except NotImplementedError:
			natural = None
		if incoming == {f"%i{level}"} and level == natural:
			entry_names[(level, block)] = f"%i{level}"
			continue
		if len(incoming) == 1:
			tag = next(iter(incoming))
			name = loop_levels[level].init if tag.startswith('init:') else tag
		else:
			name = f"%i{level}_at_{block}"
			reloads.setdefault(block, []).append(level)
		entry_names[(level, block)] = name
		for reg in loads:
			mapping[reg] = name
	return mapping


def map_advanced_registers(ir: IRSource, loop_levels, cfg=None,
			reloads: Optional[Dict[str, List[str]]] = None, block_order: List[str] = (),
			entry_names: Optional[Dict[tuple, str]] = None) -> Dict[str, str]:
	"""
	{register: name} for loads of a counter that follow its latch update,
	or its initialisation, or that sit in a block the counter enters with
	another value than its header's load (see _counter_phases, which also
	fills `reloads`, {block: [level, ...]}, with the blocks that read the
	slot again, and `entry_names`, {(level, block): name}).

	The AGU keeps a counter in %i<level> from the header's load until the
	latch advances it into %i<level>_next; a source load of the slot
	after that store carries the advanced value, so it is named after it.
	A load after the initialising store carries the initial value (a
	literal or a register).
	"""
	mapping: Dict[str, str] = {}
	if cfg is not None:
		position = {block: index for index, block in enumerate(block_order)}
		by_slot: Dict[str, List[str]] = {}
		for level, info in loop_levels.items():
			if info.counter_slot:
				by_slot.setdefault(info.counter_slot, []).append(level)
		for slot, levels in by_slot.items():
			mapping.update(_counter_phases(ir, slot, levels, loop_levels, cfg, position,
				reloads if reloads is not None else {},
				entry_names if entry_names is not None else {}))
	for level, info in loop_levels.items():
		if not info.counter_slot:
			continue
		# In the block that initialises the counter, a load after the
		# store reads the initial value; %i<level> does not exist yet
		# there, the header defines it.
		current = None
		for line in ir.lines(info.init_block):
			store = _STORE.match(line)
			if store and store.group('ptr') == info.counter_slot:
				current = store.group('value')
				continue
			load = _LOAD.match(line)
			if load and load.group('ptr') == info.counter_slot and current is not None:
				mapping[load.group('dst')] = current
		for latch, step in info.latches.items():
			if not step:
				continue
			name = advanced_register_name(level, info, latch)
			stored = False
			for line in ir.lines(latch):
				store = _STORE.match(line)
				if store and store.group('ptr') == info.counter_slot:
					stored = True
					continue
				load = _LOAD.match(line)
				if stored and load and load.group('ptr') == info.counter_slot:
					mapping[load.group('dst')] = name
	return mapping


def collect_special_operations(ir: IRSource) -> Dict[str, Dict]:
	"""
	{output register: description} for the instructions whose node list
	entry does not say enough: casts (their types), calls (callee, typed
	arguments, return type) and selects (their type).
	"""
	special: Dict[str, Dict] = {}
	cast = re.compile(
		rf'^\s*(?P<dst>{_REG})\s*=\s*(?P<op>trunc|zext|sext|fptrunc|fpext|fptoui|fptosi|uitofp|sitofp)'
		rf'\s+(?:(?:nneg|nuw|nsw)\s+)*(?P<from>\S+)\s+(?P<src>{_OPERAND})\s+to\s+(?P<to>\S+)')
	call = re.compile(
		rf'^\s*(?P<dst>{_REG})\s*=\s*(?:(?:tail|musttail|notail)\s+)?call\s+(?P<ret>[^@]+?)\s*(?P<callee>@[-\w.$]+)\s*\((?P<args>.*)\)\s*(?:#\d+)?\s*$')
	negate = re.compile(
		rf'^\s*(?P<dst>{_REG})\s*=\s*fneg\s+(?:(?:fast|nnan|ninf|nsz|arcp|contract|afn|reassoc)\s+)*'
		rf'(?P<type>\S+)\s+(?P<src>{_OPERAND})\s*$')
	select = re.compile(
		rf'^\s*(?P<dst>{_REG})\s*=\s*select\s+i1\s+(?P<cond>{_OPERAND})\s*,\s*(?P<type>\S+)\s+'
		rf'(?P<lhs>{_OPERAND})\s*,\s*\S+\s+(?P<rhs>{_OPERAND})')
	for block_id, lines in ir.blocks.items():
		for line in lines:
			match = cast.match(line)
			if match:
				special[match.group('dst')] = {'op': match.group('op'), 'inputs': [match.group('src')],
					'from': match.group('from'), 'to': match.group('to'), 'block_id': block_id}
				continue
			match = negate.match(line)
			if match:
				special[match.group('dst')] = {'op': 'fneg', 'inputs': [match.group('src')],
					'type': match.group('type'), 'block_id': block_id}
				continue
			match = call.match(line)
			if match:
				args = []
				for arg in split_top_level(match.group('args')):
					tokens = arg.split()
					if len(tokens) >= 2:
						if tokens[-1].startswith('@') or '(' in arg or _is_pointer_type(leading_type(arg)):
							raise NotImplementedError(
								f"block {block_id}: a call argument that is an address or a "
								f"constant expression cannot be carried by the datapath: {line.strip()}")
						args.append((leading_type(arg), tokens[-1]))
				ret = _return_type(match.group('ret'))
				# Only LLVM intrinsics with a scalar result can be evaluated
				# by the datapath; a call to any other function has no body
				# here and was carried as a `call` nothing could realise.
				if not match.group('callee').startswith('@llvm.'):
					raise NotImplementedError(
						f"block {block_id}: a call to {match.group('callee')} cannot be carried; "
						f"only LLVM intrinsics with a scalar result (@llvm.smax.i32, @llvm.fabs.f64, "
						f"...) are computed by the datapath: {line.strip()}")
				special[match.group('dst')] = {'op': 'call', 'callee': match.group('callee'),
					'ret': ret, 'args': args,
					'inputs': [value for _, value in args], 'block_id': block_id}
				continue
			match = select.match(line)
			if match:
				special[match.group('dst')] = {'op': 'select', 'type': match.group('type'),
					'inputs': [match.group('cond'), match.group('lhs'), match.group('rhs')],
					'block_id': block_id}
				continue
			if re.match(rf'^\s*(?:{_REG}\s*=\s*)?(?:(?:tail|musttail|notail)\s+)?call\b[^@]*%[\w.]+\s*\(', line) and '@' not in line.split('(')[0]:
				raise NotImplementedError(
					f"block {block_id}: a call through a pointer cannot be carried by the "
					f"datapath: {line.strip()}")
			if re.match(r'^\s*(?:(?:tail|musttail|notail)\s+)?call\b', line):
				what = ("an aggregate initialiser (`int t[4] = {...}` becomes a memcpy)"
					if 'llvm.memcpy' in line or 'llvm.memset' in line
					else "a call whose result is not used")
				raise NotImplementedError(
					f"block {block_id}: {what} has no place in the datapath: {line.strip()}")
	return special


_CALL_ATTRIBUTES = {'tail', 'fastcc', 'ccc', 'noundef', 'zeroext', 'signext', 'inreg',
	'nonnull', 'fast', 'nnan', 'ninf', 'nsz', 'arcp', 'contract', 'afn', 'reassoc'}


def _return_type(head: str) -> str:
	"""
	The result type of a call, from the text between `call` and the callee:
	`i32`, `noundef i32`, or the varargs form `i32 (i8*, ...)`, whose
	result is the type before the parenthesis.
	"""
	text = head.strip()
	if text.endswith(')'):
		# A function type: `i32 (i8*, ...)`; the result is what precedes it.
		depth = 0
		for index in range(len(text) - 1, -1, -1):
			if text[index] == ')':
				depth += 1
			elif text[index] == '(':
				depth -= 1
				if depth == 0:
					text = text[:index].strip()
					break
	tokens = [t for t in text.split() if t not in _CALL_ATTRIBUTES and not t.startswith('cc')]
	type_str = tokens[-1] if tokens else 'i32'
	if type_str[:1] in '[{<':
		raise NotImplementedError(f"a call returning an aggregate ({type_str}) cannot be carried")
	if _is_pointer_type(type_str):
		raise NotImplementedError(
			f"a call returning an address ({type_str}) cannot be carried: the generated "
			f"programs address only named memory objects")
	return type_str


def map_index_registers(ir: IRSource, loop_levels, block_order: List[str],
			renamed=()) -> Dict[str, str]:
	"""
	{register: loop level} for every register that carries a counter.

	The counter's alloca and every load from it anywhere in the program
	name the same quantity, which the AGU owns as %i<level>. A cast of
	such a load is a value of another type, computed by whichever
	program needs it, and is not mapped: naming it %i<level> made an
	i64 store or bound an i32. Mapping by slot rather than by walking a
	loop's own blocks means a load of the outer counter inside the inner
	body is found too.

	Two loops in sequence may share a slot, as `for (i = ...)` twice over
	the same variable does. A load then belongs to the innermost of those
	loops containing its block, or, outside them, to the last such loop
	whose header precedes the block. Loads in `renamed` -- those that
	follow the counter's initialisation or its latch update, which the
	generators name otherwise -- are not mapped.
	"""
	position = {block: index for index, block in enumerate(block_order)}
	by_slot: Dict[str, List[str]] = {}
	for level, info in loop_levels.items():
		if info.counter_slot:
			by_slot.setdefault(info.counter_slot, []).append(level)

	def level_for(slot: str, block: str) -> str:
		return counter_level_for(loop_levels, by_slot, position, slot, block)

	mapping: Dict[str, str] = {}
	for slot, levels in by_slot.items():
		mapping[slot] = levels[0]
	for block, lines in ir.blocks.items():
		for line in lines:
			load = _LOAD.match(line)
			if load and load.group('ptr') in by_slot and load.group('dst') not in renamed:
				mapping[load.group('dst')] = level_for(load.group('ptr'), block)
	return mapping
