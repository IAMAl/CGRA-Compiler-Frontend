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
Loop-level analysis for the Analyzer.

The loop file lists each natural loop's blocks, innermost loop first,
header first and latches last. This module arranges them into a forest
by containment, numbers them (an outer loop before the loops inside it,
outer loops in control flow order) and fills in the counter half of
each LoopInfo from the IR.
"""
from typing import Dict, List

from funcs.analyzer_models import LoopInfo
from funcs.analyzer_ir_access import describe_loop


class LoopAnalyzer:
	"""Builds {level: LoopInfo}; level '1' is the first outermost loop."""

	def __init__(self, analyzer):
		self.analyzer = analyzer

	def analyze(self) -> Dict[str, LoopInfo]:
		loops: List[List[str]] = self.analyzer.loops
		result: Dict[str, LoopInfo] = {}
		if not loops:
			return result

		sets = [set(loop) for loop in loops]
		for a in range(len(loops)):
			for b in range(a + 1, len(loops)):
				if sets[a] & sets[b] and not (sets[a] <= sets[b] or sets[b] <= sets[a]):
					raise NotImplementedError(
						f"loops {loops[a]} and {loops[b]} overlap without nesting")

		# The parent of a loop is the smallest loop strictly containing it.
		parent_of: Dict[int, int] = {}
		for a in range(len(loops)):
			enclosing = [b for b in range(len(loops)) if b != a and sets[a] < sets[b]]
			if enclosing:
				parent_of[a] = min(enclosing, key=lambda b: len(sets[b]))

		order = self.analyzer.block_order
		position = {block: index for index, block in enumerate(order)}
		predecessors = {block: info['predecessors']
			for block, info in self.analyzer.cfg.items()}

		level_of: Dict[int, str] = {}

		def number(index: int) -> None:
			level_of[index] = str(len(level_of) + 1)
			children = [c for c, p in parent_of.items() if p == index]
			for child in sorted(children, key=lambda c: position.get(loops[c][0], -1)):
				number(child)

		roots = [i for i in range(len(loops)) if i not in parent_of]
		for root in sorted(roots, key=lambda i: position.get(loops[i][0], -1)):
			number(root)

		for index, nodes in enumerate(loops):
			level = level_of[index]
			# Blocks of the loops that neither contain this one nor sit inside
			# it: an initialisation found in one of those is another loop's.
			others = {block for other, members in enumerate(loops)
				if other != index and not set(members) & set(nodes) for block in members}
			counter = describe_loop(self.analyzer.ir, nodes[0], nodes, predecessors, others)
			result[level] = LoopInfo(
				nodes=list(nodes),
				header=nodes[0],
				exit=nodes[-1],
				parent=level_of[parent_of[index]] if index in parent_of else '',
				children=[level_of[c] for c, p in parent_of.items() if p == index],
				**counter)

		return dict(sorted(result.items(), key=lambda item: int(item[0])))
