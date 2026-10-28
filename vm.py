"""
Pass 4: the machine. Sees only Program (ints, slots, pcs). No names, no glyphs.
Re-runnable: all state is built inside run().
"""
from railcode import VMError, RailError, wrap32
from spec import OPS


def _tdiv(a, b):                       # truncating (C-style) division
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q

BIN = {
    "ADD": lambda a, b: a + b,   "SUB": lambda a, b: a - b,   "MUL": lambda a, b: a * b,
    "DIV": _tdiv,                "MOD": lambda a, b: a - b * _tdiv(a, b),
    "AND": lambda a, b: a & b,   "OR":  lambda a, b: a | b,   "XOR": lambda a, b: a ^ b,
}
CMP = {
    "JEQ": lambda a, b: a == b,  "JNE": lambda a, b: a != b,
    "JLT": lambda a, b: a < b,   "JGT": lambda a, b: a > b,
    "JLE": lambda a, b: a <= b,  "JGE": lambda a, b: a >= b,
}


class VM:
    def __init__(self, program, out=print):
        self.p, self.out = program, out

    def run(self, fuel=256, trace=None):
        """fuel = max TAKEN BACKWARD jumps (loop iterations). Returns a result dict."""
        p, code = self.p, self.p.code
        mem, stack, sp = list(p.init), [0] * p.capacity, 0
        pc = steps = used = 0
        ins = None
        try:
            while True:
                if not 0 <= pc < len(code):
                    raise VMError("E_FALL_OFF", "pc left the program")
                ins = code[pc]
                op, arg = ins.op, ins.arg
                spec = OPS[op]
                steps += 1
                if trace:
                    trace(pc, ins, stack[:sp])
                if sp < spec.pops:
                    raise VMError("E_UNDERFLOW", f"{op} needs {spec.pops}", ins.row)
                if sp - spec.pops + spec.pushes > p.capacity:
                    raise VMError("E_OVERFLOW", f"{op} exceeds capacity {p.capacity}", ins.row)

                args = stack[sp - spec.pops:sp]
                sp -= spec.pops
                res = ()
                if   op == "HALT":  break
                elif op == "LIT":   res = (arg,)
                elif op == "GET":   res = (mem[arg],)
                elif op == "STORE": mem[arg] = args[0]
                elif op == "DROP":  pass
                elif op == "DUP":   res = (args[0], args[0])
                elif op == "SWAP":  res = (args[1], args[0])
                elif op == "OVER":  res = (args[0], args[1], args[0])
                elif op == "PRINT": self.out(args[0])
                elif op in BIN:
                    if op in ("DIV", "MOD") and args[1] == 0:
                        raise VMError("E_DIV0", "division by zero", ins.row)
                    res = (wrap32(BIN[op](*args)),)
                elif op == "JMP" or (op in CMP and CMP[op](*args)):
                    if arg <= pc:                       # back-edge: burn fuel
                        used += 1
                        if used > fuel:
                            raise VMError("E_FUEL", f"fuel exhausted ({fuel} back-edges)", ins.row)
                    pc = arg
                    continue
                elif op not in CMP:
                    raise VMError("E_OPCODE", f"bad opcode {op!r}", ins.row)

                for v in res:
                    stack[sp] = v
                    sp += 1
                pc += 1
        except RailError:
            raise
        except Exception as e:                           # never leak a Python traceback
            raise VMError("E_INTERNAL", repr(e), ins.row if ins else None)

        return {"halted": True, "steps": steps, "fuel_used": used,
                "stack": stack[:sp],
                "symbols": {n: mem[i] for n, i in p.slots.items()}}
