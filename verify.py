"""
Pass 3: load-time verifier. One forward pass proves:
 - no stack underflow / overflow (vs █ capacity) on any path
 - stack depth agrees at every merge (fall-through vs jump, loop head vs back-edge)
 - no dead code, and no path falls off the end without HALT

Returns the maximum static stack depth.
"""
from railcode import VerifyError
from spec import OPS, COND_JUMPS


def verify(p):
    code, cap = p.code, p.capacity
    seen, pending = {}, {}          # pc -> depth (reached by fall/back) / (forward jump)
    cur, peak = 0, 0

    for pc, ins in enumerate(code):
        if pc in pending:
            if cur is None:
                cur = pending[pc]
            elif cur != pending[pc]:
                raise VerifyError("E_DEPTH", f"stack depth {cur} vs {pending[pc]} at merge", ins.row)
        if cur is None:
            raise VerifyError("E_DEAD", "unreachable instruction", ins.row)
        seen[pc] = cur

        spec = OPS[ins.op]
        if cur < spec.pops:
            raise VerifyError("E_UNDERFLOW", f"{ins.op} needs {spec.pops}, stack has {cur}", ins.row)
        cur = cur - spec.pops + spec.pushes
        if cur > cap:
            raise VerifyError("E_OVERFLOW", f"depth {cur} exceeds █ capacity {cap}", ins.row)
        peak = max(peak, cur)

        if ins.op in COND_JUMPS:
            if pending.setdefault(ins.arg, cur) != cur:
                raise VerifyError("E_DEPTH", "jump arrives with a different depth", ins.row)
        elif ins.op == "JMP":
            if seen[ins.arg] != cur:
                raise VerifyError("E_DEPTH",
                                  f"back-edge depth {cur} != loop head depth {seen[ins.arg]}", ins.row)
            cur = None
        elif ins.op == "HALT":
            cur = None

    if cur is not None:
        raise VerifyError("E_FALL_OFF", "program can fall off the end without ░", code[-1].row if code else None)
    return peak
