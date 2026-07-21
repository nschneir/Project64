import struct

from c64lib.protocol import (
    CP_EXEC,
    CP_LOAD,
    CP_STORE,
    Checkpoint,
    advance_body,
    checkpoint_delete_body,
    checkpoint_set_body,
    checkpoint_toggle_body,
    condition_set_body,
    parse_checkpoint,
)


def test_checkpoint_set_body():
    body = checkpoint_set_body(0x040D, 0x040D, op=CP_EXEC)
    assert body == struct.pack("<HHBBBB", 0x040D, 0x040D, 1, 1, 4, 0)
    body = checkpoint_set_body(0x8000, 0x83E7, op=CP_LOAD | CP_STORE, stop=False, temporary=True)
    assert body == struct.pack("<HHBBBB", 0x8000, 0x83E7, 0, 1, 3, 1)


def test_parse_checkpoint_roundtrip():
    raw = struct.pack("<IBHHBBBBIIBB", 7, 1, 0x040D, 0x040D, 1, 1, 4, 0, 3, 0, 1, 0)
    ck = parse_checkpoint(raw)
    assert ck == Checkpoint(
        number=7, hit=True, start=0x040D, end=0x040D, stop=True, enabled=True,
        op=CP_EXEC, temporary=False, hit_count=3, ignore_count=0,
        has_condition=True, memspace=0,
    )


def test_small_bodies():
    assert checkpoint_delete_body(7) == struct.pack("<I", 7)
    assert checkpoint_toggle_body(7, False) == struct.pack("<IB", 7, 0)
    assert condition_set_body(7, "A != 255") == struct.pack("<IB", 7, 8) + b"A != 255"
    assert advance_body(2, step_over=False) == struct.pack("<BH", 0, 2)
    assert advance_body(1, step_over=True) == struct.pack("<BH", 1, 1)
