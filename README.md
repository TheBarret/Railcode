# Railcode (Prototype, rev 0.3)

A spatial, 2D grid-based stack machine designed for my [Symbiote kernel project](https://github.com/TheBarret/Symbiote-active).  


# Specification & Architecture

## 1. Overview & Core Principles

The Rail-Code VM is a spatial, 2D grid-based stack machine.  
Unlike linear esolangs, execution pathing is determined by topological rails and explicit active conduits  
rather than a raw program counter increment (`PC++`).  

* **Spatial Execution Vector:**   
  The Instruction Pointer (IP) tracks coordinates (`X, Y`).  
  By default, the spine flows vertically downward (`Y++`).  

* **Conduit Enforcement:**  
  State mutations and stack operations are strictly prohibited on passive rails (`│`).  
  They are only permitted when the IP intersects an active conduit (`█` or `├`) or limb structure (`╞`).  

* **Static Symbol Resolution:**  
  Variable names are resolved to fixed-index slots at load time, eliminating runtime dictionary overhead.


ALU Example:  
```py
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
```

> Would result in: `{'x': 10, 'y': 20, 'result': 250}`  

Example of a count-down:  
```py
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
```

---

## 2. Syntax & Glyph Taxonomy

### Global Header

```rust
decl <identifier>, <type>, <initial_value>;

```
> Allocates a fixed-size slot in the VM's variable array. Supported types are restricted to `int` (32-bit signed integer).

### 3. Railcode

```
    Glyph            Bytecode

    < var            GET  slot          0x01 <slot:1>
    < imm            LIT  imm32         0x02 <imm:4, signed LE>
    ╞ (bare)         POP                0x03
    . +              ADD                0x10
    . -              SUB                0x11
    . *              MUL                0x12
    . /              DIV                0x13 (C99 trunc, /0 faults)
    . ==             EQ                 0x14
    . !=             NEQ                0x15 (push 1/0)
    . <              LT                 0x16
    . <=             LE                 0x17
    . >              GT                 0x18
    . >=             GE                 0x19
    > var            SET  slot          0x20 <slot:1>
    ↳ :label         JMP  addr          0x30 <addr:4, LE>
    ╞ :label         JZ   addr          0x31 <addr:4, LE>  (pop; jump if 0)
    ░                HLT                0xFF
```

> more coming soon...
