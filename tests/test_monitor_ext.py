import struct

import pytest

from c64lib.monitor import MonitorClient
from c64lib.protocol import (
    Command,
    parse_display_get,
    parse_palette_get,
    parse_registers_available,
    parse_registers_get,
    registers_set_body,
)
from tests.fake_vice import FakeVice, resp_frame


def _avail_body():
    # two registers: id 3 = "PC" (16 bits), id 0 = "A" (8 bits)
    def item(rid, bits, name):
        n = name.encode()
        return bytes([3 + len(n), rid, bits, len(n)]) + n

    items = item(3, 16, "PC") + item(0, 8, "A")
    return struct.pack("<H", 2) + items


def _regs_body():
    items = bytes([3, 3]) + struct.pack("<H", 0x0401) + bytes([3, 0]) + struct.pack("<H", 0x2A)
    return struct.pack("<H", 2) + items


def test_parse_registers_available():
    assert parse_registers_available(_avail_body()) == {3: "PC", 0: "A"}


def test_parse_registers_get():
    assert parse_registers_get(_regs_body()) == {3: 0x0401, 0: 0x2A}


def test_registers_set_body():
    body = registers_set_body({3: 0x1234})
    assert body == bytes([0]) + struct.pack("<H", 1) + bytes([3, 3]) + struct.pack("<H", 0x1234)


def test_parse_display_get_crops_to_inner():
    # debug buffer 4x2, inner rect 2x1 at offset (1,1)
    fields = struct.pack("<HHHHHHB", 4, 2, 1, 1, 2, 1, 8)
    pixels = bytes(range(8))  # 4x2
    body = struct.pack("<I", len(fields)) + fields + struct.pack("<I", len(pixels)) + pixels
    w, h, data = parse_display_get(body)
    assert (w, h) == (2, 1)
    assert data == bytes([5, 6])  # row 1, cols 1..2


def test_parse_palette_get():
    body = struct.pack("<H", 2) + bytes([3, 0, 0, 0]) + bytes([3, 0, 255, 0])
    assert parse_palette_get(body) == [(0, 0, 0), (0, 255, 0)]


def _client(fake):
    c = MonitorClient(port=fake.port, timeout=2.0)
    c.connect(deadline=2.0)
    return c


def test_registers_by_name_and_set():
    handlers = {
        Command.REGISTERS_AVAILABLE: lambda b, rid: [resp_frame(0x83, 0, rid, _avail_body())],
        Command.REGISTERS_GET: lambda b, rid: [resp_frame(0x31, 0, rid, _regs_body())],
        Command.REGISTERS_SET: lambda b, rid: [resp_frame(0x32, 0, rid, _regs_body())],
    }
    fake = FakeVice(handlers)
    with _client(fake) as c:
        assert c.registers() == {"PC": 0x0401, "A": 0x2A}
        c.set_register("pc", 0x2000)
        with pytest.raises(KeyError):
            c.set_register("BOGUS", 1)
    set_cmd = [r for r in fake.received if r[0] == Command.REGISTERS_SET]
    assert set_cmd[0][1] == registers_set_body({3: 0x2000})


def test_keyboard_feed_body():
    fake = FakeVice({Command.KEYBOARD_FEED: lambda b, rid: [resp_frame(0x72, 0, rid)]})
    with _client(fake) as c:
        c.keyboard_feed(b"RUN\r")
    assert fake.received[0][1] == bytes([4]) + b"RUN\r"


def test_reset_hard_flag():
    fake = FakeVice({Command.RESET: lambda b, rid: [resp_frame(0xCC, 0, rid)]})
    with _client(fake) as c:
        c.reset(hard=True)
    assert fake.received[0][1] == b"\x01"


def test_autostart_body():
    fake = FakeVice({Command.AUTOSTART: lambda b, rid: [resp_frame(0xDD, 0, rid)]})
    with _client(fake) as c:
        c.autostart("/tmp/demo.prg", run=True)
    path = b"/tmp/demo.prg"
    assert fake.received[0][1] == struct.pack("<BHB", 1, 0, len(path)) + path


def test_resource_get_string_and_int():
    def handle(b, rid):
        name = b[1 : 1 + b[0]].decode()
        if name == "BasicName":
            val = b"basic-4.bin"
            return [resp_frame(0x51, 0, rid, bytes([0, len(val)]) + val)]
        return [resp_frame(0x51, 0, rid, bytes([1, 4]) + (2031).to_bytes(4, "little"))]

    fake = FakeVice({Command.RESOURCE_GET: handle})
    with _client(fake) as c:
        assert c.resource_get("BasicName") == "basic-4.bin"
        assert c.resource_get("Drive8Type") == 2031
