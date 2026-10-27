# Railcode

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


Example:  
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

---

## 2. Syntax & Glyph Taxonomy

### Global Header

```rust
decl <identifier>, <type>, <initial_value>;

```

Allocates a fixed-size slot in the VM's variable array. Supported types are restricted to `int` (32-bit signed integer).

### Spatial Glyphs

| Glyph | Name | Description |
| --- | --- | --- |
| `█` | Ignition / Entry | Program entry point; initializes stack and sets initial IP coordinates. |
| `│` | Spine Rail | Passive vertical channel. Pure transit; zero side-effects. |
| `├` | Active Conduit | Unconditional limb/node entry. Permits instruction payload execution. |
| `╞` | Conditional Limb | Pops top of stack. If zero, shifts IP heading right ($X++$) into a horizontal limb. |
| `╛` | Limb Cap | Returns IP from horizontal limb back to the vertical spine, incrementing $Y$. |
| `░` | Terminator | Halts execution cleanly. Missing terminator throws a fatal VM fault. |

---

## 3. Instruction Set Architecture (ISA) & Micro-Ops

Instructions follow the conduit symbol on the same line, separated by whitespace.

| Operation | Syntax | Description |
| --- | --- | --- |
| **Load / Push** | `< x, y, 5` | Pushes variable slots (`x`, `y`) or immediate literals (`5`) onto the stack. |
| **Store / Pop** | `> result` | Pops the top stack value and stores it into a pre-allocated variable slot index. |
| **ALU Operator** | `. +`, `. -`, `. *`, `. /` | Pops two elements ($a$, $b$), executes operation, and pushes the wrapped int32 result. |

### Arithmetic & Numeric Conformance Rules

* **Truncating Division:** Division (`/`) truncates toward zero (matching C99 behavior rather than Python floor division).
* **Int32 Wrapping:** All ALU operations wrap explicitly to 32-bit signed integer boundaries (`-2147483648` to `2147483647`).

---

## 4. Bytecode Mapping Reference

To bridge text-based grid layouts to low-level execution, the loader compiles text grids into a flat stream of encoded opcodes and immediate operand bytes.

* **Opcode Encoding:** 1-byte instruction identifiers (e.g., `GET` = `0x01`, `LIT` = `0x02`, `ADD` = `0x10`, `SET` = `0x20`, `HLT` = `0xFF`).
* **Operand Bytes:** Fixed-width slot indices or immediate values following the opcode.

```text
# Example: Push x, y, add, store
[GET slot_x] [GET slot_y] [ADD] [SET slot_result]

```
