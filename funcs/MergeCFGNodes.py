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
Remove branch-only basic blocks from an LLVM IR function.

A block whose only instruction is `br label %X` adds nothing to the
control flow; every branch to it is redirected to X and the block is
dropped. Branch targets are rewritten as whole tokens (`label %2` is not
touched when `label %21` is meant), a block that a phi node names is
kept, and the function's entry block is never removed. The output keeps
one blank line before each label, as clang lays it out; predecessor
comments are not reproduced.
"""
import os
import re
from typing import Dict, List, Tuple

from utils.IRNormalize import hoist_constant_geps, strip_debug


DEBUG = False

_LABEL = re.compile(r'^(?:"(?P<quoted>[^"]+)"|(?P<plain>[^\s:";]+)):')
_JMP = re.compile(r'^\s*br\s+label\s+%(?P<target>[-\w.$]+)\s*(?:,|$)')


def _strip_comment(line: str) -> str:
	"""The line without its `;` comment; a `;` inside a string literal stays."""
	quoted = False
	for index, char in enumerate(line):
		if char == '"':
			quoted = not quoted
		elif char == ';' and not quoted:
			return line[:index]
	return line


def _split_function(lines: List[str]) -> Tuple[List[str], List[str], List[str]]:
	"""(lines before the body, body lines, lines from the closing brace on)."""
	start = None
	for index, line in enumerate(lines):
		if line.lstrip().startswith('define '):
			start = index
			break
	if start is None:
		raise ValueError("no function definition found")
	end = None
	for index in range(start + 1, len(lines)):
		if lines[index].rstrip() == '}':
			end = index
			break
	if end is None:
		raise ValueError("function body is not closed")
	return lines[:start + 1], lines[start + 1:end], lines[end:]


def _blocks(body: List[str]) -> List[Dict]:
	"""Split a function body into [{'name', 'labelled', 'lines'}, ...]."""
	blocks: List[Dict] = []
	current = None
	for line in body:
		code = _strip_comment(line).rstrip()
		if not code.strip():
			continue
		match = _LABEL.match(code) if code[:1] not in (' ', '\t') else None
		if match:
			current = {'name': match.group('quoted') or match.group('plain'),
				'labelled': True, 'lines': []}
			blocks.append(current)
			continue
		if current is None:
			current = {'name': 'entry', 'labelled': False, 'lines': []}
			blocks.append(current)
		current['lines'].append(code)
	# A quoted label (`"for.cond":`) is written bare, so its uses must be
	# too, or the CFG stage finds no edges; a label that needs its quotes
	# (a space inside) has no bare spelling.
	for block in blocks:
		if block['labelled'] and not re.fullmatch(r'[-\w.$]+', block['name']):
			raise NotImplementedError(
				f"block label \"{block['name']}\" needs its quotes; only plain labels are supported")
	for block in blocks:
		block['lines'] = [re.sub(r'%"([-\w.$]+)"', r'%\1', line) for line in block['lines']]
	names = [block['name'] for block in blocks]
	if len(set(names)) != len(names):
		twice = sorted({n for n in names if names.count(n) > 1})
		raise NotImplementedError(
			f"two blocks are named {twice[0]} (an unlabelled first block is called entry; "
			f"a later block may not be)")
	if 'ret' in names:
		raise NotImplementedError(
			"a block is labelled ret, the name the generated address programs give their "
			"final block; rename it")
	return blocks


def _retarget(line: str, old: str, new: str) -> str:
	return re.sub(rf'label\s+%{re.escape(old)}(?![-\w.$])', f'label %{new}', line)


def CFGNodeMerger(r_file_path: str, r_file_name: str) -> List[str]:
	"""
	Node Merger for Control-Flow Graph: returns the rewritten file's lines.
	"""
	with open(os.path.join(r_file_path, r_file_name + '.ll'), 'r') as f:
		lines = hoist_constant_geps(strip_debug(f.read())).splitlines()

	head, body, tail = _split_function(lines)
	blocks = _blocks(body)

	# A block named by a phi node must stay: the phi keys its incoming
	# value on the block.
	named_by_phi = set()
	for block in blocks:
		for line in block['lines']:
			if re.match(r'^\s*%[-\w.$]+\s*=\s*phi\b', line):
				named_by_phi.update(re.findall(r',\s*%([-\w.$]+)\s*\]', line))

	# Where a removed block's branch leads, following chains of removed
	# blocks to the end.
	forward: Dict[str, str] = {}
	for index, block in enumerate(blocks):
		if index == 0 or not block['labelled'] or len(block['lines']) != 1:
			continue
		if block['name'] in named_by_phi:
			continue
		jump = _JMP.match(block['lines'][0])
		if jump and jump.group('target') != block['name']:
			forward[block['name']] = jump.group('target')

	def resolve(name: str) -> str:
		seen = set()
		while name in forward and name not in seen:
			seen.add(name)
			name = forward[name]
		return name

	# Branch-only blocks that only reach one another are an empty loop
	# (`for (;;) ;`): removing them all leaves branches to nothing.
	cyclic = sorted(name for name in forward if resolve(name) in forward)
	for block in blocks:
		if block['labelled'] and len(block['lines']) == 1:
			jump = _JMP.match(block['lines'][0])
			if jump and jump.group('target') == block['name']:
				cyclic.append(block['name'])
	if cyclic:
		raise NotImplementedError(
			f"blocks {', '.join(cyclic)} branch among themselves and do nothing: an "
			f"empty loop has no address stream or computation to generate")

	# One pattern over every removed label, compiled once: a pattern per
	# label per line recompiled past the regex cache and took a minute
	# for a few hundred empty `if` arms.
	retarget = None
	if forward:
		names = '|'.join(re.escape(old) for old in sorted(forward, key=len, reverse=True))
		retarget = re.compile(rf'label\s+%({names})(?![-\w.$])')
	out = list(head)
	for block in blocks:
		if block['name'] in forward:
			if DEBUG:
				print(f"merged branch-only block {block['name']} into {resolve(block['name'])}")
			continue
		if block['labelled']:
			out.append('')
			out.append(f"{block['name']}:")
		for line in block['lines']:
			if retarget is not None:
				line = retarget.sub(lambda m: 'label %' + resolve(m.group(1)), line)
			out.append(line)
	out.extend(tail)
	return out


def ExtractCFGNodeMerger(r_file_path: str, r_file_name: str, w_file_path: str) -> None:
	w_file_name = r_file_name + "_merged.ll"
	lines = CFGNodeMerger(r_file_path, r_file_name)
	with open(os.path.join(w_file_path, w_file_name), 'w') as f:
		f.write('\n'.join(lines) + '\n')
