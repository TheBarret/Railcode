#!/usr/bin/env python3
"""Railcode prototype interpreter.

Axioms:
  1. Spatial IP: position (X, Y). Default flow is gravity (Y++);
     a rail row is discharged before the IP falls.
  2. Two regions: the header (symbol space, linearly tokenized)
     and the rail (execution space, spatially traversed).
  3. Two glyph tiers:  ├ = data path (stack / ALU ops),
                       ╞ = control path (branches / conditionals).

Rail glyphs (CP437):
  █   stack allocation directive   (█ :0x10  -> 16 cells)
  ├   data-tier instruction       (< push, > store, + - * ALU, . print)
  ╞   control-tier instruction     (== != < >  :label)
  ↳   unconditional jump           (↳ :label)
  │   vertical pass-through rail
  ░   halt / ground

Header (tokenized before the IP ever drops):
  declare <symbol>, <type>, <value>;

Usage:
  python railcode.py program.rail      # run a source file
  python railcode.py                   # run the built-in RAILCODE_SRC
"""

import re
import sys

RAIL_CHARS = set("█├╞↳│░")
EXEC_CHARS = set("█├╞↳░")


class RailError(Exception):
    """ lexing / parsing / runtime fault in the rail"""


#  header

def tokenize_header(src):
    """Region 1: linear tokenization of declarations into symbol space."""
    symbols = {}
    for m in re.finditer(
        r"declare\s+([A-Za-z_]\w*)\s*,\s*(\w+)\s*,\s*([^;]+);", src
    ):
        name, _typ, raw = m.groups()
        raw = raw.strip()
        if re.fullmatch(r"-?\d+", raw):
            symbols[name] = int(raw)
        elif raw.startswith('"') and raw.endswith('"'):
            symbols[name] = raw[1:-1]
        else:
            symbols[name] = raw
    return symbols


#  rail grid

def build_grid(src):
    """Region 2: the rail. Comments stripped, non-rail lines dropped."""
    grid = []
    for line in src.splitlines():
        code = line.split("//", 1)[0].rstrip()
        if any(ch in RAIL_CHARS for ch in code):
            grid.append(code)
    return grid


def first_glyph(row):
    """Locate the leading rail glyph of a row: the IP's (X, Y) anchor."""
    for x, ch in enumerate(row):
        if ch in RAIL_CHARS:
            return x, ch
    return None, None


def collect_labels(grid):
    """Pre-pass: resolve ':label' definitions to grid coordinates (Y)."""
    labels = {}
    for y, row in enumerate(grid):
        x, glyph = first_glyph(row)
        if x is None or glyph in "█↳":
            continue
        rest = row[x + 1:].strip()
        if rest.startswith(":"):
            labels[rest[1:].strip()] = y
    return labels


#  machine

class Machine:
    def __init__(self, src):
        self.symbols = tokenize_header(src)
        self.grid = build_grid(src)
        self.labels = collect_labels(self.grid)
        self.stack = []
        self.capacity = 0
        self.steps = 0

    def resolve(self, tok):
        tok = tok.strip()
        if re.fullmatch(r"-?\d+", tok):
            return int(tok)
        if re.fullmatch(r"0[xX][0-9a-fA-F]+", tok):
            return int(tok, 16)
        if tok in self.symbols:
            return self.symbols[tok]
        raise RailError(f"unknown symbol: {tok!r}")

    # -- gravity: fall to the next executable row, skipping │ rails
    def fall(self, y):
        ny = y + 1
        while ny < len(self.grid):
            x, glyph = first_glyph(self.grid[ny])
            if x is not None and glyph in EXEC_CHARS:
                return ny
            ny += 1
        return len(self.grid)  # fell off the world

    def run(self, max_steps=1_000_000):
        y = 0
        while y < len(self.grid):
            if self.steps > max_steps:
                raise RailError("step limit exceeded (runaway rail)")
            x, glyph = first_glyph(self.grid[y])
            if x is None:
                y += 1
                continue
            row = self.grid[y]
            rest = row[x + 1:].strip()

            #  ░ the ground: halt
            if glyph == "░":
                return {"halted": True, "steps": self.steps,
                        "symbols": self.symbols, "capacity": self.capacity}

            #  │ pass-through
            if glyph == "│":
                y += 1
                continue

            #  █ allocation directive
            if glyph == "█":
                tok = rest.lstrip(":").strip()
                try:
                    self.capacity = int(tok, 16)
                except ValueError:
                    raise RailError(f"bad █ operand: {tok!r}")
                self.stack = []
                y += 1
                continue

            #  ↳ unconditional jump
            if glyph == "↳":
                label = rest.lstrip(":").strip()
                if label not in self.labels:
                    raise RailError(f"unknown label: {label!r}")
                self.steps += 1
                y = self.labels[label]
                continue

            op = rest.split()[0] if rest else ""
            argstr = rest[len(op):].strip()

            #  ├ data tier
            if glyph == "├":
                if op.startswith(":"):          # label definition
                    y += 1
                    continue
                if op == "<":                   # push operands
                    for a in argstr.split(","):
                        self.stack.append(self.resolve(a))
                elif op == ">":                 # pop, store into symbol
                    if not self.stack:
                        raise RailError("store on empty stack")
                    self.symbols[argstr.strip()] = self.stack.pop()
                elif op in ("+", "-", "*"):
                    b = self._pop()
                    a = self._pop()
                    if op == "+":
                        self.stack.append(a + b)
                    elif op == "-":
                        self.stack.append(a - b)
                    else:
                        self.stack.append(a * b)
                elif op == ".":
                    print(self._pop())
                else:
                    raise RailError(f"bad ├ op: {op!r}")

            #  ╞ control tier
            elif glyph == "╞":
                label = argstr.lstrip(":").strip()
                if label not in self.labels:
                    raise RailError(f"unknown label: {label!r}")
                b = self._pop()
                a = self._pop()
                conds = {
                    "==": a == b, "!=": a != b,
                    "<": a < b, ">": a > b,
                }
                if op not in conds:
                    raise RailError(f"bad ╞ op: {op!r}")
                if conds[op]:                   # true -> divert the rail
                    self.steps += 1
                    y = self.labels[label]
                    continue
                # false -> let gravity take over

            self.steps += 1
            y = self.fall(y)

        return {"halted": False, "steps": self.steps,
                "symbols": self.symbols, "capacity": self.capacity}

    def _pop(self):
        if not self.stack:
            raise RailError("pop on empty stack")
        return self.stack.pop()


#  RAILCODE_SRC

RAILCODE_SRC = """
// header
declare x, int, 0;

// rail
█ :0x10
├ :loop
│
├ < x, 10
╞ == :end
│
├ < x, 1
├ +
├ > x
│
↳ :loop
│
├ :end
░
"""

def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            src = f.read()
    else:
        src = RAILCODE_SRC
    result = Machine(src).run()
    status = "halted on ░" if result["halted"] else "fell off the rail"
    print(f"[rc] {status} after {result['steps']} steps")
    for name, value in result["symbols"].items():
        print(f"[rc]   {name} = {value!r}")


if __name__ == "__main__":
    main()
