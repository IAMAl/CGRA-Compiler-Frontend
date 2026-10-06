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
The names the generated programs give the source's memory objects.

One definition, shared by the front end and the verifier: a divergence
between the two would be a false mismatch, not a caught bug.

    '%5'      -> 's5'         a scalar local, an object of its own
    '@n'      -> 'n'          a scalar global
    '%t'      -> 'lt'         a local array (an alloca of array type)
    '%a'      -> 'ptr_a'      an array passed in by pointer
    '%n'      -> 'arg_n'      a scalar parameter, read from @arg_n
"""
import re


def _sanitize(reg: str) -> str:
	return re.sub(r'[^0-9A-Za-z_]', '_', reg.lstrip('%'))


def object_name(slot: str) -> str:
	"""The memory object a scalar slot becomes."""
	if slot.startswith('@'):
		return slot[1:]
	return 's' + _sanitize(slot)


def local_array_name(slot: str) -> str:
	return 'l' + _sanitize(slot)


def pointer_object_name(param: str) -> str:
	return 'ptr_' + _sanitize(param)


def scalar_param_name(reg: str) -> str:
	return 'arg_' + _sanitize(reg)
