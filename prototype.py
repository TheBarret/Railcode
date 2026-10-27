"""
Railcode VM prototype v0.2: spatial 2D grid stack machine.
Target: Symbiote kernel (C, freestanding). This Python prototype mirrors the
planned C implementation shapes: fixed kmalloc'd slot buffer, explicit sp,
no dictionary lookups at runtime, no regex at runtime.

Every runtime path here maps 1:1 onto the flat bytecode of the spec's
Section 4:
    GET -> < var       LIT -> < imm      ADD/SUB/MUL/DIV -> . op
    SET -> > var       JZ  -> ╞ :label   JMP -> ↳ :label   HLT -> ░

Changes vs v0.1:
  * Division truncates toward zero (C99), not Python floor.
  * All values wrap to int32 at push and in every ALU op (free in C,
    emulated here).
  * ╞ conditional limb implemented:
      - bare ╞: pops; if zero, travels the horizontal `─` limb to `╛`,
        which returns the IP to the spine column on the next row.
        NOTE: per-spec geometry this converges with the fall-through path,
        so a bare limb currently skips nothing — kept for glyph fidelity.
      - `╞ :label`: pops; if zero, jumps to the label's coordinates.
        This is the useful form (compiles to JZ).
  * ↳ :label — unconditional jump conduit (compiles to JMP).
  * Missing ░ terminator now raises a fatal VMFault (per spec).
  * Comparison ALU ops (== != < <= > >=) push 1/0 so ╞ has something to eat.
  * Multiple █ entry markers fault instead of silently last-wins.
  * `\` comment stripping kept, but done once at load time only.
"""

import re

INT32_MIN = -2**31
INT32_MAX = 2**31 - 1
COMMENT = '\\'


def wrap32(v):
    """Wrap to 32-bit signed. In C this is a no-op (int32_t)."""
    return ((v + 2**31) % 2**32) - 2**31


def trunc_div(a, b):
    """C99 truncation toward zero. In C: plain `/`."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


class VMFault(Exception):
    """Fatal VM error (illegal symbol, missing terminator, bad limb...)."""


class StackOverflow(Exception):
    pass


class StackUnderflow(Exception):
    pass


class RailInterpreter:
    def __init__(self, source_code):
        self.variables = {}
        # Mirror of a kmalloc'd slot buffer + stack pointer.
        # (In the kernel version: `slots = kmalloc(cap * sizeof(slot))`,
        #  `sp = 0`, and `kfree(slots)` on halt.)
        self.stack_capacity = None
        self.stack_slots = None
        self.sp = 0
        self.grid = []
        self.labels = {}          # ':name' -> (x, y); load-time only
        self.ip = (0, 0)
        self.entry = None
        self._parse_source(source_code)

    #  stack primitives over the fixed allocation
    def _stack_push(self, value):
        if self.sp >= self.stack_capacity:
            raise StackOverflow(f"Stack overflow: capacity {self.stack_capacity}, sp {self.sp}")
        self.stack_slots[self.sp] = wrap32(value)
        self.sp += 1

    def _stack_pop(self):
        if self.sp == 0:
            raise StackUnderflow("Stack underflow: pop from empty stack")
        self.sp -= 1
        v = self.stack_slots[self.sp]
        self.stack_slots[self.sp] = None  # clear slot (kfree hygiene)
        return v

    #  load time
    def _parse_source(self, code):
        grid_lines = []
        for line in code.splitlines():
            clean = line.split(COMMENT)[0].rstrip()
            if clean.lstrip().startswith("decl"):
                # TODO(C port): hand-rolled tokenizer, no <regex.h>.
                m = re.match(r"decl\s+(\w+),\s*(\w+),\s*(.+);", clean)
                if not m:
                    raise SyntaxError(f"Malformed decl: {clean!r}")
                name, vtype, val = m.groups()
                if vtype != "int":
                    raise SyntaxError(f"Unsupported type '{vtype}' (int only).")
                self.variables[name] = wrap32(int(val, 0))
                continue
            if clean.strip():
                grid_lines.append(clean)

        max_width = max(len(l) for l in grid_lines) if grid_lines else 0
        self.grid = [list(l.ljust(max_width)) for l in grid_lines]

        for y, row in enumerate(self.grid):
            row_text = "".join(row)

            # Entry marker detection: unconditional, every row.
            for x, ch in enumerate(row):
                if ch == '█':
                    if self.entry is not None:
                        raise SyntaxError(f"Multiple entry markers: ({self.entry}) and ({x},{y}).")
                    self.ip = (x, y)
                    self.entry = (x, y)
                    payload = "".join(row[x + 1:]).split(COMMENT)[0].strip()
                    try:
                        size = int(payload, 0)
                    except ValueError:
                        raise SyntaxError(f"Invalid stack size '{payload}' at entry marker.")
                    if size <= 0:
                        raise SyntaxError("Stack size must be positive.")
                    self.stack_capacity = size
                    self.stack_slots = [None] * size
                    self.sp = 0

            # Label definitions: only ├ rows define labels.
            gx = next((i for i, ch in enumerate(row_text)
                       if ch in ('├', '╞', '↳')), None)
            if gx is None or row_text[gx] != '├':
                continue
            for label in re.findall(r":\w+", row_text):
                self.labels.setdefault(label, (gx, y))

    def _payload(self, x, y):
        return "".join(self.grid[y][x + 1:]).split(COMMENT)[0].strip()

    #  run time (walks glyphs; C port walks flat bytecode instead)
    def run(self):
        if self.entry is None:
            raise SyntaxError("No entry marker (█) found in program.")
        if self.stack_slots is None:
            raise SyntaxError("Entry marker did not allocate a stack.")

        x, y = self.entry
        spine_x = x
        height = len(self.grid)
        width = len(self.grid[0]) if height else 0
        halted = False

        print(f"Starting execution at IP ({x},{y}) "
              f"with stack capacity {self.stack_capacity} ---")
        try:
            while 0 <= y < height and 0 <= x < width:
                sym = self.grid[y][x]

                if sym == '░':
                    halted = True
                    print(">>> Halting.")
                    break
                elif sym in ('│', '█'):
                    pass  # pure flow / declarative entry
                elif sym == '├':
                    payload = self._payload(x, y)
                    if payload and not payload.startswith(':'):
                        self._execute_instruction(payload)
                    # ':label' payload on ├ is a label definition: no-op.
                elif sym == '╞':
                    cond = self._stack_pop()
                    payload = self._payload(x, y)
                    if payload.startswith(':'):
                        # JZ: branch to label when popped value is zero.
                        if cond == 0:
                            tgt = self.labels.get(payload)
                            if tgt is None:
                                raise VMFault(f"Unknown label '{payload}'.")
                            x, y = tgt
                            continue
                    elif cond == 0:
                        # Bare limb: travel right over `─` to the `╛` cap,
                        # then return to the spine on the next row.
                        lx = x + 1
                        while lx < width and self.grid[y][lx] == '─':
                            lx += 1
                        if lx >= width or self.grid[y][lx] != '╛':
                            raise VMFault(
                                f"Limb at ({x},{y}) has no ╛ cap.")
                        x = spine_x
                elif sym == '↳':
                    # JMP: unconditional label jump.
                    payload = self._payload(x, y)
                    tgt = self.labels.get(payload)
                    if tgt is None:
                        raise VMFault(f"Unknown label '{payload}'.")
                    x, y = tgt
                    continue
                else:
                    raise VMFault(
                        f"Illegal symbol '{sym}' outside an active "
                        f"conduit at ({x},{y}).")

                y += 1
                self.ip = (x, y)

            if not halted:
                raise VMFault(
                    "Execution left the grid without a ░ terminator.")
        finally:
            self.stack_slots = None   # kfree(slots)
            self.sp = 0
            print(f"Execution finished. Final variables: {self.variables} ---")

    #  operand resolution (load-time slot index in the C port)
    def _resolve_operand(self, op_str):
        op_str = op_str.strip()
        if op_str in self.variables:
            return self.variables[op_str]
        try:
            return int(op_str, 0)
        except ValueError:
            try:
                return int(op_str, 10)  # tolerate leading zeros ("010")
            except ValueError:
                raise ValueError(
                    f"Invalid operand or unresolved variable: '{op_str}'")

    def _execute_instruction(self, payload):
        if payload.startswith("<"):
            for item in payload[1:].split(","):
                if item.strip():
                    self._stack_push(self._resolve_operand(item))

        elif payload.startswith(">"):
            var_name = payload[1:].strip()
            if var_name not in self.variables:
                raise NameError(f"Undeclared target variable: '{var_name}'")
            self.variables[var_name] = self._stack_pop()

        elif payload.startswith("."):
            op = payload[1:].strip()
            if self.sp < 2:
                raise IndexError(
                    f"ALU operation '{op}' needs 2 elements on the stack.")
            b = self._stack_pop()
            a = self._stack_pop()

            if op == '+':
                self._stack_push(a + b)
            elif op == '-':
                self._stack_push(a - b)
            elif op == '*':
                self._stack_push(a * b)
            elif op == '/':
                if b == 0:
                    raise ZeroDivisionError("ALU division by zero")
                self._stack_push(trunc_div(a, b))
            # Comparisons: push 1/0 so ╞ has a condition to consume.
            elif op == '==':
                self._stack_push(1 if a == b else 0)
            elif op == '!=':
                self._stack_push(1 if a != b else 0)
            elif op == '<':
                self._stack_push(1 if a < b else 0)
            elif op == '<=':
                self._stack_push(1 if a <= b else 0)
            elif op == '>':
                self._stack_push(1 if a > b else 0)
            elif op == '>=':
                self._stack_push(1 if a >= b else 0)
            else:
                raise ValueError(f"Unknown ALU operator: '{op}'")
        else:
            raise ValueError(f"Unrecognized instruction payload: '{payload}'")


# ---
# Tests
# ---

# 1) Spec example: x=10, y=20, result = 10 * (20 + 5) = 250
SOURCE_1 = """
decl x, int, 10;
decl y, int, 20;
decl result, int, 0;

█ 0xff        \\ Initialize stack
│             \\ NOP channel
├ :program    \\ Program entry conduit
│
├ < x, y, 5   \\ Push variables x, y, and immediate literal 5
├ . +         \\ y + 5 = 25
├ . *         \\ 10 * 25 = 250
├ > result    \\ Pop into 'result'
│
░             \\ Halt
"""

# 2) Numeric conformance: C99 truncation + int32 wrap.
#    -7 / 2 -> -3 (not floor's -4); 2147483647 + 1 -> -2147483648.
SOURCE_2 = """
decl q, int, 0;
decl w, int, 0;

█ 0x10
│
├ < -7, 2
├ . /
├ > q         \\ q = -3
├ < 2147483647, 1
├ . +
├ > w         \\ w = -2147483648
│
░
"""

# 3) Control flow: ╞ :label (JZ) + ↳ (JMP) with a comparison op.
SOURCE_3 = """
decl a, int, 4;
decl msg, int, 0;

█ 0x10
│
├ < a, 4
├ . ==         \\ cond: 1 if a == 4
╞ :neq         \\ if cond == 0 -> jump to :neq
├ < 1
├ > msg        \\ msg = 1
↳ :end
├ :neq
├ < 2
├ > msg        \\ msg = 2
│
├ :end
░
"""


def run_case(title, source, expect):
    print(f"\nRunning: {title} ")
    interp = RailInterpreter(source)
    interp.run()
    assert interp.variables == expect, \
        f"FAIL: expected {expect}, got {interp.variables}"
    print(f"PASS: {interp.variables}")


if __name__ == "__main__":
    run_case("Test 1: ALU operations", SOURCE_1, {'x': 10, 'y': 20, 'result': 250})
    run_case("Test 2: trunc div + int32 wrap", SOURCE_2, {'q': -3, 'w': -2147483648})
    run_case("Test 3: conditional limb (a == 4)", SOURCE_3, {'a': 4, 'msg': 1})
    SOURCE_3b = SOURCE_3.replace("decl a, int, 4;", "decl a, int, 9;")
    run_case("Test 3b: conditional limb (a != 4)", SOURCE_3b,{'a': 9, 'msg': 2})
    print("\nAll tests passed.")
