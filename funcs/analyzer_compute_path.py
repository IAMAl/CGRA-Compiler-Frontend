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
The arithmetic of each basic block.

Binary operations come from the node list, whose line is
    <id> <opcode>_<node> <dst> <src1> <src2>
with the operands in source order (Gen_DFG draws the src1 edge first,
Gen_AM records sources in edge order); a compare's node is
`icmp_<predicate>_<node>`. Casts, calls and selects need their types,
the callee or the literal arguments, which the node list does not carry,
so those are read from the IR. The list is in source order.
"""
import re
from typing import Dict, List


# Binary operations the datapath carries. `div` is not an LLVM opcode;
# listing it left every sdiv/srem and every floating-point operation
# out of the datapath with no diagnostic.
ARITHMETIC = {
	'add', 'sub', 'mul', 'sdiv', 'udiv', 'srem', 'urem',
	'and', 'or', 'xor', 'shl', 'ashr', 'lshr',
	'fadd', 'fsub', 'fmul', 'fdiv', 'frem',
	'icmp', 'fcmp',
}
CASTS = {'trunc', 'zext', 'sext', 'fptrunc', 'fpext', 'fptoui', 'fptosi', 'uitofp', 'sitofp'}
UNARY = CASTS | {'call', 'select', 'fneg'}


def collect_operations(analyzer) -> List[Dict]:
	"""
	Every arithmetic instruction, in source order, tagged with its block.

	Each entry is {'op', 'output', 'inputs', 'block_id', 'type'}, plus
	'predicate' for a compare, 'from'/'to' for a cast, 'callee', 'args'
	and 'ret' for a call. 'type' is the operand type the IR wrote on the
	instruction (a compare's result is i1; its operands have 'type'):
	the datapath emits it as is rather than guessing from what it knows
	about the operands, which typed `long t = i + 3` as i32.
	"""
	special = analyzer.special_operations
	operations: List[Dict] = []
	typed = re.compile(
		r'^\s*(?P<dst>%[-\w.$]+)\s*=\s*(?P<op>\w+)\s+(?:(?:samesign|nsw|nuw|exact|disjoint|nneg|fast|nnan|ninf|nsz|arcp|contract|afn|reassoc)\s+)*'
		r'(?:(?P<pred>\w+)\s+)?(?P<type>(?:\([^)]*\)|[^,\s])+)\s+(?P<lhs>[-+\w.$%@]+)\s*,')
	for block_id, nodes in analyzer.all_nodes.items():
		binary: Dict[str, Dict] = {}
		for fields in nodes:
			if len(fields) < 4:
				continue
			opcode = fields[1].rsplit('_', 1)[0]
			predicate = None
			if opcode.startswith(('icmp_', 'fcmp_')):
				opcode, predicate = opcode.split('_', 1)
			if opcode not in ARITHMETIC:
				continue
			entry = {'op': opcode, 'output': fields[2], 'inputs': fields[3:], 'block_id': block_id}
			if predicate:
				entry['predicate'] = predicate
			binary[fields[2]] = entry

		for line in analyzer.ir.lines(block_id):
			match = re.match(r'^\s*(%[-\w.$]+)\s*=', line)
			if not match:
				continue
			output = match.group(1)
			if output in binary:
				entry = binary[output]
				parsed = typed.match(line)
				if parsed is None or (entry['op'] in ('icmp', 'fcmp')) != (parsed.group('pred') is not None):
					raise RuntimeError(f"block {block_id}: cannot read the type of {line.strip()}")
				entry['type'] = parsed.group('type')
				operations.append(entry)
			elif output in special:
				operations.append(dict(special[output], output=output))
	return operations
