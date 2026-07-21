import pytest

from c64lib.protocol import (
    Command,
    ErrorCode,
    FrameDecoder,
    ProtocolError,
    Response,
    encode_command,
    memory_get_body,
    memory_set_body,
    parse_memory_get,
)


def test_encode_ping():
    # header: STX, api=2, body len (u32 LE), request id (u32 LE), command byte
    frame = encode_command(Command.PING, b"", request_id=0xAB)
    assert frame == bytes([0x02, 0x02, 0, 0, 0, 0, 0xAB, 0, 0, 0, 0x81])


def test_encode_with_body():
    body = memory_get_body(0x8000, 0x8003)
    frame = encode_command(Command.MEMORY_GET, body, request_id=1)
    # body: side_effects u8, start u16, end u16, memspace u8, bank u16
    assert body == bytes([0x00, 0x00, 0x80, 0x03, 0x80, 0x00, 0x00, 0x00])
    assert frame[:11] == bytes([0x02, 0x02, 8, 0, 0, 0, 1, 0, 0, 0, 0x01])
    assert frame[11:] == body


def test_memory_set_body():
    body = memory_set_body(0x8000, b"\xde\xad")
    assert body == bytes([0x00, 0x00, 0x80, 0x01, 0x80, 0x00, 0x00, 0x00]) + b"\xde\xad"


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
    data = _resp_frame(0x81, 0, 1, b"") + _resp_frame(0x62, 0, 0xFFFFFFFF, b"\x01\x04")
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
