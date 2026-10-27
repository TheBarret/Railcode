import re


class StackOverflow(Exception):
    pass


class StackUnderflow(Exception):
    pass


class RailInterpreter:
    def __init__(self, source_code):
        self.variables = {}
        # Mirror of a kmalloc'd slot buffer + stack pointer.
        # (In the kernel version: `self.slots = kmalloc(cap * sizeof(slot))`,
        #  `self.sp = 0`, and `kfree(self.slots)` on halt.)
        self.stack_capacity = None   # set from `█ <size>`
        self.stack_slots = None      # fixed-size buffer, allocated at entry
        self.sp = 0                  # stack pointer: next free slot index
        self.grid = []
        self.labels = {}
        self.ip = (0, 0)
        self.entry = None            # (x, y) of █
        self._parse_source(source_code)

    # ---- stack primitive that respects the fixed allocation ----
    def _stack_push(self, value):
        if self.sp >= self.stack_capacity:
            raise StackOverflow(
                f"Stack overflow: capacity {self.stack_capacity}, sp {self.sp}"
            )
        self.stack_slots[self.sp] = value
        self.sp += 1

    def _stack_pop(self):
        if self.sp == 0:
            raise StackUnderflow("Stack underflow: pop from empty stack")
        self.sp -= 1
        v = self.stack_slots[self.sp]
        self.stack_slots[self.sp] = None  # clear slot (mimics kfree hygiene)
        return v

    def _parse_source(self, code):
        lines = code.splitlines()
        grid_lines = []

        for y, line in enumerate(lines):
            clean_line = line.split('\\')[0].rstrip()

            if clean_line.startswith("decl"):
                match = re.match(r"decl\s+(\w+),\s*(\w+),\s*(.+);", clean_line)
                if match:
                    var_name, var_type, val = match.groups()
                    self.variables[var_name] = int(val) if var_type == "int" else val
                continue

            if clean_line.strip():
                grid_lines.append(clean_line)

        max_width = max(len(l) for l in grid_lines) if grid_lines else 0
        self.grid = [list(l.ljust(max_width)) for l in grid_lines]

        for y, row in enumerate(self.grid):
            for x, char in enumerate(row):
                if char == '█':
                    self.ip = (x, y)
                    self.entry = (x, y)
                    # █ <size>  -- declarative: allocate the stack here.
                    payload = "".join(row[x+1:]).split('\\')[0].strip()
                    if not payload:
                        raise SyntaxError(
                            f"Entry marker █ at ({x},{y}) must declare a stack size."
                        )
                    # Accept 0xff, 0b1010, 0o777, or plain decimal.
                    try:
                        size = int(payload, 0)
                    except ValueError:
                        raise ValueError(
                            f"Invalid stack size '{payload}' at entry marker."
                        )
                    if size <= 0:
                        raise ValueError("Stack size must be positive.")
                    self.stack_capacity = size
                    self.stack_slots = [None] * size   # kmalloc(size * slot)
                    self.sp = 0
                elif char == '├' and ':' in "".join(row[x:]):
                    rest = "".join(row[x:]).strip()
                    label_match = re.search(r"(:[\w]+)", rest)
                    if label_match:
                        self.labels[label_match.group(1)] = (x, y)

    def run(self):
        if self.entry is None:
            raise SyntaxError("No entry marker (█) found in program.")
        if self.stack_slots is None:
            raise SyntaxError("Entry marker did not allocate a stack.")

        x, y = self.ip
        height = len(self.grid)
        width = len(self.grid[0]) if height > 0 else 0

        print(f"--- Starting execution at IP ({x}, {y}) "
              f"with stack capacity {self.stack_capacity} ---")

        try:
            while 0 <= y < height and 0 <= x < width:
                symbol = self.grid[y][x]

                if symbol == '░':
                    print(">>> Halting.")
                    break
                elif symbol == '│':
                    pass  # closed pipe: pure flow
                elif symbol == '█':
                    # Entry marker is declarative; crossing it is just flow.
                    pass
                elif symbol == '├':
                    payload = "".join(self.grid[y][x+1:]).split('\\')[0].strip()
                    if not payload:
                        pass
                    elif payload.startswith(':'):
                        pass # skip label reference
                    else:
                        self._execute_instruction(payload)
                else:
                    raise SyntaxError(
                        f"Illegal symbol '{symbol}' outside of an active "
                        f"conduit at ({x}, {y})."
                    )

                y += 1
                self.ip = (x, y)
        finally:
            self.stack_slots = None
            self.sp = 0
            print(f"--- Execution finished. Final variables: {self.variables} ---")


    def _resolve_operand(self, op_str):
        """Resolves a token to its integer value or variable reference."""
        op_str = op_str.strip()
        if op_str in self.variables:
            return self.variables[op_str]
        try:
            return int(op_str, 0)  # allows 0xff, 0b1010, plain decimal
        except ValueError:
            raise ValueError(f"Invalid operand or unresolved variable: '{op_str}'")

    def _execute_instruction(self, payload):
        # 1. Push / Load to Stack (<)
        if payload.startswith("<"):
            items = [i.strip() for i in payload[1:].split(",")]
            for item in items:
                val = self._resolve_operand(item)
                self._stack_push(val)

        # 2. Pop / Store from Stack (>)
        elif payload.startswith(">"):
            var_name = payload[1:].strip()
            if var_name not in self.variables:
                raise NameError(f"Undeclared target variable: '{var_name}'")
            self.variables[var_name] = self._stack_pop()

        # 3. ALU Operations (.)
        elif payload.startswith("."):
            op = payload[1:].strip()
            if self.sp < 2:
                raise IndexError(
                    f"ALU operation '{op}' requires at least 2 elements on the stack."
                )
            b = self._stack_pop()
            a = self._stack_pop()

            if op == "+":   self._stack_push(a + b)
            elif op == "-": self._stack_push(a - b)
            elif op == "*": self._stack_push(a * b)
            elif op == "/":
                if b == 0:
                    raise ZeroDivisionError("ALU division by zero")
                self._stack_push(a // b)
            else:
                raise ValueError(f"Unknown ALU operator: '{op}'")

        else:
            raise ValueError(f"Unrecognized instruction payload: '{payload}'")

#  Test Execution
source = """
decl x, int, 10;
decl y, int, 20;
decl result, int, 0;

█ 0xff        \\ Initialize stack
│             \\ NOP channel
├ :program    \\ Program entry conduit
│
├ < x, y, 5   \\ Push variables x, y, and immediate literal 5
├ . +         \\ Add top two elements (y + 5 = 25)
├ . *         \\ Multiply with next stack element (10 * 25 = 250)
├ > result    \\ Pop final result into variable 'result'
│
░             \\ Halt program
"""

print("program:\n")
print(source)
print("\n")
interpreter = RailInterpreter(source)
interpreter.run()
