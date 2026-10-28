"""Single source of truth for instruction stack effects (the descriptor table)."""
from collections import namedtuple

Op = namedtuple("Op", "pops pushes operand")   # operand: None | int | sym | label

OPS = {
    # data
    "LIT":   Op(0, 1, "int"),   "GET":  Op(0, 1, "sym"),  "STORE": Op(1, 0, "sym"),
    "DROP":  Op(1, 0, None),    "DUP":  Op(1, 2, None),
    "SWAP":  Op(2, 2, None),    "OVER": Op(2, 3, None),
    # ALU  ( a b -- r )
    **{n: Op(2, 1, None) for n in
       ("ADD", "SUB", "MUL", "DIV", "MOD", "AND", "OR", "XOR")},
    # output sink
    "PRINT": Op(1, 0, None),
    # control (conditional jumps consume both operands)
    "JMP":   Op(0, 0, "label"),
    **{n: Op(2, 0, "label") for n in ("JEQ", "JNE", "JLT", "JGT", "JLE", "JGE")},
    "HALT":  Op(0, 0, None),
}

COND_JUMPS = {"JEQ", "JNE", "JLT", "JGT", "JLE", "JGE"}
