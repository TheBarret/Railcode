"""
Pass 2: bind. Names -> slot indices, labels -> pcs, ALLOC lifted into the header.
After this pass no instruction carries a name.
"""
from collections import namedtuple
from railcode import BindError
from spec import OPS, COND_JUMPS

Instr   = namedtuple("Instr", "op arg row")          # arg: int | slot | pc | None
Program = namedtuple("Program", "code slots init capacity labels")


def bind(header, atoms):
    slots = {n: i for i, n in enumerate(header)}
    init  = tuple(header.values())

    allocs = [a for a in atoms if a.op == "ALLOC"]
    if not allocs:
        raise BindError("E_ALLOC", "missing █ stack allocation")
    if len(allocs) > 1:
        raise BindError("E_ALLOC", "more than one █", allocs[1].row)
    if atoms[0].op != "ALLOC":
        raise BindError("E_ALLOC", "█ must be the first rail row", allocs[0].row)
    capacity = allocs[0].arg

    body = [a for a in atoms if a.op != "ALLOC"]
    labels, pc = {}, 0
    for a in body:
        if a.op == "LABEL":
            if a.arg in labels:
                raise BindError("E_LABEL_DUP", f"duplicate label {a.arg!r}", a.row)
            labels[a.arg] = pc
        else:
            pc += 1
    for name, target in labels.items():
        if target == pc:
            raise BindError("E_LABEL_END", f"label {name!r} has no instruction after it")

    code = []
    for a in (x for x in body if x.op != "LABEL"):
        here = len(code)
        arg = a.arg
        kind = OPS[a.op].operand
        if kind == "sym":
            if arg not in slots:
                raise BindError("E_SYMBOL", f"undeclared symbol {arg!r}", a.row)
            arg = slots[arg]
        elif kind == "label":
            if arg not in labels:
                raise BindError("E_LABEL", f"unknown label {arg!r}", a.row)
            arg = labels[arg]
            if a.op in COND_JUMPS and arg <= here:
                raise BindError("E_DIRECTION", "conditional jumps must go forward", a.row)
            if a.op == "JMP" and arg > here:
                raise BindError("E_DIRECTION", "unconditional jumps must go backward", a.row)
        code.append(Instr(a.op, arg, a.row))
    return Program(tuple(code), slots, init, capacity, labels)
