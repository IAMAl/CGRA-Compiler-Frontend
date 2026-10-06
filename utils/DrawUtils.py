##################################################################
##
##	ElectronNest_CP
##	Copyright (C) 2024  Shigeyuki TAKANO
##
##  GNU AFFERO GENERAL PUBLIC LICENSE
##	version 3.0
##
##################################################################

class GraphUtils:
    """
    Utilities for Graph-Drawing
    """
    def __init__( self, out ):
        self.count = 0
        self.edges = []
        self.out = out

    def write( self, line="" ):
        """
        Module for writing into a file
        """
        self.out.write(line + "\n")

    def start_df_graph( self ):
        """
        dot-file header descriptor for dfg
        """
        self.write("digraph G {")
        self.write("compound=true")
        self.write('label="Black Edges - Data-Flow"')

    def start_cf_graph( self ):
        """
        dot-file header descriptor for cfg
        """
        self.write("digraph G {")
        self.write("compound=true")
        self.write('label="Red Edges - Jump, Blue - Taken, Green - NOT Taken"')

    def edge( self, fro, to, extra="" ):
        """
        edge descriptor
        source node to destination node
        "extra" defines attribution (color, etc) of edge
        """
        self.edges.append("\"%s\" -> \"%s\"%s" % (fro, to, extra))

    def Count( self ):
        self.count += 1

    def ReadCnt( self ):
        return self.count
