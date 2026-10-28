from atom import AtomError

class VMError(Exception):
    pass

class VM:
    def __init__(self, code, labels, slots, consts):
        self.code   = code
        self.labels = labels
        self.slots  = slots
        self.locals = list(consts)
        self.stack  = []
        self.capacity = 0
        self.steps  = 0

    def run(self, max_steps=256):
        pc = 0
        while pc < len(self.code):
            if self.steps > max_steps:
                raise VMError("step limit exceeded (runaway rail)")
            a = self.code[pc]; op = a[0]

            if   op == "HALT":  return self._result(True)
            elif op == "ALLOC": self.capacity = a[1]; self.stack = []
            elif op == "PUSH":
                for tag, v in a[1]:
                    self.stack.append(self.locals[v] if tag == "slot" else v)
            elif op == "STORE": self.locals[a[1]] = self._pop()
            elif op == "ADD":   b = self._pop(); a2 = self._pop(); self.stack.append(a2 + b)
            elif op == "SUB":   b = self._pop(); a2 = self._pop(); self.stack.append(a2 - b)
            elif op == "MUL":   b = self._pop(); a2 = self._pop(); self.stack.append(a2 * b)
            elif op == "PRINT": print(self._pop())
            elif op == "JMP":
                self.steps += 1; pc = self.labels[a[1]]; continue
            elif op in ("JEQ", "JNE", "JLT", "JGT"):
                b = self._pop(); a2 = self._pop()
                ok = {"JEQ": a2 == b, "JNE": a2 != b,
                      "JLT": a2 <  b, "JGT": a2 >  b}[op]
                if ok:
                    self.steps += 1; pc = self.labels[a[1]]; continue
            else:
                raise VMError(f"bad opcode: {op!r}")

            self.steps += 1
            pc += 1
        return self._result(False)

    def _pop(self):
        if not self.stack:
            raise VMError("pop on empty stack")
        return self.stack.pop()

    def _result(self, halted):
        return {"halted": halted, "steps": self.steps,
                "capacity": self.capacity,
                "symbols": {n: self.locals[i] for n, i in self.slots.items()}}
