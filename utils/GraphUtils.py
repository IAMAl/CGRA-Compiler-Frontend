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
Helpers for reading the node lists emitted by Gen_AM.

This module used to also carry Node / EdgeTab / Create_CFGNode(s) and a
family of cycle- and echo-detection helpers. None of them had a caller:
their only entry point was FileUtils.ReadDFG, which was itself dead. They
were removed rather than left as a second, untested implementation of the
graph traversal that Det_Loop and Gen_Path actually use.
"""
import os
from typing import List


def ReadNodeList(r_file_name: str, r_file_path: str = ".") -> List[List[str]]:
    """
    Read '<r_file_name>_node_list.txt' into a list of node records.

    Each line is whitespace separated:
        <node id> <opcode> <dst> <src>...
    and is returned as a list of its fields, with newlines stripped.
    """
    node_list_file = os.path.join(r_file_path, r_file_name + "_node_list.txt")

    node_list = []
    with open(node_list_file, "r") as node_file:
        for line in node_file:
            node_list.append([item.replace('\n', '') for item in line.split(" ")])

    return node_list
