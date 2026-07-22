from c64lib.disasm import OPCODES, disassemble, instruction_length


def test_opcode_table_size_and_spotchecks():
    assert len(OPCODES) == 151          # all documented 6502 opcodes
    assert OPCODES[0x4C] == ("jmp", "abs")
    assert OPCODES[0x6C] == ("jmp", "ind")
    assert OPCODES[0xA9] == ("lda", "imm")
    assert OPCODES[0xB1] == ("lda", "izy")
    assert OPCODES[0x91] == ("sta", "izy")
    assert OPCODES[0xD0] == ("bne", "rel")
    assert OPCODES[0xEA] == ("nop", "imp")
    assert OPCODES[0x0A] == ("asl", "acc")
    assert OPCODES[0x96] == ("stx", "zpy")
    assert OPCODES[0xE8] == ("inx", "imp")


def test_instruction_lengths():
    assert instruction_length(0xEA) == 1   # nop
    assert instruction_length(0xA9) == 2   # lda #imm
    assert instruction_length(0x4C) == 3   # jmp abs
    assert instruction_length(0x02) == 1   # undocumented -> .byte


def test_disassemble_known_rom_sequence():
    # verified live: $FFD2 on the BASIC4 kernal is 4C 66 F2 = jmp $f266
    # line format: addr, 2 spaces, bytes padded to 9, 1 space, text
    lines = disassemble(b"\x4c\x66\xf2", 0xFFD2)
    assert lines == ["ffd2  4c 66 f2  jmp $f266"]


def test_disassemble_labels_and_annotation():
    labels = {"CHROUT": 0xFFD2, "chrprint": 0xF266}
    lines = disassemble(b"\x4c\x66\xf2", 0xFFD2, labels)
    assert lines == ["CHROUT:", "ffd2  4c 66 f2  jmp $f266 (chrprint)"]


def test_disassemble_modes_and_branches():
    # ldx #$00 / lda $041b,x / beq +4 / jsr $ffd2 / .byte $02
    data = bytes([0xA2, 0x00, 0xBD, 0x1B, 0x04, 0xF0, 0x04, 0x20, 0xD2, 0xFF, 0x02])
    lines = disassemble(data, 0x040D)
    assert lines[0].endswith("ldx #$00")
    assert lines[1].endswith("lda $041b,x")
    # beq is at $0412; branch base is PC-after-instruction ($0414) + 4 = $0418
    assert lines[2].endswith("beq $0418")
    assert lines[3].endswith("jsr $ffd2")
    assert lines[4].endswith(".byte $02")


def test_disassemble_indirect_and_indexed_indirect():
    lines = disassemble(bytes([0x6C, 0x00, 0x02, 0xA1, 0x40, 0x51, 0x41]), 0x1000)
    assert lines[0].endswith("jmp ($0200)")
    assert lines[1].endswith("lda ($40,x)")
    assert lines[2].endswith("eor ($41),y")


def test_implied_and_accumulator_modes():
    lines = disassemble(b"\xea\x0a", 0xC000, {})    # NOP ; ASL A
    assert "nop" in lines[0].lower()
    assert lines[1].lower().rstrip().endswith(" a")


def test_truncated_instruction_at_end():
    lines = disassemble(b"\x4c\x00", 0xC000, {})    # JMP missing its high byte
    assert len(lines) == 1                          # rendered as data, no crash
