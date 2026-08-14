"""Wire codec for the session monitor daemon (JSON-lines RPC).

One JSON object per line in each direction. Values JSON can't carry are
tagged: bytes -> {"__bytes__": base64}; Checkpoint / StopInfo -> tagged
field dicts. Exceptions cross as {"err": TypeName, "msg": str} — plus an
optional {"code": ...} for the one failure a client must be able to
recognize structurally — and re-raise client-side via raise_remote()."""

from __future__ import annotations

import base64
import json
from typing import Any

from .monitor import MonitorError, StopInfo
from .protocol import Checkpoint

PROTOCOL_VERSION = 1

#: The `code` an error line carries when the daemon has no such method. The
#: one machine-readable failure on this wire, because it is the one a client
#: must be able to tell from every other failure of the same call.
UNKNOWN_METHOD = "unknown_method"


class UnknownDaemonMethod(ValueError):
    """The daemon does not implement the method that was called.

    The old-daemon handshake: a client that grew a daemon-side loop
    (`run_until`, `profile_samples`, `sid_log`, `sid_log_at`) calls it first
    and falls back to its own loop on this — so it is the ONE remote failure
    a fallback may catch. It has its own type because falling back re-runs
    the work: a genuine ValueError from a method the daemon *does* have (an
    out-of-range scheduled write) used to be indistinguishable from this and
    bought a second helping of side effects on top of a refused first one.

    A ValueError subclass on purpose, and not only for compatibility with
    callers that have not adopted the type: an unknown method IS a bad
    argument to the dispatcher, which is what `daemon._dispatch` raises it
    as.
    """


def error_payload(exc: BaseException) -> dict:
    """The wire form of a daemon-side exception: `err`, `msg`, and `code`
    where there is one.

    `err` stays `"ValueError"` for `UnknownDaemonMethod` — true of the type,
    and it is what an unknown method has always crossed as. A client too old
    to read `code` therefore behaves exactly as it does today (the message
    match below is its whole discrimination) instead of falling into
    `raise_remote`'s RuntimeError catch-all, which would break the very
    fallback this code exists to make reliable.
    """
    if isinstance(exc, UnknownDaemonMethod):
        return {"err": "ValueError", "code": UNKNOWN_METHOD, "msg": str(exc)}
    return {"err": type(exc).__name__, "msg": str(exc)}

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


# `-> Any` is deliberate, the same call as `DaemonMonitorClient._call`: the
# return type is chosen by the tag inside `v` at runtime — bytes for
# `__bytes__`, a Checkpoint, a StopInfo, or a container of any of those,
# nested arbitrarily. Spelled honestly it is a recursive union, and pyright
# expands it at every call site into a type no caller can use: it is what made
# `daemon.py`'s two `_dispatch` arguments and all of `tests/test_rpc.py`
# unusable. Callers know which method they asked for and re-narrow themselves.
def decode_value(v) -> Any:
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


def raise_remote(name: str, msg: str, code: str | None = None):
    """Re-raise a daemon-side exception as the closest local type."""
    if code == UNKNOWN_METHOD or (
            # The pre-`code` spelling, and the reason this string match is
            # here rather than at a caller: the fallback exists FOR daemons
            # older than the code, so their bare ValueError has to arrive as
            # the typed error too. One place matches it — every caller sees
            # the type. Retire this arm only once no daemon in the wild
            # predates `code`.
            name == "ValueError" and msg.startswith("unknown daemon method")):
        raise UnknownDaemonMethod(msg)
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
