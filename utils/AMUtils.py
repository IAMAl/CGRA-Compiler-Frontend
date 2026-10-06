##################################################################
##
##	ElectronNest_CP
##	Copyright (C) 2024  Shigeyuki TAKANO
##
##  GNU AFFERO GENERAL PUBLIC LICENSE
##	version 3.0
##
##################################################################
import utils.FileUtils as progfile


def AMComposer( lines ):
    """
    Compose Adjacency Matrix (AM)
        AM for Undirected Edges
        am_row: AM Row Constructor
        am:     AM Constructor

    Indices
        row: source node
        clm: connected node

    Diagonal Elements
        AM[row][clm] = 0 when row == clm

    Up-side or Bottomn-side Triange can be used
        Our Implementation uses Upside

    Arguments
        lines: list of text lines from the AM file
    """

    # Adjacency Matrix
    am = []

    # Coluomn Size Counter
    #   for checking matrix shape
    max_clm = 0
    tmp_clm = 0

    # Loop indices (initialized so post-loop checks are safe on empty input)
    row = -1
    clm = -1

    # The empty matrix is written as `[]`: one line with no entries, which
    # is size 0, not a 1x0 matrix.
    lines = [line for line in lines if line.strip() not in ('', '[]')]

    for row, line in enumerate( lines ):

        # Parse Tokens

        line = line.split()

        # Composing Elements in One Row: the brackets of numpy's layout
        # are dropped, the rest are the entries.
        am_row = [int(var) for var in ' '.join(line).replace('[', ' ').replace(']', ' ').split()]
        clm = len(am_row) - 1

        # Error Detection
        if clm > 0 and row != 0 and clm != tmp_clm:
            print("Error: Column Mismatch {} but {} at Row-{}".format( tmp_clm, clm, row ))
        tmp_clm = clm

        if clm > max_clm:
            max_clm = clm

        # Append Composed Row to AM
        am.append( am_row )

    # Check Shape of AM (skip when input was empty)
    if row >= 0 and max_clm != row:
        print("Error: AM should be a square matrix, but shape is {} x {}".format( row, max_clm ))

    return row + 1, am


def Preprocess(r_file_path=".", r_file_name=""):

    file_name = r_file_name+"_am_inv.txt"
    lines = progfile.ReadAM( file_path=r_file_path, file_name=file_name )
    am_size, am = AMComposer( lines )

    return am_size, am
