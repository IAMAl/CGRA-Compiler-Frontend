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


# A label sits at column 0: an unquoted name or a quoted one, then ':'.
_LABEL = re.compile(r'^(?:"(?P<quoted>[^"]+)"|(?P<plain>[^\s:";]+)):')


class Type_Check:
    """
    Recognises the labels that open basic blocks.

    This used to carry an `is_<opcode>` method per instruction kind,
    matched by substring; the parser now dispatches on the parsed opcode,
    so only the label test remains.
    """
    def label_name( self, line ):
        """The name of the label on this line, or None."""
        match = _LABEL.match(line) if line[:1] not in (' ', '\t') else None
        if not match:
            return None
        return match.group('quoted') or match.group('plain')
