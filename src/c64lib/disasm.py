"""Table-driven 6502 disassembler. Pure — no emulator access here."""

from __future__ import annotations

_MODE_LEN = {
    "imp": 1, "acc": 1,
    "imm": 2, "zp": 2, "zpx": 2, "zpy": 2, "izx": 2, "izy": 2, "rel": 2,
    "abs": 3, "abx": 3, "aby": 3, "ind": 3,
}

OPCODES: dict[int, tuple[str, str]] = {
    0x00: ("brk", "imp"), 0x01: ("ora", "izx"), 0x05: ("ora", "zp"),
    0x06: ("asl", "zp"), 0x08: ("php", "imp"), 0x09: ("ora", "imm"),
    0x0A: ("asl", "acc"), 0x0D: ("ora", "abs"), 0x0E: ("asl", "abs"),
    0x10: ("bpl", "rel"), 0x11: ("ora", "izy"), 0x15: ("ora", "zpx"),
    0x16: ("asl", "zpx"), 0x18: ("clc", "imp"), 0x19: ("ora", "aby"),
    0x1D: ("ora", "abx"), 0x1E: ("asl", "abx"),
    0x20: ("jsr", "abs"), 0x21: ("and", "izx"), 0x24: ("bit", "zp"),
    0x25: ("and", "zp"), 0x26: ("rol", "zp"), 0x28: ("plp", "imp"),
    0x29: ("and", "imm"), 0x2A: ("rol", "acc"), 0x2C: ("bit", "abs"),
    0x2D: ("and", "abs"), 0x2E: ("rol", "abs"),
    0x30: ("bmi", "rel"), 0x31: ("and", "izy"), 0x35: ("and", "zpx"),
    0x36: ("rol", "zpx"), 0x38: ("sec", "imp"), 0x39: ("and", "aby"),
    0x3D: ("and", "abx"), 0x3E: ("rol", "abx"),
    0x40: ("rti", "imp"), 0x41: ("eor", "izx"), 0x45: ("eor", "zp"),
    0x46: ("lsr", "zp"), 0x48: ("pha", "imp"), 0x49: ("eor", "imm"),
    0x4A: ("lsr", "acc"), 0x4C: ("jmp", "abs"), 0x4D: ("eor", "abs"),
    0x4E: ("lsr", "abs"),
    0x50: ("bvc", "rel"), 0x51: ("eor", "izy"), 0x55: ("eor", "zpx"),
    0x56: ("lsr", "zpx"), 0x58: ("cli", "imp"), 0x59: ("eor", "aby"),
    0x5D: ("eor", "abx"), 0x5E: ("lsr", "abx"),
    0x60: ("rts", "imp"), 0x61: ("adc", "izx"), 0x65: ("adc", "zp"),
    0x66: ("ror", "zp"), 0x68: ("pla", "imp"), 0x69: ("adc", "imm"),
    0x6A: ("ror", "acc"), 0x6C: ("jmp", "ind"), 0x6D: ("adc", "abs"),
    0x6E: ("ror", "abs"),
    0x70: ("bvs", "rel"), 0x71: ("adc", "izy"), 0x75: ("adc", "zpx"),
    0x76: ("ror", "zpx"), 0x78: ("sei", "imp"), 0x79: ("adc", "aby"),
    0x7D: ("adc", "abx"), 0x7E: ("ror", "abx"),
    0x81: ("sta", "izx"), 0x84: ("sty", "zp"), 0x85: ("sta", "zp"),
    0x86: ("stx", "zp"), 0x88: ("dey", "imp"), 0x8A: ("txa", "imp"),
    0x8C: ("sty", "abs"), 0x8D: ("sta", "abs"), 0x8E: ("stx", "abs"),
    0x90: ("bcc", "rel"), 0x91: ("sta", "izy"), 0x94: ("sty", "zpx"),
    0x95: ("sta", "zpx"), 0x96: ("stx", "zpy"), 0x98: ("tya", "imp"),
    0x99: ("sta", "aby"), 0x9A: ("txs", "imp"), 0x9D: ("sta", "abx"),
    0xA0: ("ldy", "imm"), 0xA1: ("lda", "izx"), 0xA2: ("ldx", "imm"),
    0xA4: ("ldy", "zp"), 0xA5: ("lda", "zp"), 0xA6: ("ldx", "zp"),
    0xA8: ("tay", "imp"), 0xA9: ("lda", "imm"), 0xAA: ("tax", "imp"),
    0xAC: ("ldy", "abs"), 0xAD: ("lda", "abs"), 0xAE: ("ldx", "abs"),
    0xB0: ("bcs", "rel"), 0xB1: ("lda", "izy"), 0xB4: ("ldy", "zpx"),
    0xB5: ("lda", "zpx"), 0xB6: ("ldx", "zpy"), 0xB8: ("clv", "imp"),
    0xB9: ("lda", "aby"), 0xBA: ("tsx", "imp"), 0xBC: ("ldy", "abx"),
    0xBD: ("lda", "abx"), 0xBE: ("ldx", "aby"),
    0xC0: ("cpy", "imm"), 0xC1: ("cmp", "izx"), 0xC4: ("cpy", "zp"),
    0xC5: ("cmp", "zp"), 0xC6: ("dec", "zp"), 0xC8: ("iny", "imp"),
    0xC9: ("cmp", "imm"), 0xCA: ("dex", "imp"), 0xCC: ("cpy", "abs"),
    0xCD: ("cmp", "abs"), 0xCE: ("dec", "abs"),
    0xD0: ("bne", "rel"), 0xD1: ("cmp", "izy"), 0xD5: ("cmp", "zpx"),
    0xD6: ("dec", "zpx"), 0xD8: ("cld", "imp"), 0xD9: ("cmp", "aby"),
    0xDD: ("cmp", "abx"), 0xDE: ("dec", "abx"),
    0xE0: ("cpx", "imm"), 0xE1: ("sbc", "izx"), 0xE4: ("cpx", "zp"),
    0xE5: ("sbc", "zp"), 0xE6: ("inc", "zp"), 0xE8: ("inx", "imp"),
    0xE9: ("sbc", "imm"), 0xEA: ("nop", "imp"), 0xEC: ("cpx", "abs"),
    0xED: ("sbc", "abs"), 0xEE: ("inc", "abs"),
    0xF0: ("beq", "rel"), 0xF1: ("sbc", "izy"), 0xF5: ("sbc", "zpx"),
    0xF6: ("inc", "zpx"), 0xF8: ("sed", "imp"), 0xF9: ("sbc", "aby"),
    0xFD: ("sbc", "abx"), 0xFE: ("inc", "abx"),
}


def instruction_length(opcode: int) -> int:
    entry = OPCODES.get(opcode)
    return _MODE_LEN[entry[1]] if entry else 1


def _operand(mode: str, data: bytes, i: int, addr: int) -> tuple[str, int | None]:
    """Render the operand; return (text, target address for annotation)."""
    if mode == "imp":
        return "", None
    if mode == "acc":
        return "a", None
    if mode == "imm":
        return f"#${data[i + 1]:02x}", None
    if mode == "rel":
        target = (addr + 2 + int.from_bytes(data[i + 1 : i + 2], "little", signed=True)) & 0xFFFF
        return f"${target:04x}", target
    if mode in ("zp", "zpx", "zpy", "izx", "izy"):
        v = data[i + 1]
        text = {"zp": f"${v:02x}", "zpx": f"${v:02x},x", "zpy": f"${v:02x},y",
                "izx": f"(${v:02x},x)", "izy": f"(${v:02x}),y"}[mode]
        return text, v
    v = data[i + 1] | (data[i + 2] << 8)
    text = {"abs": f"${v:04x}", "abx": f"${v:04x},x", "aby": f"${v:04x},y",
            "ind": f"(${v:04x})"}[mode]
    return text, v


def disassemble(
    data: bytes, origin: int, labels: dict[str, int] | None = None
) -> list[str]:
    by_addr = {a: n for n, a in (labels or {}).items()}
    lines: list[str] = []
    i = 0
    while i < len(data):
        addr = (origin + i) & 0xFFFF
        if addr in by_addr:
            lines.append(f"{by_addr[addr]}:")
        opcode = data[i]
        entry = OPCODES.get(opcode)
        length = instruction_length(opcode)
        if i + length > len(data):
            length = len(data) - i
            entry = None
        raw = " ".join(f"{b:02x}" for b in data[i : i + length])
        if entry is None:
            lines.append(f"{addr:04x}  {raw:<9} .byte ${opcode:02x}")
            i += length
            continue
        mnemonic, mode = entry
        operand, target = _operand(mode, data, i, addr)
        note = f" ({by_addr[target]})" if target is not None and target in by_addr else ""
        text = f"{mnemonic} {operand}".rstrip()
        lines.append(f"{addr:04x}  {raw:<9} {text}{note}")
        i += length
    return lines
