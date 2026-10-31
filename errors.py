"""
Railcode 0.5 -- single fault type for every stage.

Every stage (frontend, atomize, bind, verify, vm) raises RailError.
Code catalog, grouped by the stage that raises it:

  frontend (railcode.py)
    E_DECL       malformed declare line
    E_TYPE       non-int type in a declaration (int only in 0.5)
    E_DUP_SYM    duplicate symbol declaration
    E_SLOTS      too many symbols (MAX_SLOTS)
    E_STRAY      rail row does not start with a rail glyph
    E_INT        not an integer (from parse_int)
    E_RANGE      integer literal does not fit int32

  atomize (compiler.py, pass 1)
    E_OPERAND    bad operand / trailing text / unknown ALU word
    E_ALLOC      █ malformed, non-positive, missing, duplicated, or misplaced
    E_LABEL      █? no -- bad ↳/╞/:label form, or unknown label at bind
    E_OP         bad ╞ form, or empty ├ row

  bind (compiler.py, pass 2)
    E_SHAPE      operand-shape contract violated (op with None operand got arg)
    E_SYMBOL     undeclared symbol
    E_LABEL_DUP  duplicate label definition
    E_LABEL_END  label points past the last instruction
    E_DIRECTION  cond jump not forward / ↳ not strictly backward

  verify (compiler.py, pass 3)
    E_DEAD       unreachable instruction
    E_UNDERFLOW  static stack underflow
    E_OVERFLOW   static stack exceeds █ capacity
    E_DEPTH      merge or back-edge arrives with disagreeing depth
    E_FALL_OFF   program can fall off the end without ░

  vm (vm.py, pass 4)
    E_UNDERFLOW  runtime stack underflow (same code as verify, different site)
    E_OVERFLOW   runtime stack overflow
    E_DIV0       division by zero
    E_OPCODE     bad opcode in dispatch
    E_FALL_OFF   pc left the program
    E_INTERNAL   non-RailError exception caught and wrapped
    E_FUEL       fuel exhausted (returned as a result dict, not raised)

Note E_UNDERFLOW and E_OVERFLOW are deliberately shared between verify and
vm: the same invariant, enforced statically and (defensively) at runtime.
"""


class RailError(Exception):
    """Single fault type for every stage. code = stable reason, row = source line."""
    def __init__(self, code, msg, row=None):
        self.code, self.msg, self.row = code, msg, row
        loc = f"row {row}: " if row else ""
        super().__init__(f"[{code}] {loc}{msg}")
