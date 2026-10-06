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
Readers for the intermediate files the Analyzer consumes: per-block
node lists, the CFG node list and the loop file.
"""
import ast
import os
from typing import Dict, List


class AnalyzerLoader:
	"""Loader for node lists, CFG connectivity and loop structure."""

	def __init__(self, analyzer):
		self.analyzer = analyzer

	def _read_node_list(self, block_id: str) -> List[List[str]]:
		"""
		Read one basic block's node list, or [] if the block has none.

		Results are memoised in the analyzer's own nodes_cache, so they
		belong to that analyzer and no other.
		"""
		if block_id in self.analyzer.nodes_cache:
			return self.analyzer.nodes_cache[block_id]

		file_path = os.path.join(
			self.analyzer.r_path,
			f"{self.analyzer.dfg_base_name}_bblock_{block_id}_node_list.txt")
		if not os.path.exists(file_path):
			return []

		# `<id> <opcode>_<node> <dst> <src>...`, space separated. Splitting
		# at commas gave one field holding the whole line.
		nodes: List[List[str]] = []
		with open(file_path, 'r') as f:
			for line in f:
				if line.strip():
					nodes.append(line.split())

		self.analyzer.nodes_cache[block_id] = nodes
		return nodes

	def _read_cfg_connectivity(self) -> Dict[str, Dict[str, List[str]]]:
		"""
		Read the control flow graph's predecessor and successor lists.

		Returns:
			{block_id: {'successors': [...], 'predecessors': [...]}}

		Each line of '<r_name>_node_list.txt' is
			<row> <block label> <dst> <predecessor>...
		Successors are derived by inverting the predecessor lists.
		"""
		connectivity: Dict[str, Dict[str, List[str]]] = {}
		file_path = os.path.join(self.analyzer.r_path,
			f"{self.analyzer.r_name}_node_list.txt")
		if not os.path.exists(file_path):
			return connectivity

		predecessors: Dict[str, List[str]] = {}
		with open(file_path, 'r') as f:
			for line in f:
				fields = line.split()
				if len(fields) < 2:
					continue
				block_id = fields[1]
				# fields[2] is the dst column; the rest are predecessors.
				predecessors[block_id] = [p for p in fields[3:] if p not in ('None', 'LEAF')]

		for block_id, preds in predecessors.items():
			connectivity.setdefault(block_id, {'successors': [], 'predecessors': []})
			connectivity[block_id]['predecessors'] = list(preds)

		for block_id, preds in predecessors.items():
			for pred in preds:
				entry = connectivity.setdefault(pred, {'successors': [], 'predecessors': []})
				if block_id not in entry['successors']:
					entry['successors'].append(block_id)

		return connectivity

	def _read_loop_structure(self) -> List[List[str]]:
		"""
		Read the loop file.

		Returns the loops innermost first, each as its block ids with the
		header first and the latch last, exactly as det_loop.py wrote them.
		"""
		loop_file_path = os.path.join(self.analyzer.r_path, f"{self.analyzer.r_name}_loop.txt")
		if not os.path.exists(loop_file_path):
			return []
		with open(loop_file_path, 'r') as f:
			content = f.read().strip()
		if not content:
			return []

		return [[str(node) for node in loop] for loop in ast.literal_eval(content)]

	def block_order(self, connectivity: Dict) -> List[str]:
		"""
		Blocks in control flow order: a reverse post-order from the entry.

		Successors are visited last-listed first, so the block a header
		exits to finishes before the loop body and lands after it in the
		reversed order: setup, the nest, teardown, as in the source.
		"""
		order: List[str] = []
		visited = set()

		def successors(block: str):
			return iter(reversed(connectivity.get(block, {}).get('successors', [])))

		# Iterative depth-first search: the recursive version overflowed
		# on long straight-line programs. The function's entry block
		# (the first listed) comes first; a block nothing reaches (clang
		# keeps a `for.inc` after a `return`) is ordered after everything
		# the entry reaches, not before it -- a single reversed post-order
		# over every root put the last root first, and the address
		# programs opened with an unreachable block.
		roots = [b for b in connectivity if not connectivity[b]['predecessors']]
		first = next(iter(self.analyzer.ir.blocks), None)		# the function's entry
		roots.sort(key=lambda b: b != first)
		for root in roots:
			if root in visited:
				continue
			segment: List[str] = []
			visited.add(root)
			stack = [(root, successors(root))]
			while stack:
				block, children = stack[-1]
				for succ in children:
					if succ not in visited:
						visited.add(succ)
						stack.append((succ, successors(succ)))
						break
				else:
					segment.append(block)
					stack.pop()
			order.extend(reversed(segment))
		return order

	def _get_all_block_ids(self) -> List[str]:
		"""
		Every basic block id, loop members first, then the rest.

		A program with no loops has no loop members, so the CFG node list
		supplies the blocks on its own.
		"""
		block_ids = list(dict.fromkeys(
			block_id for loop in self.analyzer.loops for block_id in loop))
		known = set(block_ids)
		for block_id in self._read_cfg_connectivity():
			if block_id in known:
				continue
			node_list = os.path.join(self.analyzer.r_path,
				f"{self.analyzer.dfg_base_name}_bblock_{block_id}_node_list.txt")
			if os.path.exists(node_list):
				block_ids.append(block_id)
				known.add(block_id)
		return block_ids

	def _collect_all_nodes(self):
		"""{block_id: node list} for every block."""
		return {block_id: self._read_node_list(block_id) for block_id in self._get_all_block_ids()}
