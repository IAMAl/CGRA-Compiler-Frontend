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
AGU program generation.

One program per memory object. Each reproduces the source's control flow
graph block for block -- every AGU program has the same control flow, so
the streams stay in lockstep -- and computes the addresses its object is
accessed through, performing the loads and stores at those addresses.

A block is emitted as: the load of its loop counter if it is a header,
its address streams, the counter initialisations the source performs
there, the counter updates if it is a loop latch, and its terminator. A
loop header whose source compares the counter ends in that compare;
every other block ends the way the source block does -- a jump, a
conditional branch on a value the datapath computes, a switch on one,
or the branch to `ret`. Subscripts are evaluated from their source
expression: a loop counter plus a constant has a register of its own
(`%off1_...`), anything else is computed step by step (`%idx0_...`)
from counters, literals and values other programs provide.
"""
import copy
import re

from funcs.analyzer_ir_access import advanced_register_name
from utils.IRNormalize import natural_alignment
from typing import Any, Dict, List, Optional, Set, Tuple


DEBUG = False


def _bits(type_str: str) -> int:
	"""Width of an integer type, for choosing between sext and trunc."""
	match = re.fullmatch(r'i(\d+)', type_str)
	return int(match.group(1)) if match else 64


class AGUCode:
	"""One generated AGU program."""

	def __init__(self, ir_code: List[str]):
		self.ir_code = ir_code

	def __getitem__(self, key: str) -> Any:
		if key == 'code':
			return self.ir_code
		raise KeyError(f"Invalid key: {key}")

	def get(self, key: str, default: Any = None) -> Any:
		try:
			return self[key]
		except KeyError:
			return default


class AGUGenerator:
	# Element type used when the IR declaration did not say.
	DEFAULT_ELEMENT_TYPE = "i32"

	def __init__(self, analysis_result: Dict, r_file_path: str, r_name: str) -> None:
		self.debug = DEBUG
		print("Initializing AGU Generator")
		self.r_path = r_file_path
		self.r_name = r_name

		control_flow = analysis_result.get('control_flow', {})
		self.cfg_block_order: List[str] = control_flow.get('block_order', [])
		self.terminators: Dict[str, Dict] = control_flow.get('terminators', {})
		self.array_element_types = analysis_result.get('array_element_types', {})
		# {block: {array: [ArrayAccess, ...]}} read from the IR: one entry
		# per access, carrying its dimension order and subscript expressions.
		self.array_accesses = analysis_result.get('array_accesses', {})
		self.array_info = copy.deepcopy(analysis_result['array_info'])
		self.loop_levels = analysis_result['loop_levels']
		# Registers that carry a loop counter; the AGU calls them %i<level>,
		# or %i<level>_next once the latch has advanced the counter.
		self.index_reg_to_loop_level = analysis_result.get('index_reg_to_loop_level', {})
		self.advanced_registers = analysis_result.get('advanced_registers', {})
		self.counter_reloads = analysis_result.get('counter_reloads', {})
		self.counter_entry_names = analysis_result.get('counter_entry_names', {})
		# A counter is computed at its slot's type (`long k` is i64).
		slot_types = analysis_result.get('slot_types', {})
		self.counter_types: Dict[str, str] = {
			level: slot_types.get(info.counter_slot, 'i32')
			for level, info in self.loop_levels.items() if info.counter_slot}

		# Scalars the loop touches are memory objects too. They have no
		# declaration to read dimensions from, so they are one element.
		self.scalar_objects: Set[str] = set()
		for arrays in self.array_accesses.values():
			for name, entries in arrays.items():
				if entries and entries[0].scalar:
					self.scalar_objects.add(name)

		self.counted = {level: info for level, info in self.loop_levels.items() if info.counter_slot}
		# Loops in sequence over one source variable share one slot, named
		# after the first of them: the source has one variable, and a
		# block reached from either loop (a `goto` past the second) can
		# then read what the path taken stored.
		self.slot_level: Dict[str, str] = {}
		for level in sorted(self.counted, key=int):
			first = next(lvl for lvl in sorted(self.counted, key=int)
				if self.counted[lvl].counter_slot == self.counted[level].counter_slot)
			self.slot_level[level] = first
		self.headers = {info.header: level for level, info in self.loop_levels.items()}
		# {latch block: [(level, step), ...]}; a step is [opcode, operands]
		# or None for a latch that does not touch the counter.
		self.latch_steps: Dict[str, List[Tuple[str, Any]]] = {}
		for level in sorted(self.counted, key=int):
			for latch, step in self.loop_levels[level].latches.items():
				self.latch_steps.setdefault(latch, []).append((level, step))
		self.inits: Dict[str, List[str]] = {}
		for level in sorted(self.counted, key=int):
			self.inits.setdefault(self.loop_levels[level].init_block, []).append(level)

		print(f"  Arrays: {list(self.array_info.keys())}")
		print(f"  Dimensions: {dict((a, info['dimensions']) for a, info in self.array_info.items())}")
		print(f"  Loop levels: {list(self.loop_levels.keys())}")

	# ------------------------------------------------------------------
	# Lookups
	# ------------------------------------------------------------------

	def element_type(self, array_name: str) -> str:
		"""LLVM element type of one array, taken from its IR declaration."""
		return self.array_element_types.get(array_name, self.DEFAULT_ELEMENT_TYPE)

	def accesses_for(self, array_name: str, block_id: str) -> List[Any]:
		"""Every access this block makes to this array, in source order."""
		return self.array_accesses.get(str(block_id), {}).get(array_name, [])

	def streams_for(self, array_name: str, block_id: str) -> List[List[Any]]:
		"""Accesses grouped into address streams, in source order."""
		streams: Dict[int, List[Any]] = {}
		for access in self.accesses_for(array_name, block_id):
			streams.setdefault(access.index, []).append(access)
		return [streams[key] for key in sorted(streams)]

	def block_order(self) -> List[str]:
		"""Every block in control flow order, the ret pseudo-block excluded."""
		order = [b for b in self.cfg_block_order if b != 'ret']
		for block in self.array_accesses:
			if block not in order:
				order.append(block)
		return order

	def _value_name(self, block_id: str, reg: str) -> str:
		"""
		The name a source register has in the generated programs.

		A value loaded from an array is the AGU's %load_ register for that
		access; a loop counter is %i<level>; a literal, or a value the
		datapath computes, keeps its name. Emitting the source register of
		a copy `b[k][j] = a[i][k]` verbatim left the store referring to a
		register no generated program defines.
		"""
		for entries in self.array_accesses.get(str(block_id), {}).values():
			for access in entries:
				if access.kind == 'load' and access.value_reg == reg:
					return access.load_name()
		if reg in self.advanced_registers:
			# The advanced counter, or the counter's initial value --
			# itself a literal or a source register with a name here.
			mapped = self.advanced_registers[reg]
			return mapped if mapped == reg else self._value_name(block_id, mapped)
		level = self.index_reg_to_loop_level.get(reg)
		if level:
			return f"%i{level}"
		return reg

	def _build_array_type(self, array_name: str) -> str:
		"""
		The declared LLVM type of an array, e.g. [32 x [32 x i32]]. An
		array reached by pointer has an unknown extent: [0 x <element>].
		"""
		dims = self.array_info.get(array_name, {}).get('dimensions') or []
		if not dims:
			raise RuntimeError(f"array @{array_name} has no known dimensions")
		type_str = self.element_type(array_name)
		for dim in reversed(dims):
			type_str = f"[{dim} x {type_str}]"
		return type_str

	# ------------------------------------------------------------------
	# Address streams
	# ------------------------------------------------------------------

	def _counter_level(self, expr) -> str:
		return (self.index_reg_to_loop_level.get(expr.load_reg)
			or self.index_reg_to_loop_level.get(expr.slot))

	def _expr_type(self, expr) -> Optional[str]:
		"""The type a subscript expression is computed at; None for a literal."""
		if expr.kind == 'lit':
			return None
		if expr.kind == 'counter':
			return self.counter_types.get(self._counter_level(expr), 'i32')
		return expr.type or 'i32'

	def _emit_expr(self, access, expr, code: List[str], count: List[int]) -> str:
		"""Evaluate a subscript expression; returns the operand holding it."""
		if expr.kind == 'lit':
			return str(expr.value)
		if expr.kind == 'counter':
			return f"%i{self._counter_level(expr)}"
		if expr.kind == 'value':
			return self._value_name(access.block, expr.reg)
		if expr.kind == 'cast':
			operand = self._emit_expr(access, expr.args[0], code, count)
			source_type = self._expr_type(expr.args[0]) or expr.type
			if source_type == expr.type:
				return operand
			name = f"%cast{count[0]}_{access.array}_{access.suffix()}"
			count[0] += 1
			code.append(f"  {name} = {expr.op} {source_type} {operand} to {expr.type}")
			return name
		type_str = self._expr_type(expr)
		operands = []
		for arg in expr.args:
			operand = self._emit_expr(access, arg, code, count)
			operands.append(self._coerce(operand, self._expr_type(arg), type_str, access, code, count))
		name = f"%idx{count[0]}_{access.array}_{access.suffix()}"
		count[0] += 1
		code.append(f"  {name} = {expr.op} {type_str} {', '.join(operands)}")
		return name

	def _coerce(self, operand: str, have: Optional[str], want: str, access, code, count) -> str:
		"""Widen or narrow an operand to the type an operation needs."""
		if have is None or have == want:
			return operand
		opcode = 'sext' if _bits(have) < _bits(want) else 'trunc'
		name = f"%cast{count[0]}_{access.array}_{access.suffix()}"
		count[0] += 1
		code.append(f"  {name} = {opcode} {have} {operand} to {want}")
		return name

	def _index_expression(self, access, dim, code: List[str], count: List[int],
			offsets: Dict[str, str]) -> str:
		"""
		Register holding one subscript of an access.

		A loop counter plus a constant (`a[i][k+1]`, `a[i][k-1]`) has a
		register named after the offset, computed once per stream
		(`a[k+1][k+1]` used to define it twice); any other expression is
		evaluated step by step.
		"""
		if not dim.is_simple:
			return self._emit_expr(access, dim.expr, code, count)
		if dim.level is None:
			raise RuntimeError(
				f"block {access.block}: subscript of {access.array} loaded from "
				f"{dim.base_reg} is not driven by a loop counter")
		index_reg = f"%i{dim.level}"
		if not dim.offset:
			return index_reg

		if dim.offset > 0:
			tag, opcode, amount = f"off{dim.offset}", 'add', dim.offset
		else:
			tag, opcode, amount = f"offm{-dim.offset}", 'sub', -dim.offset
		offset_reg = f"%{tag}_{dim.level}_{access.array}_{access.suffix()}"
		if offset_reg not in offsets:
			offsets[offset_reg] = offset_reg
			code.append(f"  {offset_reg} = {opcode} {self.counter_types.get(dim.level, 'i32')} "
						f"{index_reg}, {amount}")
		return offset_reg

	def _emit_address(self, stream: List[Any]) -> List[str]:
		"""
		The address computation of one stream.

		A read-modify-write is one stream: its load and store share an
		address, so the getelementptr is emitted once and both operations
		use it.
		"""
		code: List[str] = []
		access = stream[0]
		array_name = access.array
		suffix = access.suffix()
		count = [0]
		offsets: Dict[str, str] = {}

		subscripts = []
		for dim_no, dim in enumerate(access.dims):
			if dim.is_constant:
				# A literal subscript needs no register and no widening.
				subscripts.append(str(dim.offset))
				continue
			index_reg = self._index_expression(access, dim, code, count, offsets)
			index_type = (self.counter_types.get(dim.level, 'i32') if dim.is_simple
				else self._expr_type(dim.expr))
			if index_type == 'i64':
				subscripts.append(index_reg)		# already the width a subscript has
				continue
			sext_reg = f"%sext_{dim_no}_{array_name}_{suffix}"
			code.append(f"  {sext_reg} = sext {index_type} {index_reg} to i64")
			subscripts.append(sext_reg)

		gep_reg = f"%gep_{array_name}_{suffix}"
		elem = self.element_type(array_name)
		if access.scalar:
			# A scalar is one element, so its address is the object itself.
			code.append(f"  {gep_reg} = getelementptr inbounds {elem}, {elem}* @{array_name}, i64 0")
		else:
			array_type = self._build_array_type(array_name)
			dims = self.array_info[array_name]['dimensions']
			if len(subscripts) != len(dims):
				raise RuntimeError(
					f"block {access.block}: access to @{array_name} has {len(subscripts)} "
					f"subscripts but the array has {len(dims)} dimensions")
			indices_str = "i64 0" + "".join(f", i64 {s}" for s in subscripts)
			code.append(f"  {gep_reg} = getelementptr inbounds {array_type}, "
						f"{array_type}* @{array_name}, {indices_str}")
		return code

	def _emit_operation(self, stream: List[Any], op) -> str:
		"""One load or store of a stream, through its address register."""
		access = stream[0]
		elem = self.element_type(access.array)
		gep_reg = f"%gep_{access.array}_{access.suffix()}"
		if op.kind == 'load':
			return f"  {op.load_name()} = load {elem}, {elem}* {gep_reg}, align {natural_alignment(elem)}"
		value = self._value_name(access.block, op.value_reg)
		return f"  store {elem} {value}, {elem}* {gep_reg}, align {natural_alignment(elem)}"

	def _emit_stream(self, stream: List[Any]) -> List[str]:
		"""Address computation, then every operation on that address."""
		return self._emit_address(stream) + [self._emit_operation(stream, op) for op in stream]

	# ------------------------------------------------------------------
	# Blocks
	# ------------------------------------------------------------------

	def _terminator(self, block_id: str) -> List[str]:
		"""The branch that ends a block."""
		term = self.terminators.get(block_id, {'kind': 'ret'})
		if block_id in self.headers:
			level = self.headers[block_id]
			info = self.loop_levels[level]
			if info.compare_on_counter:
				index_reg = f"i{level}"
				bound = self._value_name(block_id, info.bound)
				# A single-block loop compares the value the source compared:
				# before or after its own update.
				counter = f"%{index_reg}_next" if info.compare_after_update else f"%{index_reg}"
				code = []
				# `icmp slt i64 %sext, %n`: the source converted the counter
				# before comparing; the same casts, in the same order.
				for number, (opcode, from_type, to_type) in enumerate(info.compare_casts):
					name = f"%cmp_{index_reg}" if number == 0 else f"%cmp{number}_{index_reg}"
					code.append(f"  {name} = {opcode} {from_type} {counter} to {to_type}")
					counter = name
				return code + [
					f"  %cond_{index_reg} = icmp {info.predicate} {info.compare_type} {counter}, {bound}",
					f"  br i1 %cond_{index_reg}, label %{info.body_entry}, label %{info.exit_target}",
				]
			# The loop runs on a condition the datapath computes.

		kind = term['kind']
		if kind == 'jump':
			return [f"  br label %{term['target']}"]
		if kind == 'cond':
			cond = self._value_name(block_id, term['cond'])
			return [f"  br i1 {cond}, label %{term['taken']}, label %{term['not_taken']}"]
		if kind == 'switch':
			value = self._value_name(block_id, term['value'])
			cases = ' '.join(f"{term['type']} {literal}, label %{label}"
				for literal, label in term['cases'])
			return [f"  switch {term['type']} {value}, label %{term['default']} [ {cases} ]"]
		return ["  br label %ret"]

	def _emit_block(self, array_name: str, block_id: str, first: bool) -> List[str]:
		code = [f"{block_id}:"]
		if first:
			for level in sorted(self.counted, key=int):
				if self.slot_level[level] == level:
					code.append(f"  %i{level}_ptr = alloca {self.counter_types[level]}, align {natural_alignment(self.counter_types[level])}")

		# A header reads its counter first: its streams, and in a
		# single-block loop its work, use the value the block was entered
		# with; the compare at the end is what decides.
		if block_id in self.headers and self.headers[block_id] in self.counted:
			level = self.headers[block_id]
			ctype = self.counter_types[level]
			code.append(f"  %i{level} = load {ctype}, {ctype}* %i{self.slot_level[level]}_ptr, align {natural_alignment(ctype)}")
		# A block entered with a counter that a latch may or may not have
		# advanced reads the slot, which is always current.
		for level in self.counter_reloads.get(block_id, []):
			if level in self.counted:
				ctype = self.counter_types[level]
				code.append(f"  %i{level}_at_{block_id} = load {ctype}, {ctype}* %i{self.slot_level[level]}_ptr, "
					f"align {natural_alignment(ctype)}")

		# The block's work in the source's order: each stream's address
		# where its first access is, each load and store where the source
		# has it, counter initialisations and latch updates where their
		# stores are. Emitting all streams before the update, or sorting
		# them into early and late by a direct use of %i<level>_next,
		# left a store of a value derived from the advanced counter
		# waiting on an update that came later, and a step read from
		# memory waiting on a load that came later.
		items = []
		for stream in self.streams_for(array_name, block_id):
			items.append((min(op.position for op in stream), 0, 'address', stream))
			for op in stream:
				items.append((op.position, 1, 'operation', (stream, op)))
		for level in self.inits.get(block_id, []):
			items.append((self.loop_levels[level].init_position, 1, 'init', level))
		for level, step in self.latch_steps.get(block_id, []):
			if step is not None:
				items.append((self.loop_levels[level].update_positions[block_id], 1, 'update', level))
		for _, _, kind, payload in sorted(items, key=lambda item: (item[0], item[1])):
			if kind == 'address':
				code.extend(self._emit_address(payload))
			elif kind == 'operation':
				code.append(self._emit_operation(*payload))
			elif kind == 'init':
				# Counters are initialised where the source initialises
				# them, so a loop entered from several places, or run
				# twice, starts right.
				value = self._value_name(block_id, self.loop_levels[payload].init)
				ctype = self.counter_types[payload]
				code.append(f"  store {ctype} {value}, {ctype}* %i{self.slot_level[payload]}_ptr, align {natural_alignment(ctype)}")
			else:
				# A latch advances its loop's counter. A loop with several
				# latches (a `continue`) names each update after the latch;
				# a single-block loop updates before it compares, as the
				# source does.
				level = payload
				info = self.loop_levels[level]
				opcode, operands = dict(self.latch_steps[block_id])[level]
				# The update adds to the value the block was entered with:
				# the header's load, or, when this latch follows another
				# latch's update or reloads the slot, that value.
				entering = self.counter_entry_names.get(level, {}).get(block_id, f"%i{level}")
				operands = [entering if op == '%counter' else self._value_name(block_id, op)
					for op in operands]
				name = advanced_register_name(level, info, block_id)
				ctype = self.counter_types[level]
				code.append(f"  {name} = {opcode} {ctype} {', '.join(operands)}")
				code.append(f"  store {ctype} {name}, {ctype}* %i{self.slot_level[level]}_ptr, align {natural_alignment(ctype)}")

		code.extend(self._terminator(block_id))
		code.append("")
		return code

	# ------------------------------------------------------------------
	# Programs
	# ------------------------------------------------------------------

	def generate(self) -> Dict[str, AGUCode]:
		"""Generate one AGU program per memory object."""
		result: Dict[str, AGUCode] = {}
		print("\nGenerating AGU code")
		order = self.block_order()
		if not order:
			raise RuntimeError("the program has no basic blocks")

		for array_name in self.array_info:
			print(f"\nProcessing array {array_name}")
			code: List[str] = [
				"; ModuleID = 'agu_code'",
				'target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"',
				'target triple = "x86_64-pc-linux-gnu"',
			]

			# The memory object this program addresses.
			if array_name in self.scalar_objects:
				elem_type = self.element_type(array_name)
				code.append(f"@{array_name} = external global {elem_type}, align {natural_alignment(elem_type)}")
			else:
				code.append(f"@{array_name} = external global {self._build_array_type(array_name)}, align 16")
			code.append("")
			code.append(f"define void @{array_name}_agu() #0 {{")

			for position, block_id in enumerate(order):
				code.extend(self._emit_block(array_name, block_id, position == 0))

			code.append("ret:")
			code.append("  ret void")
			code.extend(["}", "", "attributes #0 = { nounwind }"])

			if self.debug:
				for no, line in enumerate(code, 1):
					print(f"{no:4d}: {line}")
			result[array_name] = AGUCode(ir_code=code)

		print("AGU Code generation completed successfully")
		return result
