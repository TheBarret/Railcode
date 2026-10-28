# Railcode (Prototype, rev 0.4-experimental)

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

**Axioms:**  
  1. Spatial IP: position (`X, Y`). Default flow is gravity (`Y++`);  
     a rail row is discharged before the IP falls.  
  2. Two regions: the header (symbol space, linearly tokenized)  
     and the rail (execution space, spatially traversed).  
  3. Two glyph tiers: `├` = data path (stack / ALU ops),  
                      `╞` = control path (branches / conditionals).  

**Rail glyphs (CP437):**  
-  `█`   stack allocation directive   (`█ :0x10`  -> 16 cells)
-  `├`   data-tier instruction        (`<` push, `>` store, `+ - *` ALU, `.` print)
-  `╞`   control-tier instruction     (`== != < >, :label`)
-  `↳`   unconditional jump           (`↳ :label`)
-  `│`   vertical pass-through rail
-  `░`   halt / ground

Header (tokenized before the IP ever drops):  
  `declare <symbol>, <type>, <value>;`  

Example of a count-down:  
```
  // header
  declare x, int, 0;
  
  // rail
  █ :0x10        // kmalloc(16)
  ├ :loop
  │
  ├ < x, 10      // push x, 10
  ╞ == :end      // jump { end } if x == 10 
  │
  ├ < x, 1       // push x, 1
  ├ +            // addition
  ├ > x          // pop 
  │
  ↳ :loop        // loop back
  │
  ├ :end
  ░
```

---
