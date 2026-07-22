from unittest.mock import Mock

from c64lib.sprites import (
    C64_PALETTE,
    SpriteState,
    read_sprite_block,
    read_sprite_states,
    sprite_ascii,
)


def _mock_mon(vic: bytes, pointers: bytes):
    mon = Mock()
    mon.memory_read.side_effect = lambda a, n: {
        0xD000: vic[:n], 0x07F8: pointers[:n]}[a]
    return mon


def _vic(**over):
    v = bytearray(0x2F)
    v[0x00], v[0x01] = 100, 120          # sprite 0 x/y
    v[0x02], v[0x03] = 44, 55            # sprite 1 x/y
    v[0x10] = 0b00000010                 # sprite 1 x MSB set
    v[0x15] = 0b00000011                 # sprites 0+1 enabled
    v[0x1C] = 0b00000010                 # sprite 1 multicolor
    v[0x17] = 0b00000001                 # sprite 0 expand-y
    v[0x1B] = 0b00000001                 # sprite 0 behind text
    v[0x20], v[0x21] = 14, 6             # border, background
    v[0x25], v[0x26] = 10, 11            # mc shared colors
    v[0x27], v[0x28] = 7, 2              # sprite 0/1 colors
    for k, val in over.items():
        v[k] = val
    return bytes(v)


def test_palette_shape():
    assert len(C64_PALETTE) == 16
    assert C64_PALETTE[0] == (0, 0, 0)          # black
    assert C64_PALETTE[1] == (255, 255, 255)    # white


def test_read_sprite_states_decodes_registers():
    mon = _mock_mon(_vic(), bytes([13, 0x80, 0, 0, 0, 0, 0, 0]))
    states, shared = read_sprite_states(mon, 0x0400)
    s0, s1 = states[0], states[1]
    assert s0 == SpriteState(index=0, enabled=True, x=100, y=120, pointer=13,
                             block_addr=13 * 64, color=7, multicolor=False,
                             expand_x=False, expand_y=True, behind_text=True)
    assert s1.x == 44 + 256 and s1.multicolor and s1.color == 2
    assert s1.block_addr == 0x80 * 64
    assert states[2].enabled is False
    assert shared == {"mc_color1": 10, "mc_color2": 11,
                      "background": 6, "border": 14}


def test_read_sprite_states_uses_live_screen_base():
    mon = Mock()
    vic = _vic()
    mon.memory_read.side_effect = lambda a, n: {
        0xD000: vic[:n], 0x0FF8: bytes([9] * 8)}[a]
    states, _ = read_sprite_states(mon, 0x0C00)
    assert states[0].pointer == 9


def test_read_sprite_block_reads_63_bytes():
    mon = Mock()
    mon.memory_read.return_value = bytes(range(63))
    assert read_sprite_block(mon, 0x0340) == bytes(range(63))
    mon.memory_read.assert_called_once_with(0x0340, 63)


def test_sprite_ascii_hires():
    data = bytes([0b10000000, 0, 0b00000001] + [0] * 60)  # corners of row 0
    rows = sprite_ascii(data, multicolor=False)
    assert len(rows) == 21 and all(len(r) == 24 for r in rows)
    assert rows[0][0] == "█" and rows[0][23] == "█"
    assert rows[0][1:23] == "·" * 22 and rows[1] == "·" * 24


def test_sprite_ascii_multicolor_pairs():
    data = bytes([0b00011011] + [0] * 62)   # pairs 00 01 10 11 in row 0
    rows = sprite_ascii(data, multicolor=True)
    assert len(rows) == 21 and all(len(r) == 24 for r in rows)
    assert rows[0][:8] == "··▒▒██▓▓"
