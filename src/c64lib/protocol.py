"""Pure encode/decode for the VICE binary monitor protocol, API version 2.

Reference: https://vice-emu.sourceforge.io/vice_13.html  (section: binary monitor)
No sockets here — that lives in c64lib.monitor.
"""

from __future__ import annotations

import enum
import struct
from dataclasses import dataclass

STX = 0x02
API_VERSION = 0x02
EVENT_REQUEST_ID = 0xFFFFFFFF
MEMSPACE_MAIN = 0

_CMD_HEADER = struct.Struct("<BBIIB")    # stx, api, body_len, request_id, command
_RESP_HEADER = struct.Struct("<BBIBBI")  # stx, api, body_len, resp_type, error, request_id
_MEM_HEADER = struct.Struct("<BHHBH")    # side_effects, start, end, memspace, bank


class Command(enum.IntEnum):
    MEMORY_GET = 0x01
    MEMORY_SET = 0x02
    CHECKPOINT_GET = 0x11
    CHECKPOINT_SET = 0x12
    CHECKPOINT_DELETE = 0x13
    CHECKPOINT_LIST = 0x14
    CHECKPOINT_TOGGLE = 0x15
    CONDITION_SET = 0x22
    REGISTERS_GET = 0x31
    REGISTERS_SET = 0x32
    DUMP = 0x41
    UNDUMP = 0x42
    RESOURCE_GET = 0x51
    RESOURCE_SET = 0x52
    ADVANCE_INSTRUCTIONS = 0x71
    KEYBOARD_FEED = 0x72
    EXECUTE_UNTIL_RETURN = 0x73
    PING = 0x81
    BANKS_AVAILABLE = 0x82
    REGISTERS_AVAILABLE = 0x83
    DISPLAY_GET = 0x84
    VICE_INFO = 0x85
    PALETTE_GET = 0x91
    EXIT = 0xAA
    QUIT = 0xBB
    RESET = 0xCC
    AUTOSTART = 0xDD


class ResponseType(enum.IntEnum):
    """Unsolicited event types (direct responses reuse the Command value)."""

    JAM = 0x61
    STOPPED = 0x62
    RESUMED = 0x63


class ErrorCode(enum.IntEnum):
    OK = 0x00
    OBJECT_MISSING = 0x01
    INVALID_MEMSPACE = 0x02
    INVALID_LENGTH = 0x80
    INVALID_PARAMETER = 0x81
    INVALID_API_VERSION = 0x82
    INVALID_COMMAND_TYPE = 0x83
    GENERAL_FAILURE = 0x8F


class ProtocolError(Exception):
    pass


@dataclass(frozen=True)
class Response:
    response_type: int
    error_code: int
    request_id: int
    body: bytes

    @property
    def is_event(self) -> bool:
        return self.request_id == EVENT_REQUEST_ID


def encode_command(command: int, body: bytes = b"", request_id: int = 0) -> bytes:
    return _CMD_HEADER.pack(STX, API_VERSION, len(body), request_id, command) + body


class FrameDecoder:
    """Incremental decoder: feed() raw bytes, get back complete Responses."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Response]:
        self._buf += data
        out: list[Response] = []
        while len(self._buf) >= _RESP_HEADER.size:
            stx, api, body_len, rtype, err, rid = _RESP_HEADER.unpack_from(self._buf)
            if stx != STX:
                raise ProtocolError(f"bad frame start byte: {stx:#04x}")
            total = _RESP_HEADER.size + body_len
            if len(self._buf) < total:
                break
            body = bytes(self._buf[_RESP_HEADER.size : total])
            del self._buf[:total]
            out.append(Response(rtype, err, rid, body))
        return out


def memory_get_body(
    start: int, end: int, memspace: int = MEMSPACE_MAIN, bank: int = 0,
    side_effects: bool = False,
) -> bytes:
    return _MEM_HEADER.pack(int(side_effects), start, end, memspace, bank)


def memory_set_body(
    start: int, data: bytes, memspace: int = MEMSPACE_MAIN, bank: int = 0,
    side_effects: bool = False,
) -> bytes:
    end = start + len(data) - 1
    return _MEM_HEADER.pack(int(side_effects), start, end, memspace, bank) + data


def parse_memory_get(body: bytes) -> bytes:
    (length,) = struct.unpack_from("<H", body)
    return body[2 : 2 + length]


def parse_registers_available(body: bytes) -> dict[int, str]:
    (count,) = struct.unpack_from("<H", body)
    out: dict[int, str] = {}
    off = 2
    for _ in range(count):
        item_size = body[off]
        reg_id = body[off + 1]
        name_len = body[off + 3]
        name = body[off + 4 : off + 4 + name_len].decode("ascii")
        out[reg_id] = name
        off += 1 + item_size
    return out


def parse_registers_get(body: bytes) -> dict[int, int]:
    (count,) = struct.unpack_from("<H", body)
    out: dict[int, int] = {}
    off = 2
    for _ in range(count):
        item_size = body[off]
        reg_id = body[off + 1]
        (value,) = struct.unpack_from("<H", body, off + 2)
        out[reg_id] = value
        off += 1 + item_size
    return out


def registers_set_body(values: dict[int, int], memspace: int = MEMSPACE_MAIN) -> bytes:
    out = struct.pack("<BH", memspace, len(values))
    for reg_id, value in values.items():
        out += struct.pack("<BBH", 3, reg_id, value)
    return out


def parse_display_get(body: bytes, full: bool = False) -> tuple[int, int, bytes]:
    """Decode a DISPLAY_GET response. By default returns just the inner
    screen area (320x200 on a C64); with full=True returns the whole
    emulated frame, borders included."""
    (fields_len,) = struct.unpack_from("<I", body)
    debug_w, debug_h, off_x, off_y, inner_w, inner_h, _bpp = struct.unpack_from(
        "<HHHHHHB", body, 4
    )
    buf_off = 4 + fields_len
    (buf_len,) = struct.unpack_from("<I", body, buf_off)
    pixels = body[buf_off + 4 : buf_off + 4 + buf_len]
    if full:
        return debug_w, debug_h, pixels[: debug_w * debug_h]
    rows = []
    for y in range(off_y, off_y + inner_h):
        row_start = y * debug_w + off_x
        rows.append(pixels[row_start : row_start + inner_w])
    return inner_w, inner_h, b"".join(rows)


def parse_palette_get(body: bytes) -> list[tuple[int, int, int]]:
    (count,) = struct.unpack_from("<H", body)
    out: list[tuple[int, int, int]] = []
    off = 2
    for _ in range(count):
        item_size = body[off]
        r, g, b = body[off + 1], body[off + 2], body[off + 3]
        out.append((r, g, b))
        off += 1 + item_size
    return out


CP_LOAD = 0x01
CP_STORE = 0x02
CP_EXEC = 0x04


def op_name(op: int) -> str:
    """Render a checkpoint op mask as `exec`, `load`, `store` joined by `|`.

    The one spelling both front ends report as the `op` key, so `c64 break
    list --json` and `c64_break_list` cannot drift into two types again.
    Bits outside CP_EXEC/CP_LOAD/CP_STORE are dropped and an empty mask
    renders as `""` — VICE never reports either, and inventing a placeholder
    here would put a value in the payload that no real checkpoint produces.
    """
    parts = []
    if op & CP_EXEC:
        parts.append("exec")
    if op & CP_LOAD:
        parts.append("load")
    if op & CP_STORE:
        parts.append("store")
    return "|".join(parts)


_CKPT_INFO = struct.Struct("<IBHHBBBBIIBB")


@dataclass(frozen=True)
class Checkpoint:
    number: int
    hit: bool
    start: int
    end: int
    stop: bool
    enabled: bool
    op: int
    temporary: bool
    hit_count: int
    ignore_count: int
    has_condition: bool
    memspace: int


def checkpoint_set_body(
    start: int, end: int, *, op: int, stop: bool = True,
    enabled: bool = True, temporary: bool = False,
) -> bytes:
    return struct.pack(
        "<HHBBBB", start, end, int(stop), int(enabled), op, int(temporary)
    )


def parse_checkpoint(body: bytes) -> Checkpoint:
    (num, hit, start, end, stop, enabled, op, temp,
     hits, ignores, has_cond, memspace) = _CKPT_INFO.unpack_from(body)
    return Checkpoint(
        number=num, hit=bool(hit), start=start, end=end, stop=bool(stop),
        enabled=bool(enabled), op=op, temporary=bool(temp), hit_count=hits,
        ignore_count=ignores, has_condition=bool(has_cond), memspace=memspace,
    )


def checkpoint_delete_body(number: int) -> bytes:
    return struct.pack("<I", number)


def checkpoint_toggle_body(number: int, enabled: bool) -> bytes:
    return struct.pack("<IB", number, int(enabled))


def condition_set_body(number: int, expr: str) -> bytes:
    raw = expr.encode("ascii")
    return struct.pack("<IB", number, len(raw)) + raw


def advance_body(count: int, step_over: bool) -> bytes:
    return struct.pack("<BH", int(step_over), count)


#: The longest a resource name or string value may be on this wire: both are
#: length-prefixed with ONE byte. Probed against x64sc 3.10 on 2026-08-14 —
#: 200, 254 and 255-byte values all set and read back byte-identical — so 255
#: is the protocol's ceiling and not a guess about VICE's own storage.
RESOURCE_MAX_BYTES = 255


def _resource_bytes(what: str, text: str, encoding: str) -> bytes:
    """One length-prefixed field's payload, or a ValueError a user can act on.

    Both failures used to escape as encoder internals — `UnicodeEncodeError`
    from `str.encode`, or `bytes([309])`'s bare "bytes must be in range" —
    naming neither the resource nor the value, and reaching a caller that had
    already taken its session off warp to arm a recorder.
    """
    try:
        raw = text.encode(encoding)
    except UnicodeEncodeError as e:
        raise ValueError(
            f"{what} {text!r} cannot be encoded as {encoding}: "
            f"{e.reason} at position {e.start}") from e
    if len(raw) > RESOURCE_MAX_BYTES:
        raise ValueError(
            f"{what} {text!r} is {len(raw)} bytes, over the "
            f"{RESOURCE_MAX_BYTES} the binary monitor can carry: the field is "
            f"length-prefixed with one byte. Use a shorter path or name")
    return raw


def check_resource_value(name: str, value: str | int) -> None:
    """Raise what `resource_set_body` would raise, without sending anything.

    For a caller that must find an unusable value BEFORE it pins state on the
    outcome — `audio.pinned_record_start` takes the machine off warp and only
    then arms the recorder on the path it was given. Deliberately the encoder
    itself and not a second copy of the rule: nothing can pass here and fail
    on the wire.
    """
    resource_set_body(name, value)


def resource_get_body(name: str) -> bytes:
    raw = _resource_bytes("resource name", name, "ascii")
    return bytes([len(raw)]) + raw


def resource_set_body(name: str, value: str | int) -> bytes:
    """Value type (0 = string, 1 = integer), then the name, then the value.

    The type byte leads, unlike RESOURCE_GET's body, which is bare name —
    verified against x64sc 3.10 on 2026-08-03: a trailing type byte earns
    INVALID_LENGTH. Integers travel little-endian, and VICE reads whatever
    width it is given, so a fixed 4 bytes needs no per-resource size table.

    Integers are encoded SIGNED when negative: several VICE integer resources
    use `-1` as a sentinel, and an unsigned 4-byte pack raises OverflowError
    on every one of them. Two's complement leaves every non-negative value
    byte-identical to what an unsigned pack produced.

    An empty string travels as a single NUL: VICE rejects a zero-length value
    with INVALID_LENGTH, but reads the value as a C string, so one NUL clears
    the resource (that is how `SoundRecordDeviceName` stops a recording).

    String values travel as UTF-8, not ASCII. VICE 3.10 takes the value as
    raw bytes and hands the same bytes back — probed 2026-08-14 on
    `SoundRecordDeviceArg` with `/Users/josé/out/capture.wav` and
    `/tmp/音/capture.wav`, both byte-identical through RESOURCE_SET /
    RESOURCE_GET, and a recorder armed on the second created the file. So an
    accented character in a capture path is a working capture; it used to be
    a `UnicodeEncodeError` traceback from a session already off warp. The
    name stays ASCII — every VICE resource name is."""
    raw = _resource_bytes("resource name", name, "ascii")
    if isinstance(value, int):
        vtype, encoded = 1, value.to_bytes(4, "little", signed=value < 0)
    else:
        vtype = 0
        encoded = _resource_bytes(f"{name} value", value, "utf-8") or b"\x00"
    return bytes([vtype, len(raw)]) + raw + bytes([len(encoded)]) + encoded


def parse_resource(body: bytes) -> str | int:
    rtype, length = body[0], body[1]
    value = body[2 : 2 + length]
    if rtype == 0:
        # UTF-8, matching what `resource_set_body` sends; `replace` rather
        # than a raise because this is a READBACK — a resource set outside
        # this tree (a VICE command line, a vicerc) can hold any bytes, and
        # losing `resource_get` to a decode error would take `_TextMonitor`'s
        # `MonitorServer` probe with it.
        return value.decode("utf-8", "replace")
    return int.from_bytes(value, "little")
