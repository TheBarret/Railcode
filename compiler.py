import sys
from railcode import EMPTY_RAILCODE, build_grid
from atom import atomize
from binding import bind
from vm import VM

def compile(src):
    grid        = build_grid(src)
    atoms       = atomize(grid)
    code, labels, slots, consts = bind(src, atoms)
    return code, labels, slots, consts

def main():
    src = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else EMPTY_RAILCODE
    code, labels, slots, consts = compile(src)
    state = VM(code, labels, slots, consts).run(256)
    print("Debug symbols:")
    for n, v in state["symbols"].items():
        print(f"{n} = {v!r}")

if __name__ == "__main__":
    main()
