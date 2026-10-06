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
import utils.FileUtils as fileutils
import utils.AMUtils as amutils
import utils.GraphUtils as graphutils
import funcs.Gen_Path as genpath
import argparse


parser = argparse.ArgumentParser(description="args")

parser.add_argument('--src_path',   help='source file path',    default='.')
parser.add_argument('--src_name',   help='source file name',    required=True)
parser.add_argument('--w_path',     help='gened file path',     default='.')
parser.add_argument('--branch_leaf', action='store_true',
                    help='also enumerate every branch-to-leaf path per block '
                         '(exponential in a graph that fans out and joins; off by default)')

args = parser.parse_args()

r_file_path = args.src_path
r_file_name = args.src_name
w_file_path = args.w_path

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

# Verify source file exists (ProgReader expects .txt extension)
file_prefix = fileutils.program_base_name(r_file_name)
src_file = os.path.join(r_file_path, file_prefix + '.txt')
if not os.path.exists(src_file):
    print(f"Error: Source file {src_file} does not exist")
    sys.exit(1)

prog = fileutils.ProgReader( r_file_path=r_file_path, r_file_name=r_file_name )

for func in prog.funcs:
    for bblock in func.bblocks:
        name_bblock = bblock.name.replace('\n', '')
        block_file_name = f"{file_prefix}_bblock_{name_bblock}"
        print(f"Processing: BBlock-{name_bblock}")

        am_size, am = amutils.Preprocess( r_file_path, block_file_name )
        NodeList = graphutils.ReadNodeList(block_file_name, r_file_path)

        genpath.Gen_Path( am, NodeList, w_file_path, block_file_name, branch_leaf=args.branch_leaf )
