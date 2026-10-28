"""
Pass 1: rail rows -> atoms. Dumb on purpose: classify, validate shape, nothing else.
Atom = (op, arg, row). Operand kinds: int (LIT/ALLOC), name (GET/STORE), label.
"""
import re
from collections import namedtuple
from railcode import AtomError, parse_int, is_int

Atom = namedtuple("Atom", "op arg row")

IDENT     = re.compile(r"[A-Za-z_]\w*$")
LABEL_REF = re.compile(r":\s*([A-Za-z_]\w*)$")
COND      = re.compile(r"(==|!=|<=|>=|<|>)\s*:\s*([A-Za-z_]\w*)$")

ALU_WORDS = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD",
             "&": "AND", "|": "OR", "^": "XOR", ".": "PRINT",
             "dup": "DUP", "swap": "SWAP", "over": "OVER"}
COND_OPS  = {"==": "JEQ", "!=": "JNE", "<": "JLT", ">": "JGT", "<=": "JLE", ">=": "JGE"}


def atomize(rail):
    atoms = []
    for r in rail:
        atoms.extend(_atoms(r))
    return atoms


def _atoms(r):
    g, rest, y = r.glyph, r.rest, r.lineno
    if g == "│":
        if rest:
            raise AtomError("E_OPERAND", f"│ takes no operand: {rest!r}", y)
        return []
    if g == "░":
        if rest:
            raise AtomError("E_OPERAND", f"░ takes no operand: {rest!r}", y)
        return [Atom("HALT", None, y)]
    if g == "█":
        n = parse_int(rest.lstrip(":"), y, AtomError, "E_ALLOC")
        if n <= 0:
            raise AtomError("E_ALLOC", "stack size must be positive", y)
        return [Atom("ALLOC", n, y)]
    if g == "↳":
        m = LABEL_REF.fullmatch(rest)
        if not m:
            raise AtomError("E_LABEL", f"↳ needs ':label', got {rest!r}", y)
        return [Atom("JMP", m.group(1), y)]
    if g == "╞":
        m = COND.fullmatch(rest)
        if not m:
            raise AtomError("E_OP", f"bad ╞ form (want '<cmp> :label'): {rest!r}", y)
        return [Atom(COND_OPS[m.group(1)], m.group(2), y)]
    return _data(rest, y)          # g == "├"


def _data(rest, y):
    if not rest:
        raise AtomError("E_OP", "empty ├ row", y)
    if rest.startswith(":"):
        m = LABEL_REF.fullmatch(rest)
        if not m:
            raise AtomError("E_LABEL", f"bad label definition: {rest!r}", y)
        return [Atom("LABEL", m.group(1), y)]
    if rest[0] == "<":
        out = []
        for tok in (t.strip() for t in rest[1:].split(",")):
            if is_int(tok):
                out.append(Atom("LIT", parse_int(tok, y), y))
            elif IDENT.match(tok):
                out.append(Atom("GET", tok, y))
            else:
                raise AtomError("E_OPERAND", f"bad push operand: {tok!r}", y)
        return out
    if rest[0] == ">":
        name = rest[1:].strip()
        if not name:
            return [Atom("DROP", None, y)]
        if not IDENT.match(name):
            raise AtomError("E_OPERAND", f"bad store target: {name!r}", y)
        return [Atom("STORE", name, y)]
    if rest in ALU_WORDS:
        return [Atom(ALU_WORDS[rest], None, y)]
    raise AtomError("E_OPERAND", f"unknown ├ op or trailing operands: {rest!r}", y)
