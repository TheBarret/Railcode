"""
    Railcode 0.5 -- passes 1-3: rows -> atoms -> bound program -> verified

    Three stages, one module, one error type. Each stage is independent in intent:

      atomize : classify rail rows and validate row shape (no name resolution)
      bind    : resolve names -> slots, labels -> pcs, lift ALLOC into the header
      verify  : single forward pass; proves stack safety, merge agreement,
                no dead code, and no fall-off without HALT

    Atom and Instr share a shape; bind rewrites .arg in place of names/pcs.
"""

import re
from collections import namedtuple
from errors import RailError
from railcode import (is_int, parse_int, split_source, tokenize_header, build_rail)

from opcodes import OPS, COND_JUMPS

Atom    = namedtuple("Atom", "op arg row")      # arg: int | name | label | None
Program = namedtuple("Program", "code slots init capacity labels")

MAX_CAPACITY = 1 << 20        # 1 Mi cells; hard bound for █

#  pass 1: atomize

IDENT     = re.compile(r"[A-Za-z_]\w*$")
LABEL_REF = re.compile(r":\s*([A-Za-z_]\w*)$")
COND      = re.compile(r"(==|!=|<=|>=|<|>)\s*:\s*([A-Za-z_]\w*)$")

ALU_WORDS = {"+": "ADD",
             "-": "SUB",
             "*": "MUL",
             "/": "DIV",
             "%": "MOD",
             "&": "AND",
             "|": "OR",
             "^": "XOR",
             ".": "PRINT",
             "dup": "DUP",
             "swap": "SWAP",
             "over": "OVER"
            }
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
            raise RailError("E_OPERAND", f"│ takes no operand: {rest!r}", y)
        return []
    if g == "░":
        if rest:
            raise RailError("E_OPERAND", f"░ takes no operand: {rest!r}", y)
        return [Atom("HALT", None, y)]
    if g == "█":
        if not rest.startswith(":"):
            raise RailError("E_ALLOC", f"█ wants ':n', got {rest!r}", y)
        n = parse_int(rest[1:], y, "E_ALLOC")   # exactly one sigil, no lstrip
        if n <= 0:
            raise RailError("E_ALLOC", "stack size must be positive", y)
        return [Atom("ALLOC", n, y)]
    if g == "↳":
        m = LABEL_REF.fullmatch(rest)
        if not m:
            raise RailError("E_LABEL", f"↳ needs ':label', got {rest!r}", y)
        return [Atom("JMP", m.group(1), y)]
    if g == "╞":
        m = COND.fullmatch(rest)
        if not m:
            raise RailError("E_OP", f"bad ╞ form (want '<cmp> :label'): {rest!r}", y)
        return [Atom(COND_OPS[m.group(1)], m.group(2), y)]
    return _data(rest, y)          # g == "├"


def _data(rest, y):
    if not rest:
        raise RailError("E_OP", "empty ├ row", y)
    if rest.startswith(":"):
        m = LABEL_REF.fullmatch(rest)
        if not m:
            raise RailError("E_LABEL", f"bad label definition: {rest!r}", y)
        return [Atom("LABEL", m.group(1), y)]
    if rest[0] == "<":
        out = []
        for tok in (t.strip() for t in rest[1:].split(",")):
            if is_int(tok):
                out.append(Atom("LIT", parse_int(tok, y), y))
            elif IDENT.match(tok):
                out.append(Atom("GET", tok, y))
            else:
                raise RailError("E_OPERAND", f"bad push operand: {tok!r}", y)
        return out
    if rest[0] == ">":
        name = rest[1:].strip()
        if not name:
            return [Atom("DROP", None, y)]
        if not IDENT.match(name):
            raise RailError("E_OPERAND", f"bad store target: {name!r}", y)
        return [Atom("STORE", name, y)]
    if rest in ALU_WORDS:
        return [Atom(ALU_WORDS[rest], None, y)]
    raise RailError("E_OPERAND", f"unknown ├ op or trailing operands: {rest!r}", y)


#  pass 2: bind

def bind(header, atoms, rail=None):
    slots = {n: i for i, n in enumerate(header)}
    init  = tuple(header.values())

    # (H1) ALLOC must be the first SYNTACTIC rail row, not just the first atom.
    if rail is not None and (not rail or rail[0].glyph != "█"):
        raise RailError("E_ALLOC", "█ must be the first rail row",
                        rail[0].lineno if rail else None)

    allocs = [a for a in atoms if a.op == "ALLOC"]
    if not allocs:
        raise RailError("E_ALLOC", "missing █ stack allocation")
    if len(allocs) > 1:
        raise RailError("E_ALLOC", "more than one █", allocs[1].row)
    if atoms[0].op != "ALLOC":
        raise RailError("E_ALLOC", "█ must be the first rail row", allocs[0].row)
    capacity = allocs[0].arg

    # (H2) capacity is a bounded resource, not a free int32.
    if capacity > MAX_CAPACITY:
        raise RailError("E_ALLOC",
                        f"█ capacity {capacity} exceeds {MAX_CAPACITY}",
                        allocs[0].row)

    body = [a for a in atoms if a.op != "ALLOC"]
    labels, pc = {}, 0
    for a in body:
        if a.op == "LABEL":
            if a.arg in labels:
                raise RailError("E_LABEL_DUP", f"duplicate label {a.arg!r}", a.row)
            labels[a.arg] = pc
        else:
            pc += 1
    for name, target in labels.items():
        if target == pc:
            raise RailError("E_LABEL_END", f"label {name!r} has no instruction after it")

    code = []
    for a in (x for x in body if x.op != "LABEL"):
        here = len(code)
        arg  = a.arg
        kind = OPS[a.op].operand

        # (H3) operand-shape contract: None operands must carry None args.
        if kind is None and a.arg is not None:
            raise RailError("E_SHAPE", f"{a.op} takes no operand", a.row)

        if kind == "sym":
            if arg not in slots:
                raise RailError("E_SYMBOL", f"undeclared symbol {arg!r}", a.row)
            arg = slots[arg]
        elif kind == "label":
            if arg not in labels:
                raise RailError("E_LABEL", f"unknown label {arg!r}", a.row)
            arg = labels[arg]
            if a.op in COND_JUMPS and arg <= here:
                raise RailError("E_DIRECTION", "conditional jumps must go forward", a.row)
            if a.op == "JMP" and arg >= here:
                raise RailError("E_DIRECTION",
                                "unconditional jumps must go strictly backward", a.row)
        code.append(Atom(a.op, arg, a.row))
    return Program(tuple(code), slots, init, capacity, labels)


#  pass 3: verify

def verify(p):
    """One forward pass; returns peak static stack depth (raises on fault)."""
    code, cap = p.code, p.capacity
    seen, pending = {}, {}          # pc -> depth (fall/back) / (forward jump)
    cur, peak = 0, 0

    for pc, ins in enumerate(code):
        if pc in pending:
            if cur is None:
                cur = pending[pc]
            elif cur != pending[pc]:
                raise RailError("E_DEPTH",
                                f"stack depth {cur} vs {pending[pc]} at merge", ins.row)
        if cur is None:
            raise RailError("E_DEAD", "unreachable instruction", ins.row)
        seen[pc] = cur

        spec = OPS[ins.op]
        if cur < spec.pops:
            raise RailError("E_UNDERFLOW",
                            f"{ins.op} needs {spec.pops}, stack has {cur}", ins.row)
        cur = cur - spec.pops + spec.pushes
        if cur > cap:
            raise RailError("E_OVERFLOW",
                            f"depth {cur} exceeds █ capacity {cap}", ins.row)
        peak = max(peak, cur)

        if ins.op in COND_JUMPS:
            if pending.setdefault(ins.arg, cur) != cur:
                raise RailError("E_DEPTH", "jump arrives with a different depth", ins.row)
        elif ins.op == "JMP":
            if seen[ins.arg] != cur:
                raise RailError("E_DEPTH",
                                f"stack depth {cur} vs {seen[ins.arg]} at back-edge", ins.row)
            cur = None
        elif ins.op == "HALT":
            cur = None

    if cur is not None:
        raise RailError("E_FALL_OFF", "program can fall off the end without ░",
                        code[-1].row if code else None)
    return peak


#  build block

def build_program(src):
    header_rows, rail_rows = split_source(src)
    header = tokenize_header(header_rows)
    rail   = build_rail(rail_rows)
    atoms  = atomize(rail)
    program = bind(header, atoms, rail=rail)
    peak = verify(program)
    return atoms, program, peak
