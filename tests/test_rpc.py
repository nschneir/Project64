"""Wire codec for the session monitor daemon RPC."""

import pytest

from c64lib.monitor import MonitorError, StopInfo
from c64lib.protocol import CP_EXEC, Checkpoint
from c64lib.rpc import decode_value, encode_value, raise_remote


def test_bytes_round_trip():
    assert decode_value(encode_value(b"\x00\xff\x2a")) == b"\x00\xff\x2a"


def test_checkpoint_round_trip():
    ck = Checkpoint(number=7, hit=True, start=0x1000, end=0x1000, stop=True,
                    enabled=True, op=CP_EXEC, temporary=False, hit_count=3,
                    ignore_count=0, has_condition=False, memspace=0)
    out = decode_value(encode_value(ck))
    assert out == ck and isinstance(out, Checkpoint)


def test_stopinfo_and_nested_round_trip():
    v = {"info": StopInfo(pc=0x040D, checkpoint=None), "list": [b"ab", 5, None]}
    out = decode_value(encode_value(v))
    assert out["info"] == StopInfo(pc=0x040D, checkpoint=None)
    assert out["list"] == [b"ab", 5, None]


def test_plain_values_pass_through():
    v = {"PC": 2061, "s": "x", "f": 1.5, "t": True}
    assert decode_value(encode_value(v)) == v


def test_raise_remote_maps_types():
    with pytest.raises(TimeoutError):
        raise_remote("TimeoutError", "t")
    with pytest.raises(ConnectionError):
        raise_remote("ConnectionError", "c")
    with pytest.raises(KeyError):
        raise_remote("KeyError", "'X'")
    with pytest.raises(ValueError):
        raise_remote("ValueError", "v")
    with pytest.raises(MonitorError):
        raise_remote("MonitorError", "VICE monitor error X for command Y")
    with pytest.raises(RuntimeError):
        raise_remote("WeirdError", "?")
