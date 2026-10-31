"""Railcode 0.5 -- formal opcode specification (ISA single source of truth).

This module is the ISA document. Everything downstream (bind, verify, vm)
reads the table from here.

Contract:
  * `code` is a stable u8. Assigned once, never reused.
  * Append new ops at the next free code; bump ISA_MINOR.
  * Changing an existing op's (pops, pushes, operand) or its code is a
    BREAKING change; bump ISA_MAJOR and never renumber in place.
"""
from collections import namedtuple

ISA_VERSION = "0.5.0"
ISA_MAJOR, ISA_MINOR = 0, 5

# Reference:
#  Opcode table, reserved regions are for future tiers:
#    0x00-0x0F  control (halt, no-op-ish)
#    0x10-0x2F  literals / symbols / stack shuffles
#    0x30-0x3F  memory (currently folded into GET/STORE above)
#    0x40-0x5F  ALU
#    0x60-0x7F  I/O
#    0x80-0x9F  conditional jumps
#    0xA0-0xBF  unconditional jumps
#    0xC0-0xFF  reserved


#  Op(op_code, pops, pushes, operand, sem)
#  operand: "lit" | "sym" | "label" | None
Op = namedtuple("Op", "code pops pushes operand sem")

OPS = {
    "HALT":  Op(0x00, 0, 0, None,   "--"),
    "LIT":   Op(0x10, 0, 1, "lit",  "-- n"),
    "GET":   Op(0x11, 0, 1, "sym",  "-- v"),
    "STORE": Op(0x12, 1, 0, "sym",  "v --"),
    "DROP":  Op(0x13, 1, 0, None,   "v --"),
    "DUP":   Op(0x14, 1, 2, None,   "a -- a a"),
    "SWAP":  Op(0x15, 2, 2, None,   "a b -- b a"),
    "OVER":  Op(0x16, 2, 3, None,   "a b -- a b a"),
    "ADD":   Op(0x40, 2, 1, None,   "a b -- a+b (wraps)"),
    "SUB":   Op(0x41, 2, 1, None,   "a b -- a-b (wraps)"),
    "MUL":   Op(0x42, 2, 1, None,   "a b -- a*b (wraps)"),
    "DIV":   Op(0x43, 2, 1, None,   "a b -- a/b (trunc; b=0 traps; MIN/-1 wraps)"),
    "MOD":   Op(0x44, 2, 1, None,   "a b -- a-b*(a/b trunc)"),
    "AND":   Op(0x45, 2, 1, None,   "a b -- a&b"),
    "OR":    Op(0x46, 2, 1, None,   "a b -- a|b"),
    "XOR":   Op(0x47, 2, 1, None,   "a b -- a^b"),
    "PRINT": Op(0x60, 1, 0, None,   "v -- (emits v)"),
    "JEQ":   Op(0x80, 2, 0, "label","a b -- ; fwd if a==b"),
    "JNE":   Op(0x81, 2, 0, "label","a b -- ; fwd if a!=b"),
    "JLT":   Op(0x82, 2, 0, "label","a b -- ; fwd if a<b"),
    "JGT":   Op(0x83, 2, 0, "label","a b -- ; fwd if a>b"),
    "JLE":   Op(0x84, 2, 0, "label","a b -- ; fwd if a<=b"),
    "JGE":   Op(0x85, 2, 0, "label","a b -- ; fwd if a>=b"),
    "JMP":   Op(0xA0, 0, 0, "label","-- ; strictly backward"),
}

COND_JUMPS = {"JEQ", "JNE", "JLT", "JGT", "JLE", "JGE"}


# invariants
def _check_table():
    codes = [op.code for op in OPS.values()]
    if len(set(codes)) != len(codes):
        raise AssertionError("duplicate opcode in OPS")
    if max(codes) > 0xFF:
        raise AssertionError("opcode exceeds u8")
    for name, op in OPS.items():
        if op.operand not in (None, "lit", "sym", "label"):
            raise AssertionError(f"{name}: bad operand kind {op.operand!r}")
        if op.pops < 0 or op.pushes < 0:
            raise AssertionError(f"{name}: negative stack effect")
    for name in COND_JUMPS:
        if name not in OPS:
            raise AssertionError(f"{name} in COND_JUMPS but not OPS")
_check_table()
