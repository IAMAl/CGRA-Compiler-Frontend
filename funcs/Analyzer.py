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
Analysis the AGU and datapath generators run on.

Everything about memory objects, loop counters and block terminators is
read from the IR (funcs.analyzer_ir_access); the loop file and the CFG
node list give the loop forest and block order; the per-block node
lists give the arithmetic. The result is one dictionary both
generators consume.
"""
import re
from typing import Dict, List, Set

from funcs.analyzer_models import LoopInfo
from funcs.analyzer_compute_path import collect_operations
from funcs.analyzer_loader import AnalyzerLoader
from funcs.analyzer_loop_analysis import LoopAnalyzer
from utils.Naming import local_array_name, object_name, scalar_param_name
from funcs.analyzer_ir_access import (
	IRSource,
	collect_array_accesses,
	collect_array_declarations,
	collect_scalar_accesses,
	collect_slot_types,
	collect_special_operations,
	collect_terminators,
	check_counter_ownership,
	map_advanced_registers,
	map_index_registers,
	promote_loop_scalars,
	dims_of,
	element_of,
)

__all__ = ['Analyzer', 'LoopInfo']


def _cyclic_blocks(cfg: Dict[str, Dict[str, List[str]]]) -> Set[str]:
	"""
	Blocks that lie on a cycle of the control flow graph.

	Natural loops miss the blocks of an irreducible cycle, but those
	repeat too, so the scalars they touch are streamed like any loop's.
	"""
	# Tarjan's strongly connected components, iteratively: a block is on
	# a cycle when its component has more than one block, or it branches
	# to itself. A search from every block was quadratic in the graph.
	index: Dict[str, int] = {}
	low: Dict[str, int] = {}
	on_stack: Set[str] = set()
	stack: List[str] = []
	cyclic: Set[str] = set()
	counter = 0
	for root in cfg:
		if root in index:
			continue
		work = [(root, iter(cfg[root]['successors']))]
		index[root] = low[root] = counter
		counter += 1
		stack.append(root)
		on_stack.add(root)
		while work:
			block, children = work[-1]
			advanced = False
			for child in children:
				if child not in cfg:
					continue
				if child not in index:
					index[child] = low[child] = counter
					counter += 1
					stack.append(child)
					on_stack.add(child)
					work.append((child, iter(cfg[child]['successors'])))
					advanced = True
					break
				if child in on_stack:
					low[block] = min(low[block], index[child])
			if advanced:
				continue
			work.pop()
			if work:
				parent = work[-1][0]
				low[parent] = min(low[parent], low[block])
			if low[block] == index[block]:
				component = []
				while True:
					member = stack.pop()
					on_stack.discard(member)
					component.append(member)
					if member == block:
						break
				if len(component) > 1 or block in cfg[block]['successors']:
					cyclic.update(component)
	return cyclic


class Analyzer:
	def __init__(self, r_file_path: str, r_name: str):
		self.r_path = r_file_path
		self.r_name = r_name
		# Per-block files carry the base name without the _cfg suffix.
		self.dfg_base_name = r_name[:-4] if r_name.endswith('_cfg') else r_name

		self.loader = AnalyzerLoader(self)
		self.nodes_cache: Dict[str, List[List[str]]] = {}

		self.ir = IRSource(self.r_path, self.dfg_base_name)
		self.array_dims, self.array_element_types = collect_array_declarations(self.ir)
		self.slot_types = collect_slot_types(self.ir, (self.array_dims, self.array_element_types))
		self.pointer_objects = self.ir.pointer_objects
		self.special_operations = collect_special_operations(self.ir)
		self.loops = self.loader._read_loop_structure()
		self.cfg = self.loader._read_cfg_connectivity()
		self.all_nodes = self.loader._collect_all_nodes()

		self.block_order = self.loader.block_order(self.cfg)
		self.loop_levels = LoopAnalyzer(self).analyze()
		self.counter_reloads: Dict[str, List[str]] = {}
		self.counter_entry_names: Dict[tuple, str] = {}
		self.advanced_registers = map_advanced_registers(
			self.ir, self.loop_levels, self.cfg, self.counter_reloads, self.block_order,
			self.counter_entry_names)
		self.index_reg_to_loop_level = map_index_registers(
			self.ir, self.loop_levels, self.block_order, renamed=self.advanced_registers)
		check_counter_ownership(self.ir, self.loop_levels, self.cfg)
		self._check_object_names()
		# The generated programs name counters %i<level>; a source that
		# keeps its value names could use the same spelling for a local.
		taken = [slot for slot in self.slot_types if re.fullmatch(r'%i\d+(?:_ptr|_next.*|_at_.*)?', slot)]
		if taken:
			raise NotImplementedError(
				f"local {taken[0]} has the name the generated programs give a loop "
				f"counter; rename it (or compile without value names)")

	def _check_object_names(self) -> None:
		"""
		Every memory object of the generated programs has one source.

		The names are sanitised (`%n.addr` -> `sn_addr`), so a local
		`n_addr` next to a parameter `n`, a `%5` next to a global `@s5`,
		or a `%t` next to a global `@lt`, would fold two objects into one
		address program without a word.
		"""
		sources: Dict[str, Set[str]] = {}
		parameters = {scalar_param_name(reg) for _, reg in self.ir.scalar_params}
		for slot, type_str in self.slot_types.items():
			if slot.startswith('@'):
				if slot[1:] not in parameters:	# a scalar parameter's input global is its own
					sources.setdefault(slot[1:], set()).add(slot)
			elif type_str.startswith('['):
				sources.setdefault(local_array_name(slot), set()).add(slot)
			elif slot in self.pointer_objects:
				continue		# a pointer parameter's spill slot: the object is the array
			else:
				sources.setdefault(object_name(slot), set()).add(slot)
		for name in self.array_dims:
			if name not in parameters:
				sources.setdefault(name, set()).add('@' + name)
		for reg, name in self.pointer_objects.items():
			if reg in {r for _, r in self.ir.params}:
				sources.setdefault(name, set()).add(reg)
		for _, reg in self.ir.scalar_params:
			sources.setdefault(scalar_param_name(reg), set()).add(reg)
		for name, slots in sources.items():
			if len(slots) > 1:
				raise NotImplementedError(
					f"memory object @{name} would stand for {sorted(slots)}: rename one of them")
		# The programs are files named after their objects: two names
		# that differ only in case would overwrite each other on a
		# case-insensitive filesystem.
		by_case: Dict[str, str] = {}
		for name in sources:
			if name.lower() in by_case and by_case[name.lower()] != name:
				raise NotImplementedError(
					f"memory objects @{by_case[name.lower()]} and @{name} differ only in case; "
					f"their programs' files would collide on a case-insensitive filesystem")
			by_case[name.lower()] = name

	def _check_stream_names(self, array_accesses) -> None:
		"""
		The generated registers are named `<object>_<block>_<stream>` with
		`_` between the parts, and both an object and a block label may
		contain `_`: object `a` in block `loop_retry` and object `a_loop`
		in block `retry` would both define %load_a_loop_retry_0. Two
		address programs then defined one register without a word.
		"""
		owners: Dict[str, tuple] = {}
		for block, arrays in array_accesses.items():
			for array in arrays:
				key = f"{array}_{block}"
				if key in owners and owners[key] != (array, block):
					other = owners[key]
					raise NotImplementedError(
						f"object {array} in block {block} and object {other[0]} in block "
						f"{other[1]} would share the register names *_{key}_<stream>; rename "
						f"the object or the label")
				owners[key] = (array, block)

	def analyze(self) -> Dict:
		"""Analyze the program for the AGU and datapath generators."""
		loop_levels = self.loop_levels
		in_loop = {b for info in loop_levels.values() for b in info.nodes}
		in_loop |= _cyclic_blocks(self.cfg)

		array_accesses, pointer_types = collect_array_accesses(
			self.ir, self.index_reg_to_loop_level, self.slot_types, self.pointer_objects,
			self.advanced_registers, self.ir.global_types)
		self._check_stream_names(array_accesses)
		scalar_accesses = collect_scalar_accesses(self.ir, self.pointer_objects)
		promote_loop_scalars(scalar_accesses, array_accesses, in_loop,
			set(self.index_reg_to_loop_level))

		# One entry per memory object the program addresses: every array
		# it loads from or stores to (global, local, or passed in by
		# pointer), and every scalar the loop touches.
		array_info: Dict[str, Dict] = {}
		element_types = dict(self.array_element_types)
		local_arrays = {local_array_name(slot): type_str
			for slot, type_str in self.slot_types.items() if type_str.startswith('[')}
		for arrays in array_accesses.values():
			for name, entries in arrays.items():
				if name in array_info:
					continue
				if entries[0].scalar:
					if entries[0].ptr_reg not in self.slot_types:
						raise RuntimeError(
							f"scalar {entries[0].ptr_reg} is used but not declared in {self.ir.path}")
					array_info[name] = {'dimensions': []}
					element_types[name] = self.slot_types[entries[0].ptr_reg]
				elif name in local_arrays:
					array_info[name] = {'dimensions': dims_of(local_arrays[name])}
					element_types[name] = element_of(local_arrays[name])
				elif name in pointer_types:
					# An array of unknown extent: a zero-length array of
					# the pointer's element, so the first subscript is
					# the pointer arithmetic the source performed.
					array_info[name] = {'dimensions': [0] + dims_of(pointer_types[name])}
					element_types[name] = element_of(pointer_types[name])
				elif name in self.array_dims:
					array_info[name] = {'dimensions': self.array_dims[name]}
				else:
					raise RuntimeError(f"array @{name} is used but not declared in {self.ir.path}")

		terminators = collect_terminators(self.ir)

		# Registers the AGU programs read from the datapath: the values
		# their branches and switches decide on, counter bounds, initial
		# values and steps held in registers, and the registers that
		# subscripts are computed from.
		agu_consumed: Dict[str, List[str]] = {}

		def consume(block: str, reg: str) -> None:
			# A load the generators rename (an advanced counter, or the
			# counter's initial value) is consumed under its final name,
			# which may be a datapath value that must stay live.
			seen = set()
			while reg in self.advanced_registers and reg not in seen:
				seen.add(reg)
				reg = self.advanced_registers[reg]
			if reg and reg.startswith('%'):
				agu_consumed.setdefault(block, []).append(reg)

		own_compare = {info.header for info in loop_levels.values() if info.compare_on_counter}
		for block, term in terminators.items():
			if term['kind'] == 'cond' and block not in own_compare:
				consume(block, term['cond'])
			elif term['kind'] == 'switch':
				consume(block, term['value'])
			elif term['kind'] == 'ret' and term['value']:
				# The function's result: computed by the datapath, which
				# returns it. Nothing else kept `return i * 2` alive.
				consume(block, term['value'])
		for info in loop_levels.values():
			consume(info.header, info.bound)
			consume(info.init_block, info.init)
			for latch, step in info.latches.items():
				if step:
					for operand in step[1]:
						if operand != '%counter':
							consume(latch, operand)
		for block, arrays in array_accesses.items():
			for entries in arrays.values():
				for access in entries:
					for dim in access.dims:
						stack = [dim.expr]
						while stack:
							expr = stack.pop()
							if expr.kind == 'value':
								consume(block, expr.reg)
							stack.extend(expr.args)

		entry_names: Dict[str, Dict[str, str]] = {}
		for (level, block), name in self.counter_entry_names.items():
			entry_names.setdefault(level, {})[block] = name

		return {
			'array_info': array_info,
			'loop_levels': loop_levels,
			'control_flow': {
				'block_order': self.block_order,
				'successors': {block: list(info['successors'])
					for block, info in self.cfg.items()},
				'terminators': terminators,
			},
			'array_element_types': element_types,
			# Per-access table read straight from the IR: dimension order,
			# how many accesses each block makes to each array, and the
			# expression of each subscript.
			'array_accesses': array_accesses,
			# Scalars the loop never touches. Those it does touch have
			# already been folded into array_accesses: a load or store
			# inside a loop is streamed traffic and belongs to the AGU.
			'scalar_accesses': scalar_accesses,
			'slot_types': self.slot_types,
			'index_reg_to_loop_level': self.index_reg_to_loop_level,
			'advanced_registers': self.advanced_registers,
			# {block: [level, ...]}: blocks that read a counter's slot again
			# on entry, as %i<level>_at_<block>, because the value they are
			# entered with depends on the path taken.
			'counter_reloads': self.counter_reloads,
			# {level: {block: name}}: the register a counter has on entry to
			# a block, when it is not the header's %i<level> -- a latch's
			# update adds to that, not to the header's load.
			'counter_entry_names': entry_names,
			'agu_consumed': agu_consumed,
			'compute_info': {'operations': collect_operations(self)},
		}
