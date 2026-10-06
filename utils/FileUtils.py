##################################################################
##
##	ElectronNest_CP
##	Copyright (C) 2024  Shigeyuki TAKANO
##
##  GNU AFFERO GENERAL PUBLIC LICENSE
##	version 3.0
##
##################################################################
import ast
import os

import utils.ProgConstructor as progconst

# Number of fields ProgWriter emits per instruction record.
_NUM_INSTR_FIELDS = 9


def ReadFile( file_path=".", file_name="" ):
    """
    File-Open used for CFG (cyclic loops) file

    Arguments
        file_path:    path (directory) for source file
        file_name:    name of file for source file
    """
    with open(file_path +"/"+ file_name, "r") as file:
        lines = []
        for line in file:
            #print("reading line: {}".format(line))
            line = line.replace("\n", '')
            lines.append(line)

        return lines


def ProgWriter( prog, w_file_path=".", w_file_name="" ):
    """
    Program File Read and Composition

    Arguments:
        w_file_path:        Writinging File Path
        w_file_name:        File Name

    Function:
        - Write parsed program to file
    """
    openfile = w_file_path +"/"+ w_file_name
    with open(openfile, "w") as program:
        program.write("program {}\n".format(prog.name))
        for func in prog.funcs:
            program.write("\nbegin function {}\n".format(func.name))
            for bblock in func.bblocks:
                program.write("\nbegin bblock {}\n".format(bblock.name))
                for instr in bblock.instrs:
                    #print(instr.operands)
                    instruction = []
                    instruction.append(instr.opcode)     #Opcode Name                String
                    instruction.append(instr.dst)        #Destination Name           String
                    instruction.append(instr.d_type)     #Destination Data-Type      String
                    instruction.append(instr.operands)   #Source Name                String
                    instruction.append(instr.func)       #Function Name              String
                    instruction.append(instr.br_t)       #Lavel for Branch Taken     Bool
                    instruction.append(instr.br_f)       #Lavel for Branch Not Taken Bool
                    instruction.append(instr.imm)        #Immediate Value            String
                    instruction.append(instr.nemonic)    #Nemonic (Assembly Code)    String
                    program.writelines(str(instruction)+"\n")
                program.write("end bblock {}\n".format(bblock.name))
            program.write("\nend function {}\n".format(func.name))


def program_base_name( name ):
    """
    The base name of a parsed program, given either the base name itself
    (`mmm_merged`), the parsed file (`mmm_merged.txt`) or the IR file
    (`mmm_merged.ll`).

    Only those two suffixes are stripped. splitext() or split('.') took
    `.prog` off `my.prog`, so a dotted stem was looked up under the wrong
    name.
    """
    for suffix in ('.txt', '.ll'):
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def ProgReader( r_file_path=".", r_file_name="" ):
    """
    Program File Read and Composition

    Arguments:
        r_file_path:        Reading File Path
        r_file_name:        File Name

    Function:
        - Read File of parsed program
        - Compose program() class
    """
    openfile = os.path.join(r_file_path, program_base_name(r_file_name) + '.txt')
    with open(openfile, "r") as prog_file:
        in_prog = False
        in_func = False
        in_bblock = False
        for line in prog_file:
            if "program" in line:
                prog = progconst.program()
                prog.name = line.split(" ")[1].strip().replace('"', '')
                in_prog = True
            elif "begin function" in line:
                func = progconst.function()
                func.name = line.split(" ")[2].strip().replace('"', '')
                in_func  = True
            elif "begin bblock" in line:
                bblock = progconst.basicblock()
                # strip() here so callers no longer have to peel a trailing
                # newline off the block name before using it in a filename.
                bblock.name = line.split(" ")[2].strip().replace('"', '')
                in_bblock  = True
            elif "end bblock" in line:
                func.bblocks.append(bblock)
                in_bblock  = False
            elif "end function" in line:
                prog.funcs.append(func)
                in_func  = False
            elif in_prog and in_func and in_bblock:
                # ProgWriter emits each instruction as repr(list), so the
                # line is a Python literal and round-trips exactly. The old
                # reader split on '"' -- a character repr() never produces --
                # so it never reached the final field and never appended a
                # single instruction to the block.
                line = line.strip()
                if not line:
                    continue
                try:
                    fields = ast.literal_eval(line)
                except (SyntaxError, ValueError):
                    print(f"Warning: unparsable instruction line: {line}")
                    continue
                if not isinstance(fields, list) or len(fields) < _NUM_INSTR_FIELDS:
                    print(f"Warning: unexpected instruction record: {line}")
                    continue

                instr = progconst.instruction()
                instr.opcode = fields[0]        # Opcode Name                String
                instr.dst = fields[1]           # Destination Name           String
                instr.d_type = fields[2]        # Destination Data-Type      String
                operands = fields[3]            # Source Names               List
                instr.operands = list(operands) if isinstance(operands, list) else [operands]
                instr.func = fields[4]          # Function Name              String
                instr.br_t = fields[5]          # Lavel for Branch Taken     Bool
                instr.br_f = fields[6]          # Lavel for Branch Not Taken Bool
                instr.imm = fields[7]           # Immediate Value            String
                instr.nemonic = fields[8]       # Nemonic (Assembly Code)    String
                bblock.append(instr)
    return prog


def ReadAM( file_path=".", file_name="" ):
    """
    File-Open used for AM file

    Arguments
        file_path:    path (directory) for source file
        file_name:    name of file for source file

    Returns
        list of lines (file is closed before return)
    """

    with open( file_path +'/'+ file_name ) as f:
        return f.readlines()
