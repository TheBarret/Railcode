"""
Railcode 0.5 -- Bytecode Serializer & Deserializer (.rbc format)
"""
import struct
from collections import namedtuple
from errors import RailError
from opcodes import OPS, ISA_MAJOR, ISA_MINOR

MAGIC = b'RBC1'

# Reverse lookup: opcode byte -> operation name string
OP_BY_CODE = {op.code: name for name, op in OPS.items()}

# We redefine a runtime-friendly Program structure for the VM
BinaryProgram = namedtuple("BinaryProgram", "code slots init capacity")
Instruction   = namedtuple("Instruction", "op arg row")


def serialize_program(prog):
    """Encodes a compiled Program into bytes."""
    header = struct.pack(
        ">4s BB I H",
        MAGIC,
        ISA_MAJOR,
        ISA_MINOR,
        prog.capacity,
        len(prog.slots)
    )

    body = bytearray(header)

    # Pack symbol table (name -> initial value, ordered by slot index)
    # We invert prog.slots to get name by slot index
    slot_to_name = {idx: name for name, idx in prog.slots.items()}
    for i in range(len(prog.slots)):
        name = slot_to_name[i]
        name_bytes = name.encode('utf-8')
        init_val = prog.init[i]
        body.append(len(name_bytes))
        body.extend(name_bytes)
        body.extend(struct.pack(">I", init_val & 0xFFFFFFFF)) # Store as raw 32-bit int

    # Pack instructions
    body.extend(struct.pack(">I", len(prog.code)))
    for ins in prog.code:
        if ins.op not in OPS:
            raise RailError("E_INTERNAL", f"unknown opcode in serialization: {ins.op}")
        code_byte = OPS[ins.op].code
        arg_val = ins.arg if ins.arg is not None else 0
        body.extend(struct.pack(">B I", code_byte, arg_val & 0xFFFFFFFF))

    return bytes(body)


def deserialize_program(data):
    """Decodes raw .rbc bytes back into a runnable BinaryProgram."""
    if len(data) < 12:
        raise RailError("E_BINARY", "file too short to be a valid Railcode binary")

    magic, major, minor, capacity, num_symbols = struct.unpack_from(">4s BB I H", data, 0)

    if magic != MAGIC:
        raise RailError("E_BINARY", f"invalid magic bytes: {magic!r} (expected {MAGIC!r})")

    if major != ISA_MAJOR:
        raise RailError("E_BINARY", f"incompatible ISA major version: {major} (expected {ISA_MAJOR})")

    offset = 12
    slots = {}
    init_vals = []

    for i in range(num_symbols):
        if offset >= len(data):
            raise RailError("E_BINARY", "unexpected end of file while reading symbol table")
        name_len = data[offset]
        offset += 1

        if offset + name_len + 4 > len(data):
            raise RailError("E_BINARY", "truncated symbol record")

        name = data[offset:offset+name_len].decode('utf-8')
        offset += name_len

        init_val, = struct.unpack_from(">I", data, offset)
        # Sign-extend 32-bit unsigned back to signed 32-bit integer
        if init_val & 0x80000000:
            init_val -= 0x100000000
        offset += 4

        slots[name] = i
        init_vals.append(init_val)

    if offset + 4 > len(data):
        raise RailError("E_BINARY", "missing instruction count header")

    num_instructions, = struct.unpack_from(">I", data, offset)
    offset += 4

    code = []
    for pc in range(num_instructions):
        if offset + 5 > len(data):
            raise RailError("E_BINARY", f"truncated instruction stream at PC {pc}")

        code_byte, arg_val = struct.unpack_from(">B I", data, offset)
        offset += 5

        if code_byte not in OP_BY_CODE:
            raise RailError("E_BINARY", f"unknown opcode byte 0x{code_byte:02X} at PC {pc}")

        op = OP_BY_CODE[code_byte]

        # Sign-extend arg if needed (for negative literals or jump offsets)
        if arg_val & 0x80000000:
            arg_val -= 0x100000000

        # Pass None back if the operation takes no operand shape
        arg = arg_val if OPS[op].operand is not None else None
        code.append(Instruction(op, arg, row=pc))

    return BinaryProgram(
        code=tuple(code),
        slots=slots,
        init=tuple(init_vals),
        capacity=capacity
    )
