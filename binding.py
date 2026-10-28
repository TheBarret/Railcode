"""Pass 2: bind labels to indices, resolve operand tags, allocate slots."""
import re
from railcode import tokenize_header
from atom import AtomError

# policy
ALLOW_UNDECLARED_STORE = True     # matches interpreter's silent create
PUSH_IS_SINGLE_ATOM    = True     # one row = one step; keeps step parity

def bind(src, atoms):
    slots, consts = _alloc_slots(src, atoms)
    labels = _label_offsets(atoms)
    code   = []
    for a in atoms:
        if a[0] == "LABEL":
            continue
        code.append(_resolve(a, slots))
    return code, labels, slots, consts


def _alloc_slots(src, atoms):
    """Header decls first, then any store target not yet declared."""
    decls = tokenize_header(src)
    slots, consts = {}, []
    for name, val in decls.items():
        slots[name] = len(slots); consts.append(val)
    if ALLOW_UNDECLARED_STORE:
        for a in atoms:
            if a[0] == "STORE" and a[1] not in slots:
                slots[a[1]] = len(slots); consts.append(None)
    else:
        for a in atoms:
            if a[0] == "STORE" and a[1] not in slots:
                raise AtomError(f"store to undeclared symbol: {a[1]!r}")
    return slots, consts


def _label_offsets(atoms):
    labels, pc = {}, 0
    for a in atoms:
        if a[0] == "LABEL":
            if a[1] in labels:
                raise AtomError(f"duplicate label: {a[1]!r}")
            labels[a[1]] = pc
        else:
            pc += 1
    return labels


def _resolve(a, slots):
    op = a[0]
    if op == "PUSH":
        if PUSH_IS_SINGLE_ATOM:
            return ("PUSH", [_tok(t, slots) for t in a[1]])
        else:
            raise AtomError("PUSH_IS_SINGLE_ATOM=False needs a splitter pass")
    if op == "STORE":
        return ("STORE", slots[a[1]])
    if op in ("JMP", "JEQ", "JNE", "JLT", "JGT"):
        return a                                     # label name; VM binds via labels map
    return a


def _tok(tok, slots):
    if re.fullmatch(r"-?\d+", tok):                return ("int", int(tok))
    if re.fullmatch(r"0[xX][0-9a-fA-F]+", tok):    return ("int", int(tok, 16))
    if tok in slots:                               return ("slot", slots[tok])
    return ("str", tok)
