"""
Railcode VM prototype v0.3, spatial 2D grid stack machine.

Runtime paths:

    Glyph             Bytecode

    < var            GET  slot          0x01 <slot:1>
    < imm            LIT  imm32         0x02 <imm:4, signed LE>
    (bare ╞)         POP                0x03
    . +              ADD                0x10
    . -              SUB                0x11
    . *              MUL                0x12
    . /              DIV                0x13   (C99 trunc, /0 faults)
    . == . !=        EQ 0x14, NE 0x15   (push 1/0)
    . < . <=         LT 0x16, LE 0x17
    . > . >=         GT 0x18, GE 0x19
    > var            SET  slot          0x20 <slot:1>
    ↳ :label         JMP  addr          0x30 <addr:4, LE>
    ╞ :label         JZ   addr          0x31 <addr:4, LE>  (pop; jump if 0)
    ░                HLT                0xFF
"""

import re

INT32_MIN = -2**31
INT32_MAX = 2**31 - 1
COMMENT = '\\'
DEFAULT_MAX_STEPS = 1_000_000

#  bytecode opcodes (Section 4)
OP_GET, OP_LIT, OP_POP = 0x01, 0x02, 0x03
OP_ADD, OP_SUB, OP_MUL, OP_DIV = 0x10, 0x11, 0x12, 0x13
OP_EQ, OP_NE, OP_LT, OP_LE, OP_GT, OP_GE = 0x14, 0x15, 0x16, 0x17, 0x18, 0x19
OP_SET = 0x20
OP_JMP, OP_JZ = 0x30, 0x31
OP_HLT = 0xFF

ALU_OPCODES = {'+': OP_ADD, '-': OP_SUB, '*': OP_MUL, '/': OP_DIV,
               '==': OP_EQ, '!=': OP_NE, '<': OP_LT, '<=': OP_LE,
               '>': OP_GT, '>=': OP_GE}


def wrap32(v):
    """Wrap to 32-bit signed. In C this is a no-op (int32_t)."""
    return ((v + 2**31) % 2**32) - 2**31


def trunc_div(a, b):
    """C99 truncation toward zero. In C: plain `/`."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


class VMFault(Exception):
    """Fatal VM error (illegal symbol/opcode, missing terminator, step limit)."""


class StackOverflow(Exception):
    pass


class StackUnderflow(Exception):
    pass


class RailInterpreter:
    """Grid-walking interpreter + loader/compiler (the testbench side)."""

    def __init__(self, source_code):
        self.variables = {}         # name -> initial value (slot order = decl order)
        # Mirror of a kmalloc'd slot buffer + stack pointer.
        # (In the kernel version: `slots = kmalloc(cap * sizeof(slot))`,
        #  `sp = 0`, and `kfree(slots)` on halt.)
        self.stack_capacity = None
        self.stack_slots = None
        self.sp = 0
        self.grid = []
        self.labels = {}           # ':name' -> (x, y); load-time only
        self.ip = (0, 0)
        self.entry = None
        self._parse_source(source_code)

    #  stack primitives over the fixed allocation
    def _stack_push(self, value):
        if self.sp >= self.stack_capacity:
            raise StackOverflow(
                f"Stack overflow: capacity {self.stack_capacity}, sp {self.sp}")
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
                if name in self.variables:
                    raise SyntaxError(f"Duplicate declaration '{name}'")
                if len(self.variables) >= 256:
                    raise SyntaxError(
                        "Too many declarations (max=256)")
                self.variables[name] = wrap32(int(val, 0))
                continue
            if clean.strip():
                grid_lines.append(clean)

        max_width = max(len(l) for l in grid_lines) if grid_lines else 0
        self.grid = [list(l.ljust(max_width)) for l in grid_lines]

        # Pass 1: entry markers + label definitions.
        for y, row in enumerate(self.grid):
            row_text = "".join(row)

            for x, ch in enumerate(row):
                if ch == '█':
                    if self.entry is not None:
                        raise SyntaxError(
                            f"Multiple entry markers: ({self.entry}) "
                            f"and ({x},{y}).")
                    self.ip = (x, y)
                    self.entry = (x, y)
                    payload = "".join(row[x + 1:]).split(COMMENT)[0].strip()
                    try:
                        size = int(payload, 0)
                    except ValueError:
                        raise SyntaxError(
                            f"Invalid stack size '{payload}' at entry marker.")
                    if size <= 0:
                        raise SyntaxError("Stack size must be positive.")
                    self.stack_capacity = size
                    self.stack_slots = [None] * size   # kmalloc(size * slot)
                    self.sp = 0

            # Only ├ rows DEFINE labels; ╞/↳ rows merely REFERENCE them.
            # Registering a ╞/↳ row would make jumps land on the ╞/↳
            # glyph itself (popping again / re-jumping).
            gx = next((i for i, ch in enumerate(row_text)
                       if ch in ('├', '╞', '↳')), None)
            if gx is None or row_text[gx] != '├':
                continue
            for label in re.findall(r":\w+", row_text):
                if label in self.labels:
                    raise SyntaxError(f"Duplicate label definition '{label}'.")
                self.labels[label] = (gx, y)

        # Pass 2: validate jump references, bad programs die in the
        # loader, never in the VM.
        for y, row in enumerate(self.grid):
            row_text = "".join(row)
            for m in re.finditer(r"[╞↳]\s*(:\w+)", row_text):
                if m.group(1) not in self.labels:
                    raise SyntaxError(
                        f"Undefined label reference '{m.group(1)}' "
                        f"at row {y}.")

    def _payload(self, x, y):
        return "".join(self.grid[y][x + 1:]).split(COMMENT)[0].strip()

    #  run time (walks glyphs; the C kernel walks flat bytecode)
    def run(self, max_steps=DEFAULT_MAX_STEPS):
        if self.entry is None:
            raise SyntaxError("No entry marker (█) found in program.")
        if self.stack_slots is None:
            raise SyntaxError("Entry marker did not allocate a stack.")

        x, y = self.entry
        spine_x = x
        height = len(self.grid)
        width = len(self.grid[0]) if height else 0
        halted = False
        steps = 0

        print(f"Starting execution at IP ({x},{y}) "
              f"with stack capacity {self.stack_capacity} ---")
        try:
            while 0 <= y < height and 0 <= x < width:
                self.ip = (x, y)
                steps += 1
                if steps > max_steps:
                    raise VMFault(
                        f"Step limit exceeded ({max_steps}), "
                        f"runaway program?")

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
                    payload = self._payload(x, y)
                    if not payload.startswith(':'):
                        raise SyntaxError(
                            f"Bare ╞ at ({x},{y}) has no :label operand "
                            f"(bare conditional limbs are unsupported)")
                    if self._stack_pop() == 0:
                        x, y = self.labels[payload]
                        continue
                elif sym == '↳':
                    # JMP: unconditional label jump (backwards = loop).
                    x, y = self.labels[self._payload(x, y)]
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

    #  compile: grid -> flat bytecode (the loader's real job)
    def compile(self):
        """One static walk down the spine emits the opcode stream.
        Jump operands are patched in a second pass. Labels emit nothing;
        a label's address is the offset of the next emitted op."""
        if self.entry is None:
            raise SyntaxError("No entry marker (█) found in program.")

        x, y = self.entry
        height = len(self.grid)
        width = len(self.grid[0]) if height else 0
        code = bytearray()
        slot_index = {name: i for i, name in enumerate(self.variables)}
        code_labels = {}          # ':name' -> bytecode offset
        patches = []              # (operand_offset, label)

        def emit(*ops):
            code.extend(ops)

        def emit_imm(v):
            code.extend(wrap32(v).to_bytes(4, 'little', signed=True))

        halted = False
        while 0 <= y < height and 0 <= x < width:
            sym = self.grid[y][x]

            if sym == '░':
                emit(OP_HLT)
                halted = True
                break
            elif sym in ('│', '█'):
                pass
            elif sym == '├':
                payload = self._payload(x, y)
                if payload.startswith(':'):
                    if payload in code_labels:
                        raise SyntaxError(
                            f"Duplicate label '{payload}' during compile.")
                    code_labels[payload] = len(code)
                else:
                    self._compile_instruction(
                        payload, emit, emit_imm, slot_index)
            elif sym == '╞':
                payload = self._payload(x, y)
                if not payload.startswith(':'):
                    raise SyntaxError(
                        f"Bare ╞ at ({x},{y}) has no :label operand "
                        f"(bare conditional limbs are unsupported)")
                emit(OP_JZ)
                patches.append((len(code), payload))
                code.extend(b'\x00\x00\x00\x00')
            elif sym == '↳':
                emit(OP_JMP)
                patches.append((len(code), self._payload(x, y)))
                code.extend(b'\x00\x00\x00\x00')
            else:
                raise SyntaxError(
                    f"Illegal symbol '{sym}' at ({x},{y}) during compile.")
            y += 1

        if not halted:
            raise SyntaxError("Compile walk left grid without a ░ terminator.")

        for pos, label in patches:
            if label not in code_labels:
                raise SyntaxError(f"Undefined label '{label}' during compile.")
            tgt = code_labels[label]
            if not (0 <= tgt < len(code)):
                raise SyntaxError(
                    f"Label '{label}' resolved to {tgt}, outside code (0..{len(code)-1})")
            code[pos:pos + 4] = tgt.to_bytes(4, 'little')

        return bytes(code), slot_index

    def _compile_instruction(self, payload, emit, emit_imm, slot_index):
        if payload.startswith("<"):
            for item in payload[1:].split(","):
                item = item.strip()
                if not item:
                    continue
                if item in slot_index:
                    emit(OP_GET, slot_index[item])
                else:
                    try:
                        v = int(item, 0)
                    except ValueError:
                        try:
                            v = int(item, 10)  # tolerate leading zeros
                        except ValueError:
                            raise SyntaxError(
                                f"Unknown operand '{item}' at compile time.")
                    emit(OP_LIT)
                    emit_imm(v)
        elif payload.startswith(">"):
            name = payload[1:].strip()
            if name not in slot_index:
                raise SyntaxError(f"Undeclared target variable: '{name}'")
            emit(OP_SET, slot_index[name])
        elif payload.startswith("."):
            op = payload[1:].strip()
            if op not in ALU_OPCODES:
                raise SyntaxError(f"Unknown ALU operator: '{op}'")
            emit(ALU_OPCODES[op])
        else:
            raise SyntaxError(f"Unrecognized instruction payload: '{payload}'")

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


class BytecodeVM:
    """Flat-stream interpreter, the shape of the C kernel VM:
    a switch over a uint8_t*, fixed slots, fixed stack, no grid."""

    def __init__(self, bytecode, slots, capacity, max_steps=DEFAULT_MAX_STEPS):
        self.code = bytes(bytecode)
        self.slots = list(slots)          # variable slots (int32 each)
        self.capacity = capacity
        self.stack = [None] * capacity   # kmalloc'd in the kernel port
        self.sp = 0
        self.max_steps = max_steps

    def _push(self, v):
        if self.sp >= self.capacity:
            raise StackOverflow(
                f"Stack overflow: capacity {self.capacity}, sp {self.sp}")
        self.stack[self.sp] = wrap32(v)
        self.sp += 1

    def _pop(self):
        if self.sp == 0:
            raise StackUnderflow("Stack underflow: pop from empty stack")
        self.sp -= 1
        v = self.stack[self.sp]
        self.stack[self.sp] = None
        return v

    def run(self):
        code = self.code
        n = len(code)
        pc = 0
        steps = 0
        halted = False

        def _need(p, width):
            if p < 0 or p + width > n:
                raise VMFault(
                    f"Truncated operand at pc {p} (need {width}, have {n - p})")

        def rd8(p):
            _need(p, 1)
            return code[p]

        def rd32(p):
            _need(p, 4)
            return int.from_bytes(code[p:p + 4], 'little', signed=True)

        while pc < n:
            steps += 1
            if steps > self.max_steps:
                raise VMFault(
                    f"Step limit exceeded ({self.max_steps}), runaway program?")

            op = code[pc]
            pc += 1

            if op == OP_HLT:
                halted = True
                break
            elif op == OP_GET:
                idx = rd8(pc); pc += 1
                if idx >= len(self.slots):
                    raise VMFault(f"GET slot {idx} out of range (have {len(self.slots)})")
                self._push(self.slots[idx])
            elif op == OP_LIT:
                self._push(rd32(pc)); pc += 4
            elif op == OP_POP:
                self._pop()
            # ... ALU ops unchanged through OP_SET ...
            elif op == OP_SET:
                idx = rd8(pc); pc += 1
                if idx >= len(self.slots):
                    raise VMFault(f"SET slot {idx} out of range (have {len(self.slots)})")
                self.slots[idx] = self._pop()
            elif op == OP_JMP:
                tgt = rd32(pc)
                if not (0 <= tgt < n):
                    raise VMFault(f"JMP target {tgt} out of range (0..{n-1})")
                pc = tgt
            elif op == OP_JZ:
                tgt = rd32(pc); pc += 4
                if not (0 <= tgt < n):
                    raise VMFault(f"JZ target {tgt} out of range (0..{n-1})")
                if self._pop() == 0:
                    pc = tgt
            else:
                raise VMFault(f"Illegal opcode 0x{op:02x} at pc {pc - 1}")

        if not halted:
            raise VMFault("Bytecode fell off the end without a HLT.")
        self.stack = None   # kfree(stack)
        self.sp = 0
        return self.slots


# -
# Tests, every case runs through BOTH paths:
#   1. grid-walking interpreter (RailInterpreter.run)
#   2. compiled bytecode (RailInterpreter.compile -> BytecodeVM.run)
# and the resulting variable dumps must agree.
# -

# 1) Spec example: x=10, y=20, result = 10 * (20 + 5) = 250
SOURCE_1 = """
decl x, int, 10;
decl y, int, 20;
decl result, int, 0;

█ 0x10        \\ Initialize stack
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

SOURCE_4 = """
decl i, int, 5;
decl out, int, 0;

█ 0x20
│
├ :loop        \\ loop top
├ < i, 0
├ . >          \\ cond: i > 0
╞ :done        \\ if cond == 0 -> exit
├ < i
├ > out        \\ out = i
├ < i, 1
├ . -
├ > i          \\ i -= 1
↳ :loop        \\ backwards jump = iteration
├ :done
░
"""

def run_conformance(title, source):
    print(f"\n=== {title} ===")
    grid_vm = RailInterpreter(source)
    grid_vm.run()


if __name__ == "__main__":
    run_conformance("Example 1", SOURCE_1)
    run_conformance("Example 2", SOURCE_2)
    run_conformance("Example 3", SOURCE_3)
    run_conformance("Example 4", SOURCE_4)
    print("\nDone")
