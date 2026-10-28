"""Pass 1: grid -> atom list. One atom per executable rail row."""
import re
from railcode import (RAIL_CHARS, EXEC_CHARS, first_glyph, tokenize_header, build_grid)

class AtomError(Exception):
    pass

def atomize(grid):
    atoms = []
    for y, row in enumerate(grid):
        x, g = first_glyph(row)
        if x is None or g == "│":
            continue
        rest = row[x + 1:].strip()
        atoms.append(_atom(g, rest))
    return atoms


def _atom(g, rest):
    if g == "░":
        return ("HALT",)
    if g == "█":
        tok = rest.lstrip(":").strip()
        try:
            return ("ALLOC", int(tok, 16))
        except ValueError:
            raise AtomError(f"bad █ operand: {tok!r}")
    if g == "↳":
        return ("JMP", rest.lstrip(":").strip())

    op, arg = _split(rest)

    if g == "├":
        if op.startswith(":"):
            return ("LABEL", op[1:].strip())
        if op == "<":
            return ("PUSH", [t.strip() for t in arg.split(",")])
        if op == ">":
            return ("STORE", arg.strip())
        if op in ("+", "-", "*"):
            return ({"+": "ADD", "-": "SUB", "*": "MUL"}[op],)
        if op == ".":
            return ("PRINT",)
        raise AtomError(f"bad ├ op: {op!r}")

    if g == "╞":
        if op not in ("==", "!=", "<", ">"):
            raise AtomError(f"bad ╞ op: {op!r}")
        return ({"==": "JEQ", "!=": "JNE",
                 "<": "JLT", ">": "JGT"}[op],
                arg.lstrip(":").strip())

    raise AtomError(f"unknown glyph: {g!r}")


def _split(rest):
    """'<' 'x, 10'  -> ('<', 'x, 10');  ':' 'loop' -> (':loop', '')."""
    rest = rest.strip()
    if not rest:
        return "", ""
    if rest[0] in "<>+-*.":
        return rest[0], rest[1:].strip()
    if rest[0] == ":":
        return rest, ""                       # label marker
    parts = rest.split(None, 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")
