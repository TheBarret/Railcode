"""Railcode frontend  --  version: experimental-0.5

Railcode is a NOTATION, not an architecture. Rows are read top to bottom;
the glyph at the start of a row selects the tier. Column position carries no
meaning yet (the 2D / heading model is a later experiment).

Rail glyphs (CP437):
  █   stack allocation directive     (█ :0x10  -> 16 cells, exactly one, first)
  ├   data tier     (< push, > store/drop, ALU words, . print, :label)
  ╞   control tier  (== != < > <= >= :label   -- forward only, pops 2)
  ↳   unconditional jump (↳ :label            -- backward only)
  │   pass-through rail (no code)
  ░   halt

Header (one declaration per line, int only):
  declare <symbol>, int, <value>;

Numbers: decimal, 0x.., 0b.., optional sign, int32 range. (0.5: a bare
'█ :10' is DECIMAL; 0.4 parsed it as hex.)
"""
import re
from collections import namedtuple

VERSION = "experimental-0.5"
RAIL_CHARS = set("█├╞↳│░")
INT32_MIN, INT32_MAX = -(2 ** 31), 2 ** 31 - 1
MAX_SLOTS = 256

EMPTY_RAILCODE = """
█ :0x01
│
░
"""


class RailError(Exception):
    """Single fault type for every stage. code = stable reason, row = source line."""
    def __init__(self, code, msg, row=None):
        self.code, self.msg, self.row = code, msg, row
        loc = f"row {row}: " if row else ""
        super().__init__(f"[{code}] {loc}{msg}")

class AtomError(RailError):   pass
class BindError(RailError):   pass
class VerifyError(RailError): pass
class VMError(RailError):     pass


#  numbers: the ONLY place integers are parsed
_INT = re.compile(r"[+-]?(0[xX][0-9a-fA-F]+|0[bB][01]+|\d+)$")

def is_int(tok):
    return bool(_INT.match(tok.strip()))

def parse_int(tok, row=None, cls=RailError, code="E_INT"):
    tok = tok.strip()
    if not _INT.match(tok):
        raise cls(code, f"not an integer: {tok!r}", row)
    neg = tok.startswith("-")
    body = tok.lstrip("+-").lower()
    v = int(body, 0) if body[:2] in ("0x", "0b") else int(body, 10)
    v = -v if neg else v
    if not INT32_MIN <= v <= INT32_MAX:
        raise cls("E_RANGE", f"{tok!r} does not fit int32", row)
    return v

def wrap32(v):
    return ((v + 2 ** 31) & 0xFFFFFFFF) - 2 ** 31


#  source splitting (comments are stripped exactly once, here)
Row = namedtuple("Row", "lineno x glyph rest")
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
        rows.append(Row(lineno, x, g, text[x + 1:].strip()))
    return rows
