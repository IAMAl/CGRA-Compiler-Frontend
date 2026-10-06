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
import utils.FileUtils as progfile
import funcs.Gen_AM as Gen_AM
import argparse


parser = argparse.ArgumentParser(description="args")

parser.add_argument('--src_path',   help='source file path',        default='.')
parser.add_argument('--src_name',   help='source file name',        required=True)
parser.add_argument('--w_path',     help='gened file path',         default='.')
parser.add_argument('--gen_type',   help='gen cfg/dfg',             default='dfg')
parser.add_argument('--zero_rm',    help='block: yes/no',           default='yes')
parser.add_argument('--dst_append', help='mnemonic mode: yes/no',   default='yes')

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

ZERO_REMOVE = True
DST_APPEND  = True
GEN_DFG     = True
if 'cfg' == args.gen_type:
    GEN_DFG     = False

if 'no' == args.zero_rm:
    ZERO_REMOVE = False

if 'yes' == args.dst_append:
    mode = "dst_append"
else:
    mode = "no_dst"

if GEN_DFG:
    prog = progfile.ProgReader( r_file_path=r_file_path, r_file_name=r_file_name)

    # Use input file name as prefix for block files
    file_prefix = r_file_name

    for func in prog.funcs:
        for bblock in func.bblocks:
            name_bblock = bblock.name.replace('\n', '')

            dfg_file_name = f"{file_prefix}_bblock_{name_bblock}_dfg"
            out_file_name = f"{file_prefix}_bblock_{name_bblock}"
            Gen_AM.AMComposer( ZERO_REMOVE=ZERO_REMOVE, mode=mode, r_file_path=r_file_path, r_file_name=dfg_file_name, w_file_path=w_file_path, w_file_name=out_file_name )
else:
    r_file_name = r_file_name+"_cfg"
    w_file_name = r_file_name
    Gen_AM.AMComposer( ZERO_REMOVE=ZERO_REMOVE, mode=mode, r_file_path=r_file_path, r_file_name=r_file_name, w_file_path=w_file_path, w_file_name=w_file_name, directed=True )
