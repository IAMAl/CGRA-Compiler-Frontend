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
Natural loop detection on the control flow graph.

The CFG adjacency matrix is directed: am[i][j] == 1 means block i
branches to block j. A back edge is an edge u -> h where h dominates u,
and its natural loop is h together with every block that reaches u
without passing through h. Each loop is reported as its block names,
header first, body in control flow order, latches last; the loops are
listed innermost first. The matrix must be directed: on a symmetric
one a two-block `while` loop is a single edge, not a cycle.
"""
from typing import List


DEBUG = False


def first_block(ir_path: str) -> str:
	"""
	The label of a function's first block: the first label after the
	`define`, or `entry` when the first block is unlabelled (the name
	the parser gives it).
	"""
	import re
	in_body = False
	with open(ir_path) as f:
		for line in f:
			if line.startswith('define'):
				in_body = True
				continue
			if not in_body:
				continue
			code = line.split(';', 1)[0].rstrip()
			if not code.strip():
				continue
			match = re.match(r'^(?:"([^"]+)"|([-\w.$]+)):', code)
			if match:
				return match.group(1) or match.group(2)
			return 'entry'
	return 'entry'


def DetectLoops(am, names: List[str], entry: str = 'entry') -> List[List[str]]:
	"""
	Natural loops of the graph, innermost first.

	A retreating edge whose target does not dominate its source (an
	irreducible cycle) has no natural loop: it is reported and skipped,
	and its blocks stay ordinary control flow.
	"""
	size = len(am)
	# Edge lists from the dense matrix, row by row through numpy: the
	# element-wise scan was O(N^2) Python operations on thousands of blocks.
	import numpy as np
	dense = np.asarray(am)
	succ = [np.flatnonzero(dense[i]).tolist() for i in range(size)] if size else []
	pred = [[] for _ in range(size)]
	for i in range(size):
		for j in succ[i]:
			pred[j].append(i)

	if entry in names:
		start = names.index(entry)
	else:
		roots = [i for i in range(size) if not pred[i]]
		if not roots:
			raise ValueError("control flow graph has no entry block")
		start = roots[0]

	# Reverse post-order over the reachable blocks.
	# Iterative, so a graph of thousands of blocks does not overflow
	# the recursion limit.
	post: List[int] = []
	visited = {start}
	stack = [(start, iter(succ[start]))]
	while stack:
		node, children = stack[-1]
		for nxt in children:
			if nxt not in visited:
				visited.add(nxt)
				stack.append((nxt, iter(succ[nxt])))
				break
		else:
			post.append(node)
			stack.pop()
	rpo = list(reversed(post))
	position = {node: index for index, node in enumerate(rpo)}

	# Dominators, by iteration to a fixpoint. Each set is an integer
	# bit mask: a Python set per node cost gigabytes on thousands of
	# blocks.
	everyone = 0
	for node in rpo:
		everyone |= 1 << node
	dom = {node: everyone for node in rpo}
	dom[start] = 1 << start
	changed = True
	while changed:
		changed = False
		for node in rpo[1:]:
			incoming = [dom[p] for p in pred[node] if p in dom]
			meet = everyone
			for mask in incoming:
				meet &= mask
			new = (1 << node) | (meet if incoming else 0)
			if new != dom[node]:
				dom[node] = new
				changed = True

	loops = {}		# header -> (body, latches)
	for node in rpo:
		for target in succ[node]:
			if position[target] > position[node]:
				continue			# a forward edge
			if not dom[node] >> target & 1:
				# An irreducible cycle: the edge goes back into a region
				# with more than one entry, so no natural loop owns it. The
				# generators need no loop for such a region -- they follow
				# the control flow graph block by block -- so it is simply
				# not reported.
				print(f"Note: {names[node]} -> {names[target]} closes an irreducible cycle; "
					f"no loop is reported for it")
				continue
			body = {target}
			stack = [node]
			while stack:
				current = stack.pop()
				if current not in body:
					body.add(current)
					# An unreachable block (clang keeps a `for.inc` after a
					# `return`) may point into the loop; it is no member.
					stack.extend(p for p in pred[current] if p in position)
			members, latches = loops.setdefault(target, (set(), []))
			members |= body
			latches.append(node)

	result = []
	for header, (members, latches) in loops.items():
		inner = sorted(members - {header} - set(latches), key=position.get)
		# A single-block loop is its own latch; list it once.
		tail = sorted((l for l in latches if l != header), key=position.get)
		ordered = [header] + inner + tail
		result.append([names[i] for i in ordered])
	result.sort(key=lambda loop: (len(loop), position[names.index(loop[0])]))

	if DEBUG:
		print(f"loops: {result}" if result else "no loop detected")
	return result
