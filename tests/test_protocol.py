import struct

import pytest

from c64lib.protocol import (
    CP_EXEC,
    CP_LOAD,
    CP_STORE,
    Command,
    ErrorCode,
    FrameDecoder,
    ProtocolError,
    Response,
    encode_command,
    memory_get_body,
    memory_set_body,
    op_name,
    parse_display_get,
    parse_memory_get,
    resource_set_body,
)


def test_encode_ping():
    # header: STX, api=2, body len (u32 LE), request id (u32 LE), command byte
    frame = encode_command(Command.PING, b"", request_id=0xAB)
    assert frame == bytes([0x02, 0x02, 0, 0, 0, 0, 0xAB, 0, 0, 0, 0x81])


def test_encode_with_body():
    body = memory_get_body(0x0400, 0x0403)
    frame = encode_command(Command.MEMORY_GET, body, request_id=1)
    # body: side_effects u8, start u16, end u16, memspace u8, bank u16
    assert body == bytes([0x00, 0x00, 0x04, 0x03, 0x04, 0x00, 0x00, 0x00])
    assert frame[:11] == bytes([0x02, 0x02, 8, 0, 0, 0, 1, 0, 0, 0, 0x01])
    assert frame[11:] == body


def _display_body(debug_w, debug_h, off_x, off_y, inner_w, inner_h, pixels):
    fields = struct.pack("<HHHHHHB", debug_w, debug_h, off_x, off_y,
                         inner_w, inner_h, 8)
    return (struct.pack("<I", len(fields)) + fields
            + struct.pack("<I", len(pixels)) + pixels)


def test_parse_display_get_full_keeps_border():
    # 4x4 frame, 2x2 inner area at (1,1); border pixels are 9, inner are 1..4
    pixels = bytes([9, 9, 9, 9,
                    9, 1, 2, 9,
                    9, 3, 4, 9,
                    9, 9, 9, 9])
    body = _display_body(4, 4, 1, 1, 2, 2, pixels)
    assert parse_display_get(body) == (2, 2, bytes([1, 2, 3, 4]))
    assert parse_display_get(body, full=True) == (4, 4, pixels)


def test_memory_set_body():
    body = memory_set_body(0x0400, b"\xde\xad")
    assert body == bytes([0x00, 0x00, 0x04, 0x01, 0x04, 0x00, 0x00, 0x00]) + b"\xde\xad"


def test_resource_set_body_string():
    # value-type 0 = string, then name-length, name, value-length, value
    body = resource_set_body("SoundRecordDeviceName", "wav")
    assert body == bytes([0, 21]) + b"SoundRecordDeviceName" + bytes([3]) + b"wav"


def test_resource_set_body_empty_string_sends_a_nul():
    """VICE rejects a zero-length value outright (INVALID_LENGTH) but reads
    the value as a C string, so one NUL byte is how you clear a resource —
    and clearing SoundRecordDeviceName is how recording is stopped."""
    body = resource_set_body("SoundRecordDeviceName", "")
    assert body == bytes([0, 21]) + b"SoundRecordDeviceName" + bytes([1]) + b"\x00"


def test_resource_set_body_int():
    # value-type 1 = int; the value is little-endian in a fixed 4-byte field
    body = resource_set_body("Speed", 90)
    assert body == bytes([1, 5]) + b"Speed" + bytes([4]) + b"\x5a\x00\x00\x00"


def test_resource_set_body_negative_int_is_twos_complement():
    """Several VICE integer resources use -1 as a sentinel. An unsigned pack
    raised OverflowError on every one of them, so the caller got a crash
    instead of a set."""
    body = resource_set_body("Speed", -1)
    assert body == bytes([1, 5]) + b"Speed" + bytes([4]) + b"\xff\xff\xff\xff"
    assert resource_set_body("Speed", -2)[-4:] == b"\xfe\xff\xff\xff"


def test_resource_set_body_non_negative_ints_are_unchanged_by_the_sign_fix():
    """Signedness is selected per value, so nothing that worked before moves:
    2**31 - 1 still fits, and the largest unsigned 4-byte value still does."""
    assert resource_set_body("X", 0)[-4:] == b"\x00\x00\x00\x00"
    assert resource_set_body("X", 2**31 - 1)[-4:] == b"\xff\xff\xff\x7f"
    assert resource_set_body("X", 2**32 - 1)[-4:] == b"\xff\xff\xff\xff"


def _resp_frame(rtype, err, rid, body):
    import struct

    return struct.pack("<BBIBBI", 0x02, 0x02, len(body), rtype, err, rid) + body


def test_decode_single_response():
    dec = FrameDecoder()
    frame = _resp_frame(0x81, 0x00, 7, b"")
    out = dec.feed(frame)
    assert out == [Response(0x81, 0x00, 7, b"")]


def test_decode_split_across_feeds():
    dec = FrameDecoder()
    frame = _resp_frame(0x01, 0x00, 3, bytes([2, 0]) + b"\xa0\xa1")
    assert dec.feed(frame[:5]) == []
    assert dec.feed(frame[5:]) == [Response(0x01, 0x00, 3, bytes([2, 0, 0xA0, 0xA1]))]


def test_decode_two_frames_one_feed():
    dec = FrameDecoder()
    data = _resp_frame(0x81, 0, 1, b"") + _resp_frame(0x62, 0, 0xFFFFFFFF, b"\x01\x08")
    out = dec.feed(data)
    assert len(out) == 2
    assert out[1].is_event  # request id 0xFFFFFFFF marks an unsolicited event


def test_decode_bad_stx_raises():
    dec = FrameDecoder()
    with pytest.raises(ProtocolError):
        dec.feed(b"\x00" + b"\x00" * 11)


def test_parse_memory_get():
    assert parse_memory_get(bytes([3, 0]) + b"abc") == b"abc"


def test_error_code_names():
    assert ErrorCode(0).name == "OK"
    assert ErrorCode(0x8F).name == "GENERAL_FAILURE"


def test_op_name_joins_the_known_bits_in_one_fixed_order():
    """The spelling both front ends report as `op`, so it is pinned here
    rather than in either of them: `exec`, `load`, `store`, in that order
    whatever order the bits arrive in."""
    assert op_name(CP_EXEC) == "exec"
    assert op_name(CP_LOAD) == "load"
    assert op_name(CP_STORE) == "store"
    assert op_name(CP_STORE | CP_LOAD) == "load|store"
    assert op_name(CP_EXEC | CP_LOAD | CP_STORE) == "exec|load|store"


def test_op_name_drops_unknown_bits_and_renders_an_empty_mask_as_empty():
    """The documented half VICE never exercises — which is why it is asserted
    here and not against a live monitor. An empty mask is `""` and a bit
    outside the three is dropped, rather than either becoming a placeholder
    `op` value no real checkpoint can produce."""
    assert op_name(0) == ""
    assert op_name(0x80) == ""
    assert op_name(CP_LOAD | 0x80) == "load"
