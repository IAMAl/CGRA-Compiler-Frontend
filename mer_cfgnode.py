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
import funcs.MergeCFGNodes as MergeCFGNodes
import argparse


parser = argparse.ArgumentParser(description="args")

parser.add_argument('--src_path',   help='source file path',    default='.')
parser.add_argument('--src_name',   help='source file name',    required=True)
parser.add_argument('--w_path',     help='gened file path',     default='.')

args = parser.parse_args()

r_file_path = args.src_path
r_file_name = args.src_name
w_file_path = args.w_path

# Accept both 'foo' and 'foo.ll'; the downstream reader appends .ll itself.
if r_file_name.endswith('.ll'):
    r_file_name = r_file_name[:-3]

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

# Verify LLVM IR source file exists (the reader appends .ll extension)
src_file = os.path.join(r_file_path, r_file_name + ".ll")
if not os.path.exists(src_file):
    print(f"Error: Source file {src_file} does not exist")
    sys.exit(1)

MergeCFGNodes.ExtractCFGNodeMerger( r_file_path, r_file_name, w_file_path )
