# Railcode (Prototype, rev 0.3-experimental)

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

The grid interpreter tracks an instruction pointer using (`X, Y`) coordinates. Normal execution advances vertically down the grid (`Y++`).  

- `█` identifies the program entry and declares the operand-stack capacity.
- `│` is a passive flow rail. It advances execution without performing an operation.
- `├` is an active instruction conduit. Its payload may contain an instruction or a label definition.
- `↳` performs an unconditional jump to a label.
- `╞` performs a conditional jump, consuming the top stack value and jumping when that value is zero.
- `░` terminates execution.

## Static symbol resolution

Variable declarations are resolved to fixed-index slots during compilation.  
Labels are resolved to bytecode addresses, and jump operands are patched before execution.  

## Stack model

Railcode uses a bounded operand stack with a capacity declared at the entry marker.  
Stack operations use a fixed allocation rather than allocating memory for individual pushes.  

## Example: ALU operations
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
> Result: `{'x': 10, 'y': 20, 'result': 250}`  

## Example: count-down:  
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

## Example: While-loops

```py
    decl task, int, 1;
    
    █ 0x10
    ├ :loop    //while (true) {
    ├ < task    // do some computation...
    ├ > task      
    ↳ :loop    //}
    ░
```
> Stack overflow, stack underflow, invalid instructions, and execution-budget exhaustion are runtime errors. 
> The prototype also defines signed 32-bit arithmetic behavior, including wrapping for arithmetic results and division truncation toward zero.

---

## 2. Syntax & Glyph Taxonomy

### Global Header

```rust
decl <identifier>, <type>, <initial_value>;

```
> Allocates a fixed-size slot in the VM's variable array. Supported types are restricted to `int` (32-bit signed integer).

## 3. Instruction Set

The following table describes the currently defined bytecode encoding.  

Glyph : source form	/ Opcode / Operand / Behavior:  
- `< var`    : `GET` / 0x01	/ 1-byte / slot	Push the variable's value
- `< imm`    : `LIT` / 0x02	/ 4-byte / signed LE	Push a signed 32-bit immediate
- `╞`        : `POP` / 0x03	/ None	/ Pop and discard the top value; grammar status is unresolved (bare symbol)
- `. +`      : `ADD` / 0x10	/ None	/ Add the top two values
- `. -`	     : `SUB` / 0x11	/ None	/ Subtract the top value from the preceding value
- `. *`	     : `MUL` / 0x12	/ None	/ Multiply the top two values
- `. /`	     : `DIV` / 0x13	/ None	/ Divide the preceding value by the top value
- `. ==`     : `EQ` / 0x14	/ None	/ Push 1 if equal, otherwise 0
- `. !=`     : `NE` / 0x15	/ None	/ Push 1 if unequal, otherwise 0
- `. <`	     : `LT` / 0x16	/ None	/ Push 1 if less than, otherwise 0
- `. <=`     : `LE` / 0x17	/ None	/ Push 1 if less than or equal, otherwise 0
- `. >`	     : `GT` / 0x18	/ None	/ Push 1 if greater than, otherwise 0
- `. >=`     : `GE` / 0x19	/ None	/ Push 1 if greater than or equal, otherwise 0
- `> var`    : `SET` / 0x20	/ 1-byte / slot	Pop a value into the variable
- `↳ :label` : `JMP` / 0x30	/ 4-byte / LE address	Jump unconditionally
- `╞ :label` : `JZ` / 0x31	/ 4-byte / LE address	Pop a value; jump if zero
- `░`	       : `HLT` / 0xFF	/ None	/ Halt execution

> LE in the operand column means little-endian encoding. Immediate values and jump addresses occupy four bytes.
> more coming soon...

---
