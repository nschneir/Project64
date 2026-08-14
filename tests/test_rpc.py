"""Wire codec for the session monitor daemon RPC."""

import pytest

from c64lib.monitor import MonitorError, StopInfo
from c64lib.protocol import CP_EXEC, Checkpoint
from c64lib.rpc import (
    UNKNOWN_METHOD,
    UnknownDaemonMethod,
    decode_value,
    encode_value,
    error_payload,
    raise_remote,
)


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


# --- "the daemon has no such method", told apart from a real ValueError ------

def test_error_payload_flags_an_unknown_method_without_changing_its_type():
    """The structural half: a code field the client can branch on.

    `err` deliberately stays `ValueError` — the type an unknown method has
    always crossed as — so a client too old to read `code` behaves exactly as
    it does today rather than falling into raise_remote's RuntimeError catch-all.
    """
    payload = error_payload(UnknownDaemonMethod("unknown daemon method 'x'"))
    assert payload == {"err": "ValueError", "code": UNKNOWN_METHOD,
                       "msg": "unknown daemon method 'x'"}


def test_error_payload_leaves_every_other_exception_alone():
    assert error_payload(ValueError("bad frame")) == {"err": "ValueError",
                                                      "msg": "bad frame"}


def test_raise_remote_raises_its_own_type_for_the_unknown_method_code():
    with pytest.raises(UnknownDaemonMethod):
        raise_remote("ValueError", "unknown daemon method 'sid_log_at'",
                     UNKNOWN_METHOD)


def test_raise_remote_reads_a_pre_code_daemons_unknown_method_message():
    """The fallback exists FOR old daemons, so the old spelling — a bare
    ValueError whose message is the handshake — must still land as the typed
    error. This is the only place that string is matched."""
    with pytest.raises(UnknownDaemonMethod):
        raise_remote("ValueError", "unknown daemon method 'sid_log'")


def test_raise_remote_keeps_a_real_daemon_value_error_plain():
    """The bug this type exists for: a daemon-side ValueError from a method
    it DOES have (an out-of-range scheduled write) must not read as the
    old-daemon handshake, because the caller's fallback re-runs the window."""
    with pytest.raises(ValueError) as e:
        raise_remote("ValueError", "sid_log_at write $d404=999 is out of range")
    assert not isinstance(e.value, UnknownDaemonMethod)


def test_unknown_daemon_method_is_still_a_value_error():
    """Callers that have not adopted the type yet — `ops.run_until`'s blanket
    `except ValueError` — keep working unchanged."""
    assert issubclass(UnknownDaemonMethod, ValueError)
