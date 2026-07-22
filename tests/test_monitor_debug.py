import struct

from c64lib.monitor import MonitorClient, StopInfo
from c64lib.protocol import CP_EXEC, Command, checkpoint_set_body
from tests.fake_vice import FakeVice, resp_frame


def _client(fake):
    c = MonitorClient(port=fake.port, timeout=2.0)
    c.connect(deadline=2.0)
    return c


def _info_body(num, hit=0, start=0x040D, hits=0):
    return struct.pack("<IBHHBBBBIIBB", num, hit, start, start, 1, 1, 4, 0, hits, 0, 0, 0)


def test_checkpoint_set_and_parse():
    fake = FakeVice({
        Command.CHECKPOINT_SET: lambda b, rid: [resp_frame(0x11, 0, rid, _info_body(3))],
    })
    with _client(fake) as c:
        ck = c.checkpoint_set(0x040D)
    assert (ck.number, ck.start, ck.op) == (3, 0x040D, CP_EXEC)
    assert fake.received[0][1] == checkpoint_set_body(0x040D, 0x040D, op=CP_EXEC)


def test_checkpoint_list_collects_same_rid_infos():
    def handle(b, rid):
        return [
            resp_frame(0x11, 0, rid, _info_body(1)),
            resp_frame(0x11, 0, rid, _info_body(2, start=0x0400)),
            resp_frame(0x14, 0, rid, struct.pack("<I", 2)),
        ]

    fake = FakeVice({Command.CHECKPOINT_LIST: handle})
    with _client(fake) as c:
        cks = c.checkpoint_list()
    assert [ck.number for ck in cks] == [1, 2]
    assert cks[1].start == 0x0400


def test_step_advances_then_reads_registers():
    regs_avail = struct.pack("<H", 1) + bytes([4, 3, 16, 2]) + b"PC"
    regs_val = struct.pack("<H", 1) + bytes([3, 3]) + struct.pack("<H", 0x0412)
    fake = FakeVice({
        Command.ADVANCE_INSTRUCTIONS: lambda b, rid: [resp_frame(0x71, 0, rid)],
        Command.REGISTERS_AVAILABLE: lambda b, rid: [resp_frame(0x83, 0, rid, regs_avail)],
        Command.REGISTERS_GET: lambda b, rid: [resp_frame(0x31, 0, rid, regs_val)],
    })
    with _client(fake) as c:
        regs = c.step(2)
    assert regs == {"PC": 0x0412}
    adv = [r for r in fake.received if r[0] == Command.ADVANCE_INSTRUCTIONS]
    assert adv[0][1] == struct.pack("<BH", 0, 2)


def test_wait_for_stop_consumes_hit_and_stopped_events():
    def handle_exit(b, rid):
        return [
            resp_frame(0xAA, 0, rid),
            resp_frame(0x11, 0, 0xFFFFFFFF, _info_body(5, hit=1, hits=1)),
            resp_frame(0x62, 0, 0xFFFFFFFF, struct.pack("<H", 0x040D)),
        ]

    fake = FakeVice({Command.EXIT: handle_exit})
    with _client(fake) as c:
        c.resume()          # handler floods events in the same recv batch
        info = c.wait_for_stop(timeout=0.5)
    assert info == StopInfo(pc=0x040D, checkpoint=5)


def test_wait_for_stop_timeout_returns_none():
    fake = FakeVice({Command.PING: lambda b, rid: [resp_frame(0x81, 0, rid)]})
    with _client(fake) as c:
        c.ping()
        assert c.wait_for_stop(timeout=0.3) is None
