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
Centralized File Naming Configuration
Eliminates hardcoded file naming conventions across pipeline stages
"""
import os
from typing import Dict, List


class FileNamingConfig:
    """
    Centralized file naming configuration for the compilation pipeline.
    All file naming conventions are defined here to avoid tight coupling.
    """

    # Stage 1: CFG Node Merging
    @staticmethod
    def merged_ir(base_name: str) -> str:
        """Merged LLVM IR file after CFG node merging"""
        return f"{base_name}_merged.ll"

    # Stage 2: Graph Generation
    @staticmethod
    def parsed_prog(base_name: str) -> str:
        """Parsed program text file"""
        return f"{base_name}.txt"

    @staticmethod
    def cfg_graph(base_name: str) -> str:
        """Control Flow Graph (dot format)"""
        return f"{base_name}_cfg.dot"

    @staticmethod
    def cfg_graph_refined(base_name: str) -> str:
        """Refined CFG after duplicate removal"""
        return f"{base_name}_cfg_r.dot"

    @staticmethod
    def dfg_graph_original(base_name: str) -> str:
        """Original Data Flow Graph"""
        return f"{base_name}_dfg_o.dot"

    @staticmethod
    def dfg_graph_refined(base_name: str) -> str:
        """Refined DFG after duplicate removal"""
        return f"{base_name}_dfg_r.dot"

    @staticmethod
    def dfg_graph(base_name: str) -> str:
        """Final Data Flow Graph"""
        return f"{base_name}_dfg.dot"

    @staticmethod
    def bblock_dfg(func_name: str, bblock_name: str) -> str:
        """Per-basic-block DFG"""
        return f"{func_name}_bblock_{bblock_name}_dfg.dot"

    # Stage 3: Adjacency Matrix Generation
    #
    # Two index conventions are emitted and each has its own node list:
    # `_am_inv.txt` pairs with `_node_list.txt` (the pair every later
    # stage reads), and `_am.txt`, whose rows are reversed, pairs with
    # `_node_list_inv.txt`.
    @staticmethod
    def adjacency_matrix(base_name: str) -> str:
        """Adjacency matrix file, rows reversed"""
        return f"{base_name}_am.txt"

    @staticmethod
    def adjacency_matrix_inv(base_name: str) -> str:
        """Adjacency matrix file in node-list order (the one consumed)"""
        return f"{base_name}_am_inv.txt"

    @staticmethod
    def node_list(base_name: str) -> str:
        """Node list for the _am_inv matrix (the one consumed)"""
        return f"{base_name}_node_list.txt"

    @staticmethod
    def node_list_inv(base_name: str) -> str:
        """Node list for the reversed _am matrix"""
        return f"{base_name}_node_list_inv.txt"

    @staticmethod
    def bblock_am(func_name: str, bblock_name: str) -> str:
        """Per-basic-block adjacency matrix, rows reversed"""
        return f"{func_name}_bblock_{bblock_name}_am.txt"

    @staticmethod
    def bblock_am_inv(func_name: str, bblock_name: str) -> str:
        """Per-basic-block adjacency matrix in node-list order (consumed)"""
        return f"{func_name}_bblock_{bblock_name}_am_inv.txt"

    @staticmethod
    def bblock_node_list(func_name: str, bblock_name: str) -> str:
        """Per-basic-block node list (consumed)"""
        return f"{func_name}_bblock_{bblock_name}_node_list.txt"

    @staticmethod
    def bblock_node_list_inv(func_name: str, bblock_name: str) -> str:
        """Per-basic-block node list for the reversed matrix"""
        return f"{func_name}_bblock_{bblock_name}_node_list_inv.txt"

    # Stage 4: Path Generation
    @staticmethod
    def bblock_path_ld_ld(func_name: str, bblock_name: str) -> str:
        """Load-to-load path for basic block"""
        return f"{func_name}_bblock_{bblock_name}_bpath_ld_ld.txt"

    @staticmethod
    def bblock_path_ld_leaf(func_name: str, bblock_name: str) -> str:
        """Load-to-leaf path for basic block"""
        return f"{func_name}_bblock_{bblock_name}_bpath_ld_leaf.txt"

    @staticmethod
    def bblock_path_branch_leaf(func_name: str, bblock_name: str) -> str:
        """Branch-to-leaf path for basic block"""
        return f"{func_name}_bblock_{bblock_name}_bpath_branch_leaf.txt"

    # Stage 5: Loop Detection
    @staticmethod
    def cfg_loop(base_name: str) -> str:
        """CFG loop information (base_name should already include _cfg suffix)"""
        return f"{base_name}_loop.txt"

    # Stage 6: Program Generation
    @staticmethod
    def agu_program(output_name: str, array_name: str) -> str:
        """AGU program for specific array"""
        return f"{output_name}_{array_name}_agu.ll"

    @staticmethod
    def output_manifest(output_name: str) -> str:
        """The list of final outputs a run wrote under this name."""
        return f"{output_name}_outputs.txt"

    @staticmethod
    def datapath_program(output_name: str) -> str:
        """Datapath program"""
        return f"{output_name}_datapath.ll"


class FileCleanup:
    """
    Utility for cleaning up intermediate files on error.
    Provides error recovery functionality.
    """

    @staticmethod
    def cleanup_files(file_paths: List[str], base_path: str = ".") -> Dict[str, bool]:
        """
        Remove intermediate files, tracking success/failure.

        Args:
            file_paths: List of file paths to remove
            base_path: Base directory for the files

        Returns:
            Dictionary mapping file paths to success status
        """
        results = {}
        for file_path in file_paths:
            full_path = os.path.join(base_path, file_path)
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
                    results[file_path] = True
                else:
                    results[file_path] = None  # File didn't exist
            except OSError as e:
                print(f"Warning: Failed to remove {full_path}: {e}")
                results[file_path] = False

        return results
