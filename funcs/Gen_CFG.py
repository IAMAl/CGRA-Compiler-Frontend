##################################################################
##
##	ElectronNest_CP
##	Copyright (C) 2024  Shigeyuki TAKANO
##
##  GNU AFFERO GENERAL PUBLIC LICENSE
##	version 3.0
##
##################################################################
import utils.DrawUtils as drawutils


DEBUG = False


def cfg_extractor( prog, out ):
    """
    Control Graph Extractor

    One dot edge per branch target of each block's terminator: both arms
    of a conditional branch, the target of a jump, and the default and
    every case of a switch. Targets are resolved within the block's own
    function: numbered labels restart per function, so searching every
    function joined unrelated blocks. A block may branch to itself, and
    every block that returns gets an edge to the `ret` pseudo-block.
    """
    for func in prog.funcs:
        names = {bblock.name for bblock in func.bblocks if bblock.name is not None}
        for bblock in func.bblocks:
            if not bblock.instrs:
                continue
            last = bblock.instrs[-1]
            fro = bblock.name

            if last.opcode == "br":
                colours = ["blue", "green"]
            elif last.opcode == "jmp":
                colours = ["red"]
            else:
                colours = ["black"] * len(last.targets)
            if fro == "entry":
                colours = ["black"] * len(last.targets)

            for target, colour in zip(last.targets, colours):
                if DEBUG:
                    print(" target :{} -> {}".format(fro, target))
                if target in names:
                    out.write("\"%s\" -> \"%s\"[color=%s dir=black]\n" % (fro, target, colour))

            if last.opcode == "ret":
                out.write("\"%s\" -> \"%s\"[color=black dir=black]\n" % (fro, "ret"))

    out.write("}")


def dupl_remover_cfg( w_file_path, w_file_name, prog ):
    openfile = w_file_path + '/' + w_file_name

    with open(openfile, "r") as dot_file:
        present_lines = dot_file.readlines()

    # Order-preserving dedup
    seen = set()
    deduped = []
    for line in present_lines:
        if line not in seen:
            seen.add(line)
            deduped.append(line)

    if DEBUG:
        num_dup = len(present_lines) - len(deduped)
        print("Total {} lines removed.".format(num_dup))

    out_file_name = w_file_path + "/" + prog.name + "_cfg_r.dot"
    with open(out_file_name, "w") as dot_file:
        dot_file.writelines(deduped)


def Main_Gen_LLVMtoCFG( prog, w_file_path ):

    w_file_name = prog.name + "_cfg.dot"

    with open(w_file_path+"/"+w_file_name, "w") as out:
        # Graph Utilities
        g_cfg = drawutils.GraphUtils(out)

        # Graph Header Description
        g_cfg.start_cf_graph()
        cfg_extractor(prog=prog, out=out)

    # Reform Graph
    dupl_remover_cfg(w_file_path, w_file_name, prog)
