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
LLVM IR reader.

`asm_parser` turns the text of a module into program / function /
basicblock / instruction objects (utils.ProgConstructor). Instructions
are recognised by opcode, not by token count, so the flags an opcode may
carry (`add nsw i64`), the width of its type, opaque pointers (`ptr %x`)
and the number of subscripts on a getelementptr do not change how a line
is read. An instruction the reader does not know raises rather than
being mis-filed as something else.

Every instruction records:
    opcode     the mnemonic; getelementptr carries its base and icmp its
               predicate (`getelementptr_@a`, `icmp_slt`)
    dst        the register defined, or None
    d_type     the type the instruction works on, when it names one
    operands   the registers and literals it reads, in source order
    func       predicate / flags / cast types / callee, informational
    br_t/br_f  branch targets as 'label:<name>'
    targets    every branch target as a plain block name
    cases      (literal, label) pairs of a switch
    imm        True when an operand is a literal
    sw         True for a switch
"""
import os
import re

from utils.IRNormalize import split_top_level
import copy

import utils.InstrTypeChecker as type_checker
import utils.ProgConstructor as progconst

DEBUG = False
type_chk = type_checker.Type_Check()


BINARY_OPS = {
	'add', 'sub', 'mul', 'udiv', 'sdiv', 'urem', 'srem',
	'shl', 'lshr', 'ashr', 'and', 'or', 'xor',
	'fadd', 'fsub', 'fmul', 'fdiv', 'frem',
}
CAST_OPS = {
	'trunc', 'zext', 'sext', 'fptrunc', 'fpext', 'fptoui', 'fptosi',
	'uitofp', 'sitofp', 'ptrtoint', 'inttoptr', 'bitcast', 'addrspacecast',
}
# Keywords that may precede an operation's type.
FLAGS = {
	'nsw', 'nuw', 'exact', 'fast', 'nnan', 'ninf', 'nsz', 'arcp', 'contract',
	'afn', 'reassoc', 'inbounds', 'volatile', 'nneg', 'disjoint', 'samesign',
	'nusw',
}

_METADATA_TAIL = re.compile(r',\s*!\w[\w.]*\s+!\w+\s*$')
_DEFINE = re.compile(r'^define\b.*\s(?P<name>@[-\w.$]+)\s*\(')
_SWITCH = re.compile(
	r'^switch\s+(?P<type>\S+)\s+(?P<value>\S+?)\s*,\s*label\s+%(?P<default>[-\w.$]+)\s*\[(?P<cases>.*)\]\s*$')
_CASE = re.compile(r'\S+\s+(?P<literal>-?\d+|true|false)\s*,\s*label\s+%(?P<label>[-\w.$]+)')


class Parsed:
	"""The fields of one parsed instruction."""

	def __init__(self):
		self.opcode = None
		self.dst = None
		self.d_type = None
		self.operands = []
		self.func = None
		self.br_t = None
		self.br_f = None
		self.imm = False
		self.sw = False
		self.targets = []
		self.cases = []


def _label( token ):
	return "label:<" + token.replace(",", "").lstrip("%") + ">"


def _name( token ):
	return token.replace(",", "").lstrip("%")


def _last( part ):
	"""The value of a `<type> <value>` operand."""
	return part.split()[-1].rstrip(",")


def _is_literal( token ):
	return not token.startswith("%")


def _drop_flags( tokens ):
	index = 0
	while index < len(tokens) and tokens[index] in FLAGS:
		index += 1
	return tokens[index:]


def instr_parser( instr ):
	"""
	Instruction Parser

	Takes the whitespace-split tokens of one instruction (a switch is
	given joined onto one line). Returns a Parsed.
	"""
	text = _METADATA_TAIL.sub("", " ".join(instr))
	tokens = text.split()
	p = Parsed()

	if tokens[0] == "br":
		if tokens[1] == "label":
			# br label %31
			p.opcode = "jmp"
			p.br_t = p.br_f = _label(tokens[2])
			p.targets = [_name(tokens[2])]
		else:
			# br i1 %6, label %7, label %32
			p.opcode = "br"
			p.operands.append(tokens[2].rstrip(","))
			p.br_t = _label(tokens[4])
			p.br_f = _label(tokens[6])
			p.targets = [_name(tokens[4]), _name(tokens[6])]
		return p

	if tokens[0] == "switch":
		# switch i32 %7, label %38 [ i32 48, label %8 i32 43, label %11 ]
		match = _SWITCH.match(text)
		if not match:
			raise NotImplementedError(f"unsupported switch form: {text}")
		p.opcode = "switch"
		p.sw = True
		p.d_type = match.group("type")
		p.operands.append(match.group("value"))
		p.br_t = _label(match.group("default"))
		p.cases = [(case.group("literal"), case.group("label"))
			for case in _CASE.finditer(match.group("cases"))]
		p.targets = [match.group("default")] + [label for _, label in p.cases]
		return p

	if tokens[0] == "store":
		# store [volatile] i32 %45, i32* %43, align 4
		parts = split_top_level(" ".join(_drop_flags(tokens[1:])))
		p.opcode = "store"
		p.d_type = parts[1].split()[0]
		p.operands = [_last(parts[0]), _last(parts[1])]
		p.imm = _is_literal(p.operands[0])
		return p

	if tokens[0] == "ret":
		# ret void / ret i32 %27
		p.opcode = "ret"
		p.d_type = tokens[1]
		if len(tokens) > 2:
			p.operands.append(tokens[2].rstrip(","))
		return p

	if tokens[0] in ("tail", "notail", "musttail") and len(tokens) > 1 and tokens[1] == "call":
		tokens = tokens[1:]
	if tokens[0] == "call":
		# call void @push(double %10)
		p.opcode = "call"
		callee = re.search(r'(@[-\w.$]+)\s*\(', text)
		p.func = callee.group(1) if callee else None
		p.operands = re.findall(r'%[-\w.$]+', text.split("(", 1)[-1])
		return p

	if tokens[0] == "unreachable":
		p.opcode = "unreachable"
		p.imm = None
		p.sw = None
		return p

	if len(tokens) < 3 or tokens[1] != "=":
		raise NotImplementedError(f"unsupported instruction: {text}")

	p.dst = tokens[0]
	opcode = tokens[2]
	rest = tokens[3:]

	if opcode == "load":
		# %38 = load [volatile] i32, i32* %2, align 4
		parts = split_top_level(" ".join(_drop_flags(rest)))
		p.opcode = "load"
		p.d_type = parts[0]
		p.operands.append(_last(parts[1]))

	elif opcode in ("icmp", "fcmp"):
		# %10 = icmp eq i32 %9, 9
		# The predicate travels in the opcode, the way a getelementptr's
		# base does, so the data-flow graph keeps it. Fast-math flags
		# (`fcmp fast olt`) and `samesign` come before the predicate.
		rest = _drop_flags(rest)
		p.opcode = opcode + "_" + rest[0]
		p.func = rest[0]
		p.d_type = rest[1]
		p.operands = [rest[2].rstrip(","), rest[3]]
		p.imm = any(_is_literal(op) for op in p.operands)

	elif opcode == "fneg":
		# %3 = fneg double %2
		rest = _drop_flags(rest)
		p.opcode = "fneg"
		p.d_type = rest[0]
		p.operands.append(rest[1])

	elif opcode in CAST_OPS:
		# %27 = sext i8 %26 to i32   (or `zext nneg i32 %x to i64`)
		rest = _drop_flags(rest)
		p.opcode = opcode
		p.d_type = rest[3]
		p.operands.append(rest[1].rstrip(","))
		p.func = rest[0] + " to " + rest[3]

	elif opcode == "alloca":
		# %1 = alloca i32, align 4
		p.opcode = "alloca"
		p.func = " ".join(rest)

	elif opcode == "getelementptr":
		# %18 = getelementptr inbounds [256 x [256 x i32]], [256 x [256 x i32]]* @A, i64 0, i64 %17
		# %21 = getelementptr inbounds [256 x i32], ptr %18, i64 0, i64 %20
		# %46 = getelementptr inbounds i8, i8* %45, i64 %4
		parts = split_top_level(" ".join(_drop_flags(rest)))
		base = _last(parts[1])
		indices = [_last(part) for part in parts[2:]]
		p.opcode = "getelementptr_" + base
		p.d_type = parts[0]
		p.func = parts[0]
		if not _is_literal(base):
			p.operands.append(base)
		p.operands += [index for index in indices if not _is_literal(index)]
		p.imm = any(_is_literal(index) for index in indices)

	elif opcode == "phi":
		# %x = phi i32 [ %a, %bb1 ], [ %b, %bb2 ]
		p.opcode = "phi"
		p.d_type = rest[0]
		p.operands = re.findall(r'\[\s*([^,\s]+)\s*,', " ".join(rest))
		p.imm = any(_is_literal(op) for op in p.operands)

	elif opcode == "select":
		# %x = select i1 %c, i32 %a, i32 %b
		p.opcode = "select"
		parts = split_top_level(" ".join(rest))
		p.d_type = parts[1].split()[0]
		p.operands = [_last(part) for part in parts]
		p.imm = any(_is_literal(op) for op in p.operands)

	elif opcode in ("call", "tail", "notail", "musttail"):
		# %3 = call i32 @getchar()
		p.opcode = "call"
		callee = re.search(r'(@[-\w.$]+)\s*\(', text)
		p.func = callee.group(1) if callee else None
		p.operands = re.findall(r'%[-\w.$]+', text.split("(", 1)[-1])

	elif opcode in BINARY_OPS:
		# %11 = add nsw i32 %10, 1
		p.opcode = opcode
		flags = [token for token in rest if token in FLAGS]
		rest = _drop_flags(rest)
		p.d_type = rest[0]
		p.operands = [rest[1].rstrip(","), rest[2]]
		p.func = " ".join(flags) or None
		p.imm = any(_is_literal(op) for op in p.operands)

	else:
		raise NotImplementedError(f"unsupported instruction: {text}")

	return p


def asm_parser( asm ):
	"""
	LLVM-IR Parser

	Reads the lines of a module. Everything outside a `define` is skipped;
	inside one, a name at column 0 followed by ':' opens a basic block,
	'}' closes the function, and every other non-empty line is an
	instruction. The first block of a function without a label is named
	'entry'. Blank lines carry no meaning, so a label directly after a
	branch, or a blank line inside a block, reads the same as clang's
	layout.
	"""
	prog = progconst.program()
	func = None
	bblock = None
	pending_switch = None		# lines of a switch not yet closed by ']'

	def close_block():
		nonlocal bblock
		if bblock is not None:
			func.append(bblock)
			bblock = None

	for line in asm:
		code = line.split(";", 1)[0].rstrip()
		stripped = code.strip()

		# A switch spans several lines; gather it into one instruction.
		if pending_switch is not None:
			pending_switch.append(stripped)
			if "]" not in stripped:
				continue
			code = "  " + " ".join(pending_switch)
			stripped = code.strip()
			pending_switch = None
		elif stripped.startswith("switch ") and "]" not in stripped:
			pending_switch = [stripped]
			continue

		if func is None:
			match = _DEFINE.match(stripped)
			if match:
				func = progconst.function()
				func.set_name(match.group("name"))
				if DEBUG:
					print(f"Enter Func: {func.name}")
			elif stripped.startswith("define"):
				# A name the pattern cannot read (a quoted one, `@"my func"`)
				# used to leave the function unopened and its body skipped
				# without a word.
				raise NotImplementedError(
					f"cannot read the function's name; only plain names (@[-\\w.$]+) "
					f"are supported: {stripped}")
			continue

		if stripped == "}":
			close_block()
			prog.append(func)
			func = None
			continue

		if not stripped:
			continue

		label = type_chk.label_name(code)
		if label is not None:
			close_block()
			bblock = progconst.basicblock()
			bblock.set_name(label)
			if DEBUG:
				print(f"Enter BBlock: {bblock.name}")
			continue

		if bblock is None:
			bblock = progconst.basicblock()
			bblock.set_name("entry")

		parsed = instr_parser(stripped.split())
		instr = progconst.instruction()
		instr.opcode = parsed.opcode
		instr.dst = parsed.dst
		instr.d_type = parsed.d_type
		instr.operands = parsed.operands
		instr.func = parsed.func
		instr.br_t = parsed.br_t
		instr.br_f = parsed.br_f
		instr.imm = parsed.imm
		instr.sw = parsed.sw
		instr.targets = parsed.targets
		instr.cases = parsed.cases
		instr.nemonic = code
		bblock.append(instr)

	if func is not None:
		# The body never closed: the program would be silently incomplete.
		raise ValueError(f"function {func.name} is not closed by a '}}'")

	if DEBUG:
		for p_index, func_ in enumerate(prog.funcs):
			print(func_.name)
			for f_index, bblock_ in enumerate(func_.bblocks):
				print(bblock_.name)
				for b_index, instr in enumerate(bblock_.instrs):
					print("{}:{}:{}:{}".format(p_index, f_index, b_index, instr.nemonic))

	return prog


def is_Val( src ):
	"""
	Check literal is value (val) or not.
	Return
		True:   Literal is Value
		False:  Otherwise
	Common for Source-1 and Source-2.
	"""
	return "%" != src[0]


def is_None( src ):
	"""
	Check literal is None or not.
	Return
		True:   source is type of None
		False:  Otherwise
	Common for Source-1 and Source-2.
	"""
	return None == src


def FetchSrc( src="src2", instr=None ):
	"""
	Fetch Src-ID from instr class.
	Return
		Literal:    if operand exists
		None:       otherwise
	"""
	if None == instr:
		print("Error: Un-registered Instruction is discovered.")
		return None
	elif "src2" == src and len(instr.operands) > 1:
		# Fetch Source-2
		return instr.operands[1]
	elif "src1" == src and len(instr.operands) > 0:
		# Fetch Source-1
		return instr.operands[0]
	else:
		return None


def SetNextInstr(r=None):
	"""
	Move to Next Instr
	"""

	# Get program
	prog = r.ReadProg()

	# Get current pointer
	ptr = r.ReadPtr()
	f_ptr, b_ptr, i_ptr = ptr["f_ptr"], ptr["b_ptr"], ptr["i_ptr"]

	# Set current pointer by exploring next pointer
	if f_ptr == 0 and b_ptr == 0 and i_ptr == 0:
		r.next_bb = True
		ptr = {"f_ptr":f_ptr, "b_ptr":b_ptr, "i_ptr":i_ptr}

	elif f_ptr == 0 and b_ptr == 0 and i_ptr > 0:
		# Move within this block
		r.next_bb = False
		i_ptr -= 1
		ptr = {"f_ptr":f_ptr, "b_ptr":b_ptr, "i_ptr":i_ptr}

	elif f_ptr == 0 and b_ptr > 0 and i_ptr == 0:
		# Move within this block
		r.next_bb = False
		b_ptr -= 1
		i_ptr = prog.funcs[f_ptr].bblocks[b_ptr].num_instrs - 1
		ptr = {"f_ptr":f_ptr, "b_ptr":b_ptr, "i_ptr":i_ptr}

	elif f_ptr == 0 and b_ptr > 0 and i_ptr > 0:
		# Move within this block
		r.next_bb = False
		i_ptr -= 1
		ptr = {"f_ptr":f_ptr, "b_ptr":b_ptr, "i_ptr":i_ptr}

	elif f_ptr > 0 and b_ptr == 0 and i_ptr == 0:
		# Move next func last block, last instr
		r.next_bb = True
		f_ptr -= 1
		b_ptr = prog.funcs[f_ptr].num_bblocks - 1
		i_ptr = prog.funcs[f_ptr].bblocks[b_ptr].num_instrs - 1
		ptr = {"f_ptr":f_ptr, "b_ptr":b_ptr, "i_ptr":i_ptr}

	elif f_ptr > 0 and b_ptr == 0 and i_ptr > 0:
		# Move within this bblock
		r.next_bb = False
		i_ptr -= 1
		ptr = {"f_ptr":f_ptr, "b_ptr":b_ptr, "i_ptr":i_ptr}

	elif f_ptr > 0 and b_ptr > 0 and i_ptr == 0:
		# Move next block
		r.next_bb = True
		b_ptr -= 1
		i_ptr = prog.funcs[f_ptr].bblocks[b_ptr].num_instrs - 1
		ptr = {"f_ptr":f_ptr, "b_ptr":b_ptr, "i_ptr":i_ptr}

	elif f_ptr > 0 and b_ptr > 0 and i_ptr > 0:
		# Move within this bblock
		r.next_bb = False
		i_ptr -= 1
		ptr = {"f_ptr":f_ptr, "b_ptr":b_ptr, "i_ptr":i_ptr}

	r.SetPtr(ptr)


class RegInstr:
	"""
	Registering Utilities
	"""
	def __init__(self, prog, ptr):
		self.prog = prog            #program class
		self.ptr = ptr              #tracking pointer
		self.stack_ptr = []         #stack for pointers
		self.hit_ptr = None         #pointer for search-hit
		self.instr = None           #instruction class
		self.next_bb = False        #Moved to Next Basic Block then True
		self.num_exit = 0           #count of dst-search hits used in SearchDst

	def ReadProg( self ):
		"""
		Read Program
		"""
		return self.prog

	def ReadHitPtr( self ):
		"""
		Read Hit (Source-Node) Pointer
		"""
		return self.hit_ptr

	def ReadPtr( self ):
		"""
		Read Current Pointer
		"""
		return self.ptr

	def SetPtr( self, ptr=None ):
		"""
		Set Pointers
		"""
		self.ptr = copy.deepcopy(ptr)

	def PushPtr( self ):
		"""
		Push Pointers to Stack
		Used for Record a Path having Source-2 for backing to the instr
		Used when enters to source-2 path
		"""
		ptr = self.ptr
		self.stack_ptr.append(copy.deepcopy(ptr))

	def PopPtr( self, SrcNo=None ):
		"""
		Pop Pointers from Stack
		Used for reverting Path and entering to Source-1 path
		"""
		if len(self.stack_ptr) > 0:
			self.ptr = self.stack_ptr.pop()

	def DepthStack( self ):
		"""
		Return Stack-Depth
		"""
		return len(self.stack_ptr)

	def CheckInstr( self, ptr=None ):
		"""
		Record instruction addressed by current pointer
		Marking discovered flag which indicates source-1 operand is commited.
		"""
		if None == ptr:
			f_ptr, b_ptr, i_ptr = self.ptr["f_ptr"], self.ptr["b_ptr"], self.ptr["i_ptr"]
		else:
			f_ptr, b_ptr, i_ptr = ptr["f_ptr"], ptr["b_ptr"], ptr["i_ptr"]
		self.prog.funcs[f_ptr].bblocks[b_ptr].instrs[i_ptr].discovered = True

	def ReadInstr( self, ptr=None ):
		"""
		Fetch Instruction addessed by current pointer
		"""
		f_ptr, b_ptr, i_ptr = ptr["f_ptr"], ptr["b_ptr"], ptr["i_ptr"]
		return self.prog.funcs[f_ptr].bblocks[b_ptr].instrs[i_ptr]

	def SetPrevInstr( self, instr=None ):
		"""
		Set discovered instruction
		"""
		self.instr = instr

	def NextInstr( self, prog, r ):
		"""
		Set Instruction as a Node
		Update pointers (current and previous) for this loop-cycle.
		"""
		SetNextInstr(r)

		# Can Explore Path
		return "next_seq_src2"

	def CheckTerm( self ):
		"""
		Check termination
		If all instructions are discovered then does termination.
		This event is at reaching to first instruction (pointer is zero).
		"""
		prog = self.ReadProg()
		cont = False
		for func in prog.funcs:
			for bblock in func.bblocks:
				for instr in bblock.instrs:
					if instr.discovered or len(instr.operands) == 0:
						cont = cont | False
					else:
						cont = True

		if not cont and len(self.stack_ptr) == 0:
			return "term"
		else:
			return "next_reg_dst"

	def SearchDst( self ):
		"""
		Search Instruction having Undiscovered
		This module works when seeking pointer reaches to terimial nodes.
		This case needs to resets pointer to un-discovered instruction
			which is closest to end of file.
		"""
		prog = self.prog
		f_ptr = self.ptr["f_ptr"]
		for f_index in range(f_ptr, -1,-1):
			num_bblocks = prog.funcs[f_index].num_bblocks - 1
			for b_index in range(num_bblocks, -1, -1):
				num_instrs = prog.funcs[f_index].bblocks[b_index].num_instrs - 1
				for i_index in range(num_instrs, -1, -1):
					instr = prog.funcs[f_index].bblocks[b_index].instrs[i_index]
					if not instr.discovered:
						# Find dst node
						prog.funcs[f_index].bblocks[b_index].instrs[i_index].discovered = True
						ptr = {"f_ptr":f_index, "b_ptr":b_index, "i_ptr":i_index}
						self.SetPtr(ptr)

						self.num_exit += 1

						return True

		# Could Not Find source node
		return False

	def SearchSrc( self, src=None ):
		"""
		Search Instruction having Source Operand
		"""
		prog = self.prog
		f_ptr = self.ptr["f_ptr"]
		for f_index in range(f_ptr, -1,-1):
			num_bblocks = prog.funcs[f_index].num_bblocks - 1
			for b_index in range(num_bblocks, -1, -1):
				num_instrs = prog.funcs[f_index].bblocks[b_index].num_instrs - 1
				for i_index in range(num_instrs, -1, -1):
					instr = prog.funcs[f_index].bblocks[b_index].instrs[i_index]
					if instr.dst == src and src != None:
						# Found source node
						ptr = {"f_ptr":f_index, "b_ptr":b_index, "i_ptr":i_index}
						self.hit_ptr = ptr
						return True

		# Could Not Find source node
		return False


def IR_Parser( dir_ll, file_name ):
	openfile = dir_ll +"/"+ file_name
	prog = None

	with open(openfile, "r") as llvm_ir:
		"""
		LLVM-IR file-open, and parsing the IR file
		"""
		prog = asm_parser(llvm_ir)
		prog.name = os.path.splitext(file_name)[0]
		print("File: {} parsed.".format(file_name))

		return prog
