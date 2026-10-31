# Railcode (Prototype, rev 0.5-experimental)

A spatial, 2D grid-based stack machine designed for my [Symbiote kernel project](https://github.com/TheBarret/Symbiote-active).  

# Usage 
```
python railcode.py --help
usage: railcode [-h] [--atoms] [--code] [--trace] [--fuel FUEL] [file]

Railcode experimental-0.5

positional arguments:
  file

options:
  -h, --help   show this help message and exit
  --atoms      low-pass 1 output
  --code       low-pass 2 output
  --trace      print pc/op/stack per step
  --fuel FUEL  max loop fuel (↳ back-edges)

```

<img width="1256" height="660" alt="image" src="https://github.com/user-attachments/assets/edeed921-e36c-4f2b-a3cf-c1c3e7f14b43" />  

# Specification & Architecture

## 1. Overview & Core Principles

Railcode is a NOTATION, not an architecture. Rows are read top to bottom;  
the glyph at the start of a row selects the tier, column position carries no meaning yet.  

**Rail glyphs (CP437):**  
- ` █ `  stack allocation directive     (█ :0x10  -> 16 cells, exactly one, first)
- ` ├ `  data tier     (< push, > store/drop, ALU words, . print, :label)
- ` ╞ `  control tier  (== != < > <= >= :label   -- forward only, pops 2)
- ` ↳ `  unconditional jump (↳ :label            -- backward only)
- ` │ `  pass-through rail (no code)
- ` ░ `  halt

* **Spatial Execution Vector:**   
  The Instruction Pointer (IP) tracks coordinates (`X, Y`).  
  By default, the spine flows vertically downward (`Y++`).  

* **Conduit Enforcement:**  
  State mutations and stack operations are strictly prohibited on passive rails (`│`).  
  They are only permitted when the IP intersects an active conduit (`█` or `├`) or limb structure (`╞`).  

* **Static Symbol Resolution:**  
  Variable names are resolved to fixed-index slots at load time, eliminating runtime dictionary overhead.

**Axioms:**  
  1. Spatial IP: position (`X, Y`). Default flow is gravity (`Y++`); a rail row is discharged before the IP falls.  
  2. Two regions: the header (symbol space, linearly tokenized) and the rail (execution space, spatially traversed).  
  3. Two glyph tiers: `├` = data path (stack / ALU ops), `╞` = control path (branches / conditionals).  

Header (tokenized before the IP ever drops):  
  `declare <symbol>, <type>, <value>;`  

Example of a count-down:  
```
  // header
  declare x, int, 0;
  
  // rail
  █ :2            // STACK_OPEN (= kmalloc(2xint))
  │               // NOP's
  ├ :loop
  ├ < x, 255     // PUSH x, 255
  ╞ == :end      // JEQ [loop]
  │
  ├ < x, 1       // PUSH x, 1
  ├ +            // ADD
  ├ > x          // POP x
  │
  ↳ :loop        // JMP [loop]
  ├ :end
  ├ < x          // PUSH x
  ├ .           // POP, PRINTF
  │
  ░               // STACK_CLOSE (= HALT, kfree())
```

> Tab's and spaces matter in this context, re-aligning this (cosmetically) can produce parsing errors.  

## Changelog

- A bare `█ :10` parsed as **decimal**, or `█ :0x10` for hexadecimal.
- Incorrect `├ . +` syntax now faults.
- `PUSH` is split internally into `LIT` and `GET` atoms, so one row can yield several atoms.
- **Forward and backward rules:** conditional jumps must go forward and `↳` must go backward, enforced by the binder (`E_DIRECTION`). 
- **Verifier:** One pass proves that stack depth agrees at every merge, including loop heads, with no underflow, no overflow past `█`, no dead code.
- **Value space:** int32 only, with wrapping and C-style truncating `/` and `%`. String declarations are rejected (`E_TYPE`).
- **Added ops:** `dup`, `swap`, `over`, `/ % & | ^`, and `<=` / `>=` in `╞`. The stack-effect table drives both the verifier and the runtime checks.
- **I/O:** `├ .` calls `out` sink instead of a hard-wired (stdout) `print`.
- **Debug flags:** `--atoms`, `--code`, `--trace`, and `--fuel N`.

---
