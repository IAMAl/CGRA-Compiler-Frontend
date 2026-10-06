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
Data-flow paths of one basic block, from its adjacency matrix.

Three kinds are written per block: load-to-load (`ld_ld`), load-to-leaf
(`ld_leaf`) and branch-to-leaf (`branch_leaf`). The store-rooted kinds
that used to be written alongside them had no reader and were built by a
formatter that spliced unrelated paths together through a shared
constant leaf, so they are gone.
"""
import re

import numpy as np


class Path:
	def __init__( self ):
		self.st_route_path = []
		self.st_ld_path = []
		self.st_leaf_path = []
		self.ld_ld_path = []
		self.ld_leaf_path = []

		self.Branch_St = []
		self.Branch_Ld = []

		self.Branch = []

	def Register( self, path_select, path ):
		if path_select == 'st_route_path':
			self.st_route_path.append( path[:] )

		elif path_select == 'st_ld_path':
			self.st_ld_path.append( path[:] )

		elif path_select == 'st_leaf_path':
			self.st_leaf_path.append( path[:] )

		elif path_select == 'ld_ld_path':
			self.ld_ld_path.append( path[:] )

		elif path_select == 'ld_leaf_path':
			self.ld_leaf_path.append( path[:] )

	def Get( self, path_select ):
		if path_select == 'st_route_path':
			return self.st_route_path

		elif path_select == 'st_ld_path':
			return self.st_ld_path

		elif path_select == 'st_leaf_path':
			return self.st_leaf_path

		elif path_select == 'ld_ld_path':
			return self.ld_ld_path

		elif path_select == 'ld_leaf_path':
			return self.ld_leaf_path

	def Push( self, index ):
		self.Branch.append( index )

	def StPush( self, index ):
		self.Branch_St.append( index )

	def LdPush( self, index ):
		self.Branch_Ld.append( index )


# A node's mnemonic is `<opcode>_<number>`; a register named `%payload`
# or an array `@brick` must not look like a load or a branch.
_STORE_NODE = re.compile(r'^store_\d+$')
_LOAD_NODE = re.compile(r'^load_\d+$')


def is_StNode( mnemonic ):
	return _STORE_NODE.match( mnemonic[1] ) is not None


def is_LdNode( mnemonic ):
	return _LOAD_NODE.match( mnemonic[1] ) is not None


def is_LeafNode( mnemonic ):
	# A leaf entry is [id, name, 'LEAF'] exactly (Gen_AM); a node whose
	# source operand is a global named `@LEAFS` or a register `%LEAF`
	# is not one, and taking it for one left the exploration spinning.
	return len(mnemonic) > 2 and mnemonic[2] == 'LEAF'


def Get_NeighborNode( row ):
	NNodes = []
	for index, elm in enumerate( row ):
		if elm == 1:
			NNodes.append( index )
	return NNodes


def Get_Mnemonic( NodeList, index ):
	return NodeList[ index ]


class Explored:
	"""
	The explored-edge matrix, with the count of entries in which it still
	differs from the adjacency matrix kept per row.

	The exploration used to recompute `am ^ em` and scan every row on
	every step, which made a block of N nodes cost O(N^3); the counts
	make the same query O(N).
	"""

	def __init__( self, am ):
		size = len( am )
		self.am = am
		self.em = np.zeros(( size, size ), dtype=np.int8 )		# 0/1: int64 cost gigabytes on large blocks
		self.diff = [int(sum(1 for v in row if v == 1)) for row in am]

	def mark( self, src_idx, dst_idx ):
		if dst_idx == src_idx:
			return
		for a, b in ((src_idx, dst_idx), (dst_idx, src_idx)):
			if self.em[a][b] == 0:
				self.em[a][b] = 1
				# An explored entry the graph does not have counts as a
				# difference, exactly as the xor did.
				self.diff[a] += -1 if self.am[a][b] == 1 else 1

	def non_explored( self ):
		return [idx for idx, count in enumerate( self.diff ) if count > 0]


def Set_Explored( em, src_idx, dst_idx ):
	em.mark( src_idx, dst_idx )
	return em


def Get_NonExploredNodes( am, em ):
	return em.non_explored()


def is_ParentNodeExist( NNodes, index ):
	count = 0
	for node in NNodes:
		if node < index:
			count += 1
	return count


def Explore_Path( am, NodeList ):

	path = Path()

	TotalNumNodes = len( am[0] ) if len( am ) else 0		# an edge-less block has an empty matrix
	PtrList = np.zeros( TotalNumNodes, dtype=int )
	em = Explored( am )
	neighbors = [Get_NeighborNode( row ) for row in am]

	# Counter
	#   count number of nodes arrived
	CountNodes = 0

	# Store instruction related path lists
	st_ld_path = []
	st_route_path = []
	st_leaf_path = []

	# Load instruction related path lists
	ld_ld_path = []
	ld_leaf_path = []

	# Path event flags
	start_st = False
	start_ld_ld = False
	start_ld_leaf = False

	# Branch node stack
	Branch = []

	# Node ID (index of Adjacency Matrix)
	index = 0
	tmp_index = 0
	nlist = []

	# The loop ends when every node has been visited or nothing is left to
	# explore. The previous condition ORed `len(nlist) == 0`, which is true
	# exactly when exploration has finished, so the guard never stopped the
	# loop and only the break statements below could end it.
	#
	# Every step marks an edge, advances a pointer or pops a branch, so a
	# walk needs on the order of the nodes plus the edges; the exploration
	# measures at about two steps per node. A walk far beyond that is
	# stuck (a node it never counts as visited), and an error names it
	# rather than the stage running forever.
	edges = sum( len( row ) for row in neighbors )
	limit = 32 * ( TotalNumNodes + 1 ) + 8 * edges
	steps = 0
	while CountNodes <= (TotalNumNodes + 1) and NodeList:
		steps += 1
		if steps > limit:
			raise RuntimeError(
				f"path exploration did not finish after {limit} steps over {TotalNumNodes} nodes "
				f"(stuck at node {index}, {NodeList[index][1] if index < len(NodeList) else '?'})" )

		nlist = Get_NonExploredNodes( am, em )

		# Fetch Neighbor Nodes
		NNodes = neighbors[ index ]

		# Fetch Mnemonic
		mnemonic = Get_Mnemonic( NodeList, index )

		# Number of Parent Nodes
		num_parent_nodes = is_ParentNodeExist( NNodes, index )


		br = False

		if not is_LeafNode( mnemonic ):
			if len(NNodes) > 2:
				br = True

			# Register arriving the branch node
			if ( len(NNodes) - num_parent_nodes ) >= 2 and PtrList[ index ] < 1:
				Branch.append( int(mnemonic[0]) )

			CountNodes += 1
			tmp_index = index

			if is_StNode( mnemonic ):
				# Store instruction (first or subsequent — same handling;
				#   supports multiple stores in a basic block)
				start_st = True
				path.StPush( index )

				# Register Path Node
				if not start_ld_ld:
					st_ld_path.append( index )
				st_route_path.append( index )
				st_leaf_path.append( index )

			elif is_LdNode( mnemonic ) and not start_ld_ld:
				# Node is first load instruction
				start_ld_ld = True
				start_ld_leaf = True
				path.LdPush( index )

				# Register Path Node
				if start_st:
					st_route_path.append( index )
					st_leaf_path.append( index )
					st_ld_path.append( index)
					path.Register( 'st_ld_path', st_ld_path )
					st_ld_path = []

				# Register Path Node
				ld_ld_path.append( index )
				ld_leaf_path.append( index )

			elif is_LdNode( mnemonic ) and start_ld_ld:
				# Node is second load instruction

				start_ld_leaf = True
				path.LdPush( index )

				# Register Path Node
				if start_st:
					st_route_path.append( index )
					st_leaf_path.append( index )

				# Register Path Node. The path can be empty here when the
				# first load was reached through a branch that reset it,
				# as in a body that only copies one array into another.
				if ld_ld_path and index < ld_ld_path[-1]:
					ld_ld_path = []
				else:
					ld_ld_path.append( index )
					path.Register( 'ld_ld_path', ld_ld_path )
				ld_leaf_path = [index]
				if len(Branch) > 1:
					append_point = Branch[-1]
					if append_point in ld_ld_path:
						branch_index = ld_ld_path.index(append_point)
						ld_ld_path = ld_ld_path[0:branch_index]
					else:
						ld_ld_path = []
						start_ld_ld = False
				else:
					ld_ld_path = []
					start_ld_ld = False

			else:
				# Node is common instruction
				# Register Path Node
				if start_st:
					if not start_ld_ld:
						if len(st_leaf_path) > 0 and len(Branch) > 0:
							append_no = Branch[-1]
							st_ld_path = st_leaf_path[:append_no+1]
						st_ld_path.append( index )

					st_leaf_path.append( index )

					st_route_path.append( index )

				# Register Path Node
				if start_ld_ld:
					if len(ld_ld_path) > 0 and index < ld_ld_path[-1]:
						ld_ld_path = []
						ld_leaf_path = []

						start_ld_ld = False
					else:
						ld_ld_path.append( index )
						ld_leaf_path.append( index )


			tmp_index = index
			if PtrList[ index ] > len( NNodes ):
				if len(Branch) > 0:
					index = Branch.pop(-1)
					CountNodes -= 1
				else:
					break  # No more branches to explore
			elif PtrList[ index ]  >= 2:
				if len(nlist) > 0:
					index = nlist[0]
				else:
					break
			elif br:
				if num_parent_nodes > 1:
					offset = num_parent_nodes + PtrList[ index ]
					index = NNodes[ min(offset, len(NNodes) - 1) ]
					CountNodes -= 1
				else:
					offset = PtrList[ index ] + 1
					index = NNodes[ min(offset, len(NNodes) - 1) ]
					# NNodes belongs to the node we just left, but the
					# pointer read here is the one of the node we moved to,
					# so it can run past the end. A dense block -- several
					# products, each unrolled -- reaches that case.
					check_offset = PtrList[ index ]
					if check_offset < len(NNodes):
						check_mnemonic = Get_Mnemonic( NodeList, NNodes[ check_offset ] )
						if is_LdNode( check_mnemonic ):
							start_ld_ld = True
			else:
				if is_StNode( mnemonic ) or (is_LdNode( mnemonic ) and len(NNodes) > 2):
					index = NNodes[ PtrList[ index ] ]
				elif len(NNodes) > 1 and (PtrList[ index ]+1) < len(NNodes):
					index = NNodes[ PtrList[ index ]  + 1 ]
				elif PtrList[ index ] < len(NNodes):
					index = NNodes[ PtrList[ index ] ]
				else:
					index = NNodes[-1]

			if PtrList[ index ] < len(NNodes):
				PtrList[ tmp_index ] += 1

			# Set explored node
			em = Set_Explored( em, tmp_index, index )

		elif is_LeafNode( mnemonic ):
			PtrList[ index ] += 1

			# Register Path Node
			tmp_index = index
			if start_st:
				st_route_path.append( index )
				st_leaf_path.append( index )
				path.Register( 'st_route_path', st_route_path )
				path.Register( 'st_leaf_path', st_leaf_path )
				st_route_path = []
				st_leaf_path = []

				if len(Branch) > 0:
					append_point = Branch[-1]
					if append_point in st_ld_path:
						branch_index = st_ld_path.index(append_point)
						st_ld_path = st_ld_path[0:branch_index]
				else:
					st_ld_path = []

			# Register Path Node
			if start_ld_leaf:
				ld_leaf_path.append( index )
				path.Register( 'ld_leaf_path', ld_leaf_path )
				ld_leaf_path = []  # クリア
				start_ld_leaf = False
				if start_ld_ld and len(Branch) > 0:
					append_point = Branch[-1]
					if append_point in ld_ld_path:
						branch_index = ld_ld_path.index(append_point)
						ld_ld_path = ld_ld_path[0:branch_index]
				elif len(ld_ld_path)>0 and index < ld_ld_path[-1]:
					ld_ld_path = []
					start_ld_ld = False

			path.Push( index )
			nlist = Get_NonExploredNodes( am, em )
			if len(Branch) > 0:
				index = Branch.pop(-1)
			elif len(nlist) > 0:
				index = nlist[0]
			else:
				break

		# Check Remained Node
		#   exit when there is not remained

	return path


def is_BranchNode( mnemonic ):
	# Only the branch itself roots a path. Starting from the compare as
	# well would emit sub-paths already covered by the branch's paths.
	return len(mnemonic) > 1 and mnemonic[1].split('_')[0] in ('br', 'switch')


def Get_Branch_Leaf_Paths( am, NodeList ):
	"""
	Enumerate every path from a branch node to a leaf node.

	Node IDs increase from the sink towards the leaves (the same
	convention Explore_Path relies on), so a path is a strictly
	increasing walk over the adjacency matrix that ends on a LEAF.
	"""
	paths = []

	def forward( node_id ):
		# Only walk towards the leaves; the matrix is symmetric.
		return [next_id for next_id in Get_NeighborNode( am[node_id] )
			if node_id < next_id < len( NodeList )]

	# Depth-first with an explicit stack of (path, remaining successors):
	# a recursive walk overflowed on a chain of a thousand operations.
	for root, mnemonic in enumerate( NodeList ):
		if root >= len(am) or not is_BranchNode( mnemonic ):
			continue
		stack = [([root], forward( root ))]
		while stack:
			path, pending = stack[-1]
			node_id = path[-1]
			node = Get_Mnemonic( NodeList, node_id )
			if len(node) > 3 and is_LeafNode( node ):
				paths.append( path[:] )
				stack.pop()
				continue
			if pending:
				next_id = pending.pop(0)
				stack.append((path + [next_id], forward( next_id )))
				continue
			# A terminal node that is not marked LEAF still ends a path.
			if not forward( node_id ) and len(path) > 1:
				paths.append( path[:] )
			stack.pop()

	return paths


def Gen_Path( am, NodeList, w_path, w_name, branch_leaf=False ):
	"""
	Write the load-to-load and load-to-leaf paths of one block, and, when
	asked, every branch-to-leaf path.

	The branch-to-leaf enumeration lists every path, so a data-flow graph
	that fans out and joins repeatedly (`t = t * t` thirty times over)
	has exponentially many of them and the file grows to match. Nothing
	downstream reads it, so it is off unless requested.
	"""
	explored_path = Explore_Path( am, NodeList )

	w_path_name = w_path+'/'+w_name+"_bpath_ld_ld.txt"
	with open(w_path_name, "w") as ld_ld_path:
		ld_ld_path.writelines(map(str, explored_path.Get( 'ld_ld_path' )))

	w_path_name = w_path+'/'+w_name+"_bpath_ld_leaf.txt"
	with open(w_path_name, "w") as ld_leaf_path:
		ld_leaf_path.writelines(map(str, explored_path.Get( 'ld_leaf_path' )))

	if branch_leaf:
		w_path_name = w_path+'/'+w_name+"_bpath_branch_leaf.txt"
		with open(w_path_name, "w") as branch_leaf_path:
			branch_leaf_path.writelines(map(str, Get_Branch_Leaf_Paths( am, NodeList )))
