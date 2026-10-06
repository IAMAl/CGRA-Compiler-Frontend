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
Datapath program generation.

The datapath does the arithmetic. It reads the values the AGU programs
load, under the AGU's names (%load_<object>_<block>_<stream>), and hands
back the values the AGU programs store, branch on, or initialise and
bound their counters with. Scalars no loop touches have no address
stream, so the datapath declares and carries those itself.

The file is a flat instruction list with one `; block <id>` comment per
basic block, so each group can be placed against the AGU's control flow.
"""
from typing import Dict, List

from funcs.analyzer_compute_path import ARITHMETIC, CASTS, UNARY
from utils.IRNormalize import natural_alignment


class DataPathGenerator:
	DEFAULT_ELEMENT_TYPE = "i32"

	def __init__(self, analysis_result: Dict, r_file_path: str, r_name: str):
		self.r_path = r_file_path
		self.r_name = r_name
		self.loop_levels = analysis_result['loop_levels']
		self.operations = analysis_result['compute_info']['operations']
		# Element types from the IR declarations.
		self.array_element_types = analysis_result.get('array_element_types', {})
		# {block: {array: [ArrayAccess, ...]}}, shared with the AGU so both
		# sides name the same access the same way.
		self.array_accesses = analysis_result.get('array_accesses', {})
		# Source registers holding a loop counter. The AGU owns those
		# values and calls them %i<level>.
		self.index_reg_to_loop_level = analysis_result.get('index_reg_to_loop_level', {})
		self.advanced_registers = analysis_result.get('advanced_registers', {})
		# The type each counter has: %i<level> is its slot's type.
		slot_types = analysis_result.get('slot_types', {})
		self.counter_types = {level: slot_types.get(info.counter_slot, 'i32')
			for level, info in self.loop_levels.items() if info.counter_slot}
		# Control flow order of every block.
		self.cfg_block_order = analysis_result.get('control_flow', {}).get('block_order', [])
		self.terminators = analysis_result.get('control_flow', {}).get('terminators', {})
		# {block: [ScalarAccess, ...]} for scalars the datapath must carry.
		self.scalar_accesses = analysis_result.get('scalar_accesses', {})
		# {slot: declared type} for every scalar local and global.
		self.slot_types = analysis_result.get('slot_types', {})
		# {block: [register, ...]} the AGU programs read from the datapath.
		self.agu_consumed = analysis_result.get('agu_consumed', {})

	# ------------------------------------------------------------------
	# Lookups
	# ------------------------------------------------------------------

	def element_type(self, array_name: str) -> str:
		"""LLVM element type of one array, or the fallback."""
		return self.array_element_types.get(array_name, self.DEFAULT_ELEMENT_TYPE)

	def slot_type(self, slot: str) -> str:
		return self.slot_types.get(slot, self.DEFAULT_ELEMENT_TYPE)

	def scalar_slots(self) -> List[str]:
		"""
		Scalars the datapath owns, in first-seen order.

		Loop counters live in the AGU under the name %i<level>, so they
		are excluded: only values the datapath itself computes remain.
		"""
		slots: List[str] = []
		for block_id in self.cfg_block_order or self.scalar_accesses:
			for access in self.scalar_accesses.get(str(block_id), []):
				if access.slot in self.index_reg_to_loop_level:
					continue
				if access.slot not in slots:
					slots.append(access.slot)
		return slots

	def scalar_ops_in(self, block_id: str) -> List:
		"""Scalar loads and stores of this block, minus the loop counters."""
		owned = set(self.scalar_slots())
		return [a for a in self.scalar_accesses.get(str(block_id), []) if a.slot in owned]

	def stores_in(self, block_id: str) -> List:
		"""Every array store this block performs, in stream order."""
		found = []
		for entries in self.array_accesses.get(str(block_id), {}).values():
			found += [a for a in entries if a.kind == 'store']
		return sorted(found, key=lambda a: (a.array, a.index))

	def loads_in(self, block_id: str) -> Dict[str, object]:
		"""{source register: ArrayAccess} for every array load of this block."""
		found: Dict[str, object] = {}
		for entries in self.array_accesses.get(str(block_id), {}).values():
			for access in entries:
				if access.kind == 'load':
					found[access.value_reg] = access
		return found

	def map_operand(self, operand: str, reg_name_mapping: Dict[str, str], computed=()) -> str:
		"""
		Rewrite one operand into the name the generated code uses.

		A loaded array element becomes the AGU's %load_ register; a loop
		counter becomes %i<level>; anything else is passed through. A
		value the datapath computes itself keeps its name even when it
		carries a counter: `sext i32 %i1 to i64` is the datapath's, and
		replacing it with %i1 turned the i64 arithmetic on it into i32.
		"""
		seen = set()
		while operand in self.advanced_registers and operand not in seen:
			# An advanced counter, or the counter's initial value -- itself
			# a literal, a load, or a value with a name of its own here.
			seen.add(operand)
			operand = self.advanced_registers[operand]
		if operand in reg_name_mapping:
			return reg_name_mapping[operand]
		if operand in computed:
			return operand
		level = self.index_reg_to_loop_level.get(operand)
		return f'%i{level}' if level else operand

	def _block_order(self, blocks) -> List[str]:
		"""Control flow order first, then anything left in numeric order."""
		ordered = [b for b in self.cfg_block_order if b in blocks]
		remaining = sorted((b for b in blocks if b not in ordered),
				key=lambda x: int(x) if str(x).isdigit() else float('inf'))
		return ordered + remaining

	# ------------------------------------------------------------------
	# Generation
	# ------------------------------------------------------------------

	def ComputeDataPath(self) -> Dict:
		"""Generate the datapath program: {'code': [line, ...]}."""
		result = {'code': []}
		code = result['code']

		block_operations: Dict[str, List[Dict]] = {}
		for op in self.operations:
			block_operations.setdefault(str(op['block_id']), []).append(op)

		# A block appears when it has arithmetic, an array access or a
		# scalar access. A loop header's compare alone does not count: the
		# AGU performs that compare, so the group would be empty.
		blocks = {b for b, ops in block_operations.items()
			if any(op['op'] not in ('icmp', 'fcmp', 'sext', 'zext', 'trunc') for op in ops)}
		blocks |= set(self.array_accesses)
		blocks |= {b for b in self.scalar_accesses if self.scalar_ops_in(b)}
		blocks |= {b for b, regs in self.agu_consumed.items() if regs}
		# The block that returns: the datapath returns the result, or
		# `ret void`, so the verifier sees where the program ends.
		blocks |= {b for b, term in self.terminators.items() if term['kind'] == 'ret'}
		block_order = self._block_order(blocks)

		# Scalars the datapath owns: locals are declared here, globals
		# are referenced as the externals they are.
		# The counters the address units own, for whoever checks that
		# every scalar of the source is accounted for somewhere.
		for level in sorted(self.loop_levels, key=int):
			slot = self.loop_levels[level].counter_slot
			if slot:
				code.append(f"; counter {slot} = %i{level}")
		scalar_slots = self.scalar_slots()
		if scalar_slots:
			for slot in scalar_slots:
				if slot.startswith('@'):
					code.append(f"{slot} = external global {self.slot_type(slot)}, align {natural_alignment(self.slot_type(slot))}")
				else:
					code.append(f"{slot} = alloca {self.slot_type(slot)}, align {natural_alignment(self.slot_type(slot))}")
			code.append("")

		for block_id in block_order:
			lines = self._generate_block(block_id, block_operations.get(block_id, []))
			if not lines:
				continue		# nothing of the datapath's here: no group
			code.append(f"; block {block_id}")
			code.extend(lines)
			code.append("")

		return result

	def _generate_block(self, block_id: str, ops: List[Dict]) -> List[str]:
		code: List[str] = []
		loads = self.loads_in(block_id)
		array_stores = self.stores_in(block_id)
		scalar_ops = self.scalar_ops_in(block_id)

		# Every load the AGU performs is available under the AGU's name,
		# including a scalar the loop touches: those are memory objects
		# too, and the datapath reads them under the name the AGU gave them.
		reg_name_mapping = {reg: access.load_name() for reg, access in loads.items()}

		# Only work whose result reaches memory or the AGU is emitted.
		# Walking the block backwards from its stores, the branch condition
		# and the counter values the AGU takes from here keeps exactly the
		# instructions those depend on and drops the rest: the `k + 1` that
		# only feeds an address (the AGU computes those itself), and a
		# latch's counter update (the AGU emits that too).
		binary = [op for op in ops
			if (op['op'] in ARITHMETIC and len(op['inputs']) > 1) or op['op'] in UNARY]
		live = {a.value_reg for a in array_stores}
		live |= {a.value_reg for a in scalar_ops if a.kind == 'store'}
		live |= set(self.agu_consumed.get(block_id, []))
		kept: List[Dict] = []
		for op in reversed(binary):
			if op['output'] in live:
				kept.append(op)
				live.update(op['inputs'])
		kept.reverse()
		defined_by = {op['output']: op for op in kept}
		computed = set(defined_by)

		# Every operation is emitted at the type the source wrote on it.
		def operation_type(op: Dict) -> str:
			return op['type']

		# The loads the arithmetic needs, in first-use order.
		needed = dict.fromkeys(operand for op in kept for operand in op['inputs']
			if operand in loads)
		for reg in needed:
			access = loads[reg]
			elem = self.element_type(access.array)
			code.append(f"{access.load_name()} = load {elem}, {elem}* "
						f"%gep_{access.array}_{access.suffix()}, align {natural_alignment(elem)}")

		# Emitted on demand rather than all at once, because a scalar
		# slot can be written and then read again in the same block.
		emitted = set()

		def emit_computation(reg: str) -> None:
			"""Emit the operation defining reg, after the ones it needs (iteratively)."""
			stack = [(reg, False)]
			while stack:
				current, expanded = stack.pop()
				op = defined_by.get(current)
				if op is None or id(op) in emitted:
					continue
				if not expanded:
					stack.append((current, True))
					stack.extend((operand, False) for operand in reversed(op['inputs']))
					continue
				emitted.add(id(op))
				mapped = [self.map_operand(i, reg_name_mapping, computed) for i in op['inputs']]
				opcode = op['op']
				if opcode in CASTS:
					code.append(f"{op['output']} = {opcode} {op['from']} {mapped[0]} to {op['to']}")
				elif opcode == 'fneg':
					code.append(f"{op['output']} = fneg {op['type']} {mapped[0]}")
				elif opcode == 'call':
					args = ', '.join(f"{type_str} {value}" for (type_str, _), value in zip(op['args'], mapped))
					code.append(f"{op['output']} = call {op['ret']} {op['callee']}({args})")
				elif opcode == 'select':
					code.append(f"{op['output']} = select i1 {mapped[0]}, {op['type']} {mapped[1]}, "
								f"{op['type']} {mapped[2]}")
				else:
					if op.get('predicate'):
						opcode = f"{opcode} {op['predicate']}"
					code.append(f"{op['output']} = {opcode} {operation_type(op)} {mapped[0]}, {mapped[1]}")

		# Scalar loads and stores keep their source order, with the
		# arithmetic a store needs emitted just before it.
		for access in scalar_ops:
			elem = self.slot_type(access.slot)
			if access.kind == 'load':
				code.append(f"{access.value_reg} = load {elem}, {elem}* {access.slot}, align {natural_alignment(elem)}")
			else:
				emit_computation(access.value_reg)
				value = self.map_operand(access.value_reg, reg_name_mapping, computed)
				code.append(f"store {elem} {value}, {elem}* {access.slot}, align {natural_alignment(elem)}")

		for op in kept:
			emit_computation(op['output'])

		# Each store keeps the value the source stored through it.
		for access in array_stores:
			elem = self.element_type(access.array)
			value = self.map_operand(access.value_reg, reg_name_mapping, computed)
			code.append(f"store {elem} {value}, {elem}* %gep_{access.array}_{access.suffix()}, align {natural_alignment(elem)}")

		# The function's result is the datapath's to return.
		term = self.terminators.get(block_id)
		if term and term['kind'] == 'ret':
			if term['value']:
				emit_computation(term['value'])
				code.append(f"ret {term['type']} {self.map_operand(term['value'], reg_name_mapping, computed)}")
			else:
				code.append("ret void")

		return code
