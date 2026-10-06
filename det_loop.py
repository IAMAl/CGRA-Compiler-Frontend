##################################################################
##
##	ElectronNest_CP
##	Copyright (C) 2024  Shigeyuki TAKANO
##
##  GNU AFFERO GENERAL PUBLIC LICENSE
##	version 3.0
##
##################################################################
import os
import sys
import utils.AMUtils as amutils
import utils.GraphUtils as graphutils
import funcs.Det_Loop as Det_Loop
import argparse


parser = argparse.ArgumentParser(description="args")

parser.add_argument('--src_path',   help='source file path',    default='.')
parser.add_argument('--src_name',   help='source file name',    required=True)
parser.add_argument('--w_path',     help='gened file path',     default='.')
parser.add_argument('--w_name',     help='output file name',    required=True)

args = parser.parse_args()

r_file_path = args.src_path
r_file_name = args.src_name
w_file_path = args.w_path
w_file_name = args.w_name

# Verify paths exist
if not os.path.exists(r_file_path):
    print(f"Error: Source path {r_file_path} does not exist")
    sys.exit(1)

if not os.path.exists(w_file_path):
    try:
        os.makedirs(w_file_path)
    except OSError as e:
        print(f"Error creating output path {w_file_path}: {e}")
        sys.exit(1)

# Preprocess() reads the *inverse* matrix, so that is the file whose
# absence must be reported here.
am_file = os.path.join(r_file_path, f"{r_file_name}_am_inv.txt")
if not os.path.exists(am_file):
    print(f"Error: Adjacency matrix file {am_file} does not exist")
    print(f"Please run gen_am.py first to generate the adjacency matrix")
    sys.exit(1)

am_size, am = amutils.Preprocess(r_file_path=r_file_path, r_file_name=r_file_name)
names = [node[1] for node in graphutils.ReadNodeList(r_file_name, r_file_path)]

# The entry block is the function's first block, read from the IR the
# graph was drawn from (`<base>_cfg` comes from `<base>.ll`): choosing
# it by the name `entry` took a later block of that name for the
# entry and reported a loop that does not exist.
loops = Det_Loop.DetectLoops(am, names, entry=Det_Loop.first_block(
    os.path.join(r_file_path, r_file_name[:-len('_cfg')] + '.ll')))

if loops:
    print("Cycle: {} in Graph {}".format(loops, r_file_name))
else:
    print("No Cycles in Graph {}".format(r_file_name))

openfile = os.path.join(w_file_path, w_file_name + "_loop.txt")
with open(openfile, "w") as cfg_cycle_file:
    cfg_cycle_file.writelines(str(loops))
