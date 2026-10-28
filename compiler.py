"""Railcode 0.5 driver:  source -> rows -> atoms -> bound program -> verified -> VM"""
import argparse
import sys
from railcode import (VERSION, EMPTY_RAILCODE, RailError, split_source, tokenize_header, build_rail)
from atom import atomize
from binding import bind
from verify import verify
from vm import VM


def build_program(src):
    header_rows, rail_rows = split_source(src)
    header = tokenize_header(header_rows)
    atoms = atomize(build_rail(rail_rows))
    program = bind(header, atoms)
    peak = verify(program)
    return atoms, program, peak


def main(argv=None):
    ap = argparse.ArgumentParser(prog="railcode", description=f"Railcode {VERSION}")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--atoms", action="store_true", help="dump pass 1 output")
    ap.add_argument("--code",  action="store_true", help="dump pass 2 output")
    ap.add_argument("--trace", action="store_true", help="print pc/op/stack per step")
    ap.add_argument("--fuel",  type=int, default=256, help="max loop back-edges")
    a = ap.parse_args(argv)

    if a.file:
        with open(a.file, encoding="utf-8") as f:
            src = f.read()
    else:
        src = EMPTY_RAILCODE
    try:
        atoms, prog, peak = build_program(src)
        if a.atoms:
            for x in atoms: print("atom ", tuple(x))
        if a.code:
            print(f"capacity={prog.capacity} peak_depth={peak} slots={prog.slots} labels={prog.labels}")
            for pc, i in enumerate(prog.code): print(f"{pc:3} {i.op:<6} {i.arg!s:<5} (row {i.row})")
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
