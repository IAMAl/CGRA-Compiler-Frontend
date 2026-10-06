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
Data classes shared by the Analyzer and the generators.
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class LoopInfo:
	"""
	One natural loop, as the generators need to see it.

	The control-flow half (nodes, header, latches, nesting) comes from
	the loop file; the counter half is read from the IR: which alloca
	holds the counter, where and how it is initialised, how the header
	compares it and how each latch advances it. Every field of the
	counter half is taken from the source rather than assumed.

	A loop need not have a counter, and its header need not compare one:
	then the AGU reproduces the header's own terminator, branching on the
	value the datapath computes as it does for an `if`.
	"""
	nodes: List[str]		# every block of the loop, header first, latches last
	header: str
	exit: str				# the primary latch (the last block listed)
	parent: str				# enclosing level, '' for an outermost loop
	children: List[str]

	counter_slot: Optional[str] = None	# alloca of the counter, or None
	init: Optional[str] = None			# literal or register stored before entry
	init_block: Optional[str] = None	# the block that stores it
	compare_on_counter: bool = False	# the header compares the counter itself
	predicate: str = 'slt'				# icmp predicate with the counter on the left
	bound: Optional[str] = None			# literal or register compared against
	compare_type: str = 'i32'			# the type the header compares at
	compare_casts: List[tuple] = field(default_factory=list)	# (op, from, to) applied to the counter first
	init_position: int = 0				# line of the initialising store in init_block
	# {latch block: line of the store that advances the counter}
	update_positions: Dict[str, int] = field(default_factory=dict)
	compare_after_update: bool = False	# single-block loop: compare the advanced value
	body_entry: Optional[str] = None	# where the header goes while the loop runs
	exit_target: Optional[str] = None	# where the header goes when it is done
	# {latch block: [opcode, operands] or None}. The operands carry the
	# counter as '%counter'; None for a latch that does not touch it.
	latches: Dict[str, Optional[List[str]]] = field(default_factory=dict)
