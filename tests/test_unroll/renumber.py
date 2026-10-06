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
Renumber the unnamed values of every function the way LLVM requires.

LLVM's reader insists that unnamed registers and unnamed basic blocks
share one counter and appear in order: the entry block takes 0 when it
has no label, then every unnamed parameter, block and instruction takes
the next number in textual order. A generator that hands out numbers
before it emits, or an edit that removes an instruction, leaves gaps
that `llvm-as` rejects, so the front end would never see such a file
from clang. This pass restores the numbering after the fact.

    python renumber.py file.ll [...]     rewrites the files in place
"""
import re
import sys

_FUNCTION = re.compile(r'(?P<head>^define\b[^\n]*\{[ \t]*\n)(?P<body>.*?)(?P<tail>^\})', re.M | re.S)
_DEF = re.compile(r'^\s*%(\d+)\s*=')
_LABEL = re.compile(r'^(\d+):')
_NAMED_LABEL = re.compile(r'^(?:"[^"]+"|[^\s:";]+):')


def renumber(text: str) -> str:
    """The text with every function's unnamed values renumbered (and LF line ends)."""
    text = text.replace('\r\n', '\n')
    defines = len(re.findall(r'^define\b', text, re.M))
    covered = len(_FUNCTION.findall(text))
    if covered != defines:
        raise ValueError(f"{defines - covered} function(s) do not open with '{{' at the end of "
                         f"their define line; that layout is not handled")
    return _FUNCTION.sub(lambda m: _renumber_function(m.group('head'), m.group('body')) + m.group('tail'), text)


def _split_comment(line: str):
    """(code, comment) of one line; a ';' inside a string is not a comment."""
    quoted = False
    for index, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == ';' and not quoted:
            return line[:index], line[index:]
    return line, ''


def _rename_code(code: str, rename) -> str:
    """Rename %N outside string literals (inline asm, metadata strings)."""
    pieces = code.split('"')
    for index in range(0, len(pieces), 2):
        pieces[index] = re.sub(r'%(\d+)\b', rename, pieces[index])
    return '"'.join(pieces)


def _renumber_function(head: str, body: str) -> str:
    mapping = {}
    counter = 0

    def take(old: str) -> None:
        nonlocal counter
        if old in mapping:
            raise ValueError(f"%{old} is defined twice")
        mapping[old] = str(counter)
        counter += 1

    params = head[head.index('('):]
    for old in re.findall(r'%(\d+)\b', params):
        take(old)

    lines = body.split('\n')
    first = next((line for line in lines if line.strip() and not line.lstrip().startswith(';')), '')
    if not _NAMED_LABEL.match(first):
        # The unnamed entry block is a value too, and `; preds` comments
        # refer to it by the number it had.
        take(str(counter))
    for line in lines:
        label = _LABEL.match(line)
        if label:
            take(label.group(1))
            continue
        definition = _DEF.match(_split_comment(line)[0])
        if definition:
            take(definition.group(1))

    def rename(match) -> str:
        old = match.group(1)
        if old not in mapping:
            raise ValueError(f"%{old} is used but never defined")
        return '%' + mapping[old]

    head = _rename_code(head, rename)
    renamed = []
    for line in lines:
        label = _LABEL.match(line)
        if label:
            line = mapping[label.group(1)] + ':' + line[label.end():]
        # Comments (`; preds = %9`) may name values that no longer
        # exist and are left alone; strings are not code either.
        code, comment = _split_comment(line)
        renamed.append(_rename_code(code, rename) + comment)
    return head + '\n'.join(renamed)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    for path in sys.argv[1:]:
        with open(path) as f:
            text = f.read()
        renumbered = renumber(text)
        if renumbered != text:
            with open(path, 'w') as f:
                f.write(renumbered)
            print(f"renumbered {path}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
