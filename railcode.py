"""
    Railcode 0.5 -- frontend (region 1/2 parsing) + CLI entry point.
    Pipeline:
        split_source -> tokenize_header / build_rail -> atomize -> bind -> verify -> VM.run
"""
import argparse
import re
import sys
from collections import namedtuple
from errors import RailError


VERSION                 = "experimental-0.5"
RAIL_CHARS              = set("█├╞↳│░")
MAX_SLOTS               = 256
INT32_MIN, INT32_MAX    = -(2 ** 31), 2 ** 31 - 1

EMPTY_RAILCODE = """
█ :0x01
│
░
"""

#  numbers: the ONLY place integers are parsed
_INT = re.compile(r"[+-]?(0[xX][0-9a-fA-F]+|0[bB][01]+|\d+)$")


def is_int(tok):
    return bool(_INT.match(tok.strip()))


def parse_int(tok, row=None, code="E_INT"):
    tok = tok.strip()
    if not _INT.match(tok):
        raise RailError(code, f"not an integer: {tok!r}", row)
    neg = tok.startswith("-")
    body = tok.lstrip("+-").lower()
    v = int(body, 0) if body[:2] in ("0x", "0b") else int(body, 10)
    v = -v if neg else v
    if not INT32_MIN <= v <= INT32_MAX:
        raise RailError("E_RANGE", f"{tok!r} does not fit int32", row)
    return v


def wrap32(v):
    return ((v + 2 ** 31) & 0xFFFFFFFF) - 2 ** 31


#  source splitting (comments are stripped exactly once, here)
Row = namedtuple("Row", "lineno glyph rest")
_DECL_START = re.compile(r"\s*declare\b")
_DECL = re.compile(r"declare\s+([A-Za-z_]\w*)\s*,\s*(\w+)\s*,\s*([^;]+);$")


def split_source(src):
    """-> (header_rows, rail_rows), each a list of (lineno, text)."""
    header, rail = [], []
    for lineno, line in enumerate(src.splitlines(), 1):
        code = line.split("//", 1)[0].rstrip()
        if not code.strip():
            continue
        (header if _DECL_START.match(code) else rail).append((lineno, code))
    return header, rail


def tokenize_header(header_rows):
    """Region 1: declarations -> ordered {name: int}."""
    symbols = {}
    for lineno, text in header_rows:
        m = _DECL.match(text.strip())
        if not m:
            raise RailError("E_DECL", f"malformed declaration: {text.strip()!r}", lineno)
        name, typ, raw = m.groups()
        if typ != "int":
            raise RailError("E_TYPE", f"type {typ!r} unsupported in 0.5 (int only)", lineno)
        if name in symbols:
            raise RailError("E_DUP_SYM", f"duplicate declaration: {name!r}", lineno)
        symbols[name] = parse_int(raw, lineno)
    if len(symbols) > MAX_SLOTS:
        raise RailError("E_SLOTS", f"{len(symbols)} symbols exceeds {MAX_SLOTS}")
    return symbols


def build_rail(rail_rows):
    """Region 2: every row must START with a rail glyph (stray text is a fault)."""
    rows = []
    for lineno, text in rail_rows:
        x = len(text) - len(text.lstrip())
        g = text[x]
        if g not in RAIL_CHARS:
            raise RailError("E_STRAY", f"row does not start with a rail glyph: {text.strip()!r}", lineno)
        rows.append(Row(lineno, g, text[x + 1:].strip()))
    return rows


def main(argv=None):
    # deferred import: compiler imports this module (cycle)
    from compiler import build_program
    from vm import VM

    ap = argparse.ArgumentParser(prog="railcode", description=f"Railcode {VERSION}")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--atoms", action="store_true", help="low-pass 1 output")
    ap.add_argument("--code",  action="store_true", help="low-pass 2 output")
    ap.add_argument("--trace", action="store_true", help="print pc/op/stack per step")
    ap.add_argument("--fuel",  type=int, default=256, help="max loop fuel (↳ back-edges)")
    a = ap.parse_args(argv)

    try:
        src = open(a.file, encoding="utf-8").read() if a.file else EMPTY_RAILCODE
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    try:
        # builders
        atoms, prog, peak = build_program(src)
        if a.atoms:
            for x in atoms:
                print("atom ", tuple(x))
        if a.code:
            print(f"capacity={prog.capacity} peak_depth={peak} slots={prog.slots} labels={prog.labels}")
            for pc, i in enumerate(prog.code):
                print(f"{pc:3} {i.op:<6} {i.arg!s:<5} (row {i.row})")

        tr = (lambda pc, i, st: print(f"  [{pc:3}] {i.op:<6} {i.arg!s:<5} stack={st}")) if a.trace else None

        r = VM(prog).run(a.fuel, tr)

    except RailError as e:
        print(f"railcode fault: {e}", file=sys.stderr)
        return 1
    print(f"! halted: steps={r['steps']} fuel_used={r['fuel_used']} stack={r['stack']}")
    print("Debug symbols:")
    for n, v in r["symbols"].items():
        print(f"{n} = {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
