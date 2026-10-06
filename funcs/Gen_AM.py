##################################################################
##
##	ElectronNest_CP
##	Copyright (C) 2024  Shigeyuki TAKANO
##
##  GNU AFFERO GENERAL PUBLIC LICENSE
##	version 3.0
##
##################################################################
import re

import numpy as np


# A load node is `load_<number>`; a register named `%payload` is not one.
_LOAD_NODE = re.compile(r'^load_\d+$')


def Get_Dst(dot_lines, opcode, first_dst=None):
    """
    The destination recorded for the first edge whose tail is `opcode`.

    `first_dst` is that lookup as a dictionary, kept by the caller; the
    scan over every edge parsed so far made a large block quadratic.
    """
    if first_dst is not None:
        return first_dst.get(opcode, "None")
    for line in dot_lines:
        chk_opcode = line[1]
        if chk_opcode == opcode:
            if len(line) > 2:
                return line[2]
            else:
                return "None"
    return "None"


def _normalize_node_list(node_list):
    """
    Strip stray '"' from the name fields, in place.

    This used to happen as a side effect of the first _write_node_list
    call, which the adjacency-matrix construction below silently relied
    on to match node names. Doing it explicitly keeps the matrices
    correct regardless of the order the files are written in.
    """
    for node in node_list:
        node[1] = node[1].replace('"', '')
        if len(node) > 2:
            node[2] = node[2].replace('"', '')
    return node_list


def _write_node_list(file_path, node_list, mode):
    """
    Write a node list to file_path. Expects _normalize_node_list to have
    been applied already.

    An entry is [id, name, src..., dst] (a leaf is [id, name, 'LEAF']),
    and each line is written as `id name dst src...`. Any number of
    sources is handled: a CFG block with three predecessors used to have
    its third one written in the dst column and a fourth dropped.
    """
    with open(file_path, "w") as node_list_file:
        for node in node_list:
            node_list_file.write(str(node[0]) + " " + node[1])

            if len(node) > 3 and mode == "dst_append":
                node_list_file.write(" " + node[-1] + " " + " ".join(node[2:-1]) + "\n")
            elif len(node) > 2 and mode == "dst_append":
                node_list_file.write(" None " + node[2] + "\n")
            else:
                node_list_file.write(" " + node[2] + "\n")


def _remove_zero_rows_cols(matrix):
    """
    Drop the nodes with no edge at all: their row and column together.

    Returns:
        (matrix, kept_indices) -- the reduced matrix and the original row
        indices that survived. Callers must filter the node list with
        kept_indices: dropping rows from the matrix without dropping the
        matching node entries left every downstream index-to-node lookup
        pointing at the wrong node.

    A node is kept when its row or its column has an edge. On a
    symmetric matrix the two agree; on a directed one a sink such as the
    `ret` pseudo-block has an empty row but a live column and must stay.
    """
    matrix = np.asarray(matrix)
    if matrix.size == 0:
        return np.zeros((0, 0), dtype=np.int8), []
    live = matrix.any(axis=1) | matrix.any(axis=0)
    kept_indices = [int(i) for i in np.flatnonzero(live)]
    if not kept_indices:
        return np.zeros((0, 0), dtype=np.int8), []
    return matrix[live][:, live], kept_indices


def _filter_node_list(node_list, kept_indices):
    """
    Keep only the nodes whose matrix row survived zero-removal and
    renumber them, so that node[0] again equals the node's row index.
    """
    if kept_indices is None:
        return node_list

    filtered = []
    for new_index, old_index in enumerate(kept_indices):
        if old_index >= len(node_list):
            continue
        node = list(node_list[old_index])
        node[0] = new_index
        filtered.append(node)
    return filtered


def _write_am(file_path, am):
    """
    Write a 0/1 adjacency matrix to file_path in numpy's text layout
    (`[[0 1]\n [1 0]]`), one row per line. numpy's own formatter took
    minutes and gigabytes on a 10 000-node block.
    """
    am = np.asarray(am)
    with open(file_path, "w") as am_file:
        if am.size == 0:
            am_file.write('[]')
            return
        am_file.write('[')
        for number, row in enumerate(am):
            am_file.write(('' if number == 0 else '\n ') + '[' + ' '.join(map(str, row.tolist())) + ']')
        am_file.write(']')


def AMComposer( ZERO_REMOVE=False, mode="dst_append", r_file_path=".", r_file_name="", w_file_path=".", w_file_name="", directed=False ):
    """
    Adjacency Matrix Composer

    Arguments:
        r_file_path:  path for input file
        r_file_name:  input file name
        w_file_path:  path for output file
        w_file_name:  output file name
        directed:     keep edge direction: am[from][to] = 1 for a dot
                      edge `from -> to`. The data flow graphs are walked
                      undirected, but the control flow graph needs its
                      direction for loop detection -- symmetric, a
                      two-block loop is not a cycle.

    Function
        - Generates File representing Adjacency Matrix
        - Generates File representing Node List
        - Files having Postfix "_inv" is an Inverse AM and is Node List
    """

    # Parsing
    # Feeding dot file, and split with "->"
    dot_lines = []
    first_dst = {}

    openfile = r_file_path +"/"+ r_file_name+".dot"
    with open(openfile, "r") as dot_file:
        for present_line in dot_file:

            present_line = present_line.split(' -> ')

            tmp_line = []
            if len(present_line) > 1:
                present_line[1] = present_line[1].split('[')
                if len(present_line[1]) > 1:
                    tmp = present_line[1][1].split(' label=')
                    if len(tmp) > 1:
                        dst =  Get_Dst(dot_lines, present_line[1][0].replace('"', ''), first_dst)
                        tmp_line.append(present_line[1][0])
                        tmp_line.append(present_line[0])
                        # tmp[1] is the tail of a dot edge attribute list,
                        # e.g. '"%21"]'. Take the quoted label out of it.
                        tmp = tmp[1].strip().rstrip(']').strip('"')
                        tmp_line.append(tmp)
                        tmp_line.append(dst)
                        present_line = tmp_line
                    else:
                        dst =  Get_Dst(dot_lines, present_line[1][0].replace('"', ''), first_dst)
                        tmp_line.append(present_line[1][0])
                        tmp_line.append(present_line[0])
                        tmp_line.append(dst)
                        present_line = tmp_line
                else:
                    dst =  Get_Dst(dot_lines, present_line[0].replace('"', ''), first_dst)
                    tmp_line.append(present_line[0])
                    tmp_line.append(present_line[1][0])
                    tmp_line.append(dst)
                    present_line = tmp_line
            elif len(present_line) > 0:
                present_line[0] = present_line[0].split('[')[0]

            # Remove Unnecessary Chars from all elements
            for i in range(len(present_line)):
                present_line[i] = present_line[i].replace('" ', '')
                present_line[i] = present_line[i].replace('"', '')

            if len(present_line) > 1:
                dot_lines.append(present_line)
                first_dst.setdefault(present_line[1],
                                     present_line[2] if len(present_line) > 2 else "None")


    # Node-ID Composition
    leaf_node_list = []
    node_list = []
    node_index = {}          # node name -> position in node_list
    dst_found_list = []
    src_found_list = set()
    leaf_names = set()
    # Edges whose head is a given name, for the "is this a source" test.
    heads_all = {}
    for no, nodes in enumerate(dot_lines):
        heads_all.setdefault(nodes[0], []).append(no)
    for no, nodes in enumerate(dot_lines):
        # Check Node in Destination
        dst_node = nodes[0].replace('"', '')
        src_node = nodes[1].replace('"', '')

        if len(nodes) > 3:
            src_index = nodes[2].replace('"', '')
            dst_index = nodes[-1].replace('"', '')
        elif len(nodes) > 2:
            src_index = nodes[1].replace('"', '')
            dst_index = nodes[-1].replace('"', '')
        elif len(nodes) > 1:
            src_index = nodes[1].replace('"', '')
            dst_index = "SINK"
        else:
            src_index = "LEAF"


        # Register Node to List
        find_dst = dst_node in node_index
        index = node_index.get(dst_node, 0)

        if not find_dst:
            if not no in src_found_list:
                dst_found_list.append(no)
                node_index[dst_node] = len(node_list)
                node_list.append([no, dst_node, src_index, dst_index])


        # Check 2nd Source, add 2nd Source to List-entry if available
        if find_dst:
            if len(nodes) > 1:
                if len(node_list[index]) > 3:
                    node_list[index] = node_list[index][:len(node_list[index])-1]+[src_index]+[node_list[index][len(node_list[index])-1]]
                elif len(node_list[index]) > 2:
                    node_list[index] = node_list[index]+[" "+src_index]

        # Check Node in Source: is this name the head of a later edge?
        src_node = nodes[1]
        find = any(later > no for later in heads_all.get(src_node, ()))

        # Register
        if not find:
            if no in src_found_list or src_node in leaf_names:
                find = True
            if not find and not _LOAD_NODE.match(src_node):
                src_found_list.add(no)
                leaf_names.add(src_node)
                leaf_node_list.append([ no, src_node, "LEAF" ])


    # Node-ID Sorting
    for no, node in enumerate(node_list):
        node_list[no][0] = no

    # Append Leaf-Node to Node-List
    len_entry = len(node_list)
    count = 0
    for index, leaf_node in enumerate(leaf_node_list):
        if leaf_node[1] not in node_index and not _LOAD_NODE.match(leaf_node[1]):
            node_index[leaf_node[1]] = len(node_list)
            node_list.append([len_entry+count, leaf_node[1], leaf_node[2]])
            count += 1

    # Normalize names before any matrix construction: the edge lists and
    # the node list must agree on how a node is spelled.
    _normalize_node_list(node_list)

    # Inverse-AM Composition
    #
    # Two index conventions are emitted:
    #   _am_inv.txt  rows follow node_list order  -> paired with _node_list.txt
    #   _am.txt      rows are reversed            -> paired with _node_list_inv.txt
    # The node lists are written after the matrices so that zero-removal can
    # drop the matching node entries; previously the node lists were written
    # first and unfiltered, so the two halves of each pair disagreed.

    # Compose Inverse-AM
    # Names were normalised above, so the lookup is rebuilt from them.
    position = {}
    for no, node in enumerate(node_list):
        position.setdefault(node[1], no)

    iam = np.zeros((len(node_list), len(node_list)), dtype=np.int8)
    for line in dot_lines:
        src_node = line[0].replace('"', "")
        dst_node = line[1].replace('"', "")

        src_no = position.get(src_node)
        dst_no = position.get(dst_node)

        # line[0] is the edge's head (the dot target), line[1] its tail.
        if src_no is not None and dst_no is not None:
            iam[dst_no][src_no] = 1
            if not directed:
                iam[src_no][dst_no] = 1


    # Remove Zero-Row and Zero-Column
    iam_kept = None
    if ZERO_REMOVE:
        iam, iam_kept = _remove_zero_rows_cols(iam)

    iam = np.array(iam)

    # Output The Inverse-AM and the node list whose order it follows
    _write_am(w_file_path +"/"+ w_file_name+"_am_inv.txt", iam)
    _write_node_list(w_file_path +"/"+ w_file_name+"_node_list.txt",
                     _filter_node_list(node_list, iam_kept), mode)

    # AM Composition
    # Compose AM
    am = np.zeros((len(node_list), len(node_list)), dtype=np.int8)
    for line in dot_lines:
        src_node = line[0].replace('"', "")
        dst_node = line[1].replace('"', "")

        src_no = position.get(src_node)
        dst_no = position.get(dst_node)
        if src_no is not None:
            src_no = len(node_list) - src_no - 1
        if dst_no is not None:
            dst_no = len(node_list) - dst_no - 1

        if src_no is not None and dst_no is not None:
            am[dst_no][src_no] = 1
            if not directed:
                am[src_no][dst_no] = 1

    # Remove Zero-Row and Zero-Column
    am_kept = None
    if ZERO_REMOVE:
        am, am_kept = _remove_zero_rows_cols(am)

    am = np.array(am)

    #   Output AM and the reversed node list its rows follow
    _write_am(w_file_path +"/"+ w_file_name+"_am.txt", am)
    _write_node_list(w_file_path +"/"+ w_file_name+"_node_list_inv.txt",
                     _filter_node_list(list(reversed(node_list)), am_kept), mode)
