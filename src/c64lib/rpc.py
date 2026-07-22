"""Wire codec for the session monitor daemon (JSON-lines RPC).

One JSON object per line in each direction. Values JSON can't carry are
tagged: bytes -> {"__bytes__": base64}; Checkpoint / StopInfo -> tagged
field dicts. Exceptions cross as {"err": TypeName, "msg": str} and
re-raise client-side via raise_remote()."""

from __future__ import annotations

import base64
import json

from .monitor import MonitorError, StopInfo
from .protocol import Checkpoint

PROTOCOL_VERSION = 1

_CHECKPOINT_FIELDS = ("number", "hit", "start", "end", "stop", "enabled",
                      "op", "temporary", "hit_count", "ignore_count",
                      "has_condition", "memspace")


def encode_value(v):
    if isinstance(v, bytes):
        return {"__bytes__": base64.b64encode(v).decode()}
    if isinstance(v, Checkpoint):
        return {"__checkpoint__": {f: getattr(v, f) for f in _CHECKPOINT_FIELDS}}
    if isinstance(v, StopInfo):
        return {"__stopinfo__": {"pc": v.pc, "checkpoint": v.checkpoint}}
    if isinstance(v, (list, tuple)):
        return [encode_value(x) for x in v]
    if isinstance(v, dict):
        return {k: encode_value(x) for k, x in v.items()}
    return v


def decode_value(v):
    if isinstance(v, dict):
        if "__bytes__" in v:
            return base64.b64decode(v["__bytes__"])
        if "__checkpoint__" in v:
            return Checkpoint(**v["__checkpoint__"])
        if "__stopinfo__" in v:
            return StopInfo(**v["__stopinfo__"])
        return {k: decode_value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [decode_value(x) for x in v]
    return v


def send_line(f, obj: dict) -> None:
    f.write((json.dumps(obj, separators=(",", ":")) + "\n").encode())
    f.flush()


def raise_remote(name: str, msg: str):
    """Re-raise a daemon-side exception as the closest local type."""
    if name == "TimeoutError":
        raise TimeoutError(msg)
    if name == "ConnectionError":
        raise ConnectionError(msg)
    if name == "KeyError":
        raise KeyError(msg)
    if name == "ValueError":
        raise ValueError(msg)
    if name == "MonitorError":
        # MonitorError's ctor wants (command, error_code); rebuild by hand.
        e = MonitorError.__new__(MonitorError)
        Exception.__init__(e, msg)
        e.error_code = -1
        raise e
    raise RuntimeError(f"{name}: {msg}")
