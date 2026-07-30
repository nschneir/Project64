import pytest

from c64lib.monitor import MonitorClient, MonitorError
from c64lib.protocol import Command
from tests.fake_vice import FakeVice, resp_frame


def _client(fake: FakeVice) -> MonitorClient:
    c = MonitorClient(port=fake.port, timeout=2.0)
    c.connect(deadline=2.0)
    return c


def test_ping_roundtrip():
    fake = FakeVice({Command.PING: lambda body, rid: [resp_frame(0x81, 0, rid)]})
    with _client(fake) as c:
        c.ping()
    assert fake.received[0][0] == Command.PING


def test_memory_read():
    def handle(body, rid):
        return [resp_frame(0x01, 0, rid, bytes([4, 0]) + b"\x01\x02\x03\x04")]

    fake = FakeVice({Command.MEMORY_GET: handle})
    with _client(fake) as c:
        assert c.memory_read(0x0400, 4) == b"\x01\x02\x03\x04"
    # request body: side_effects=0, start=0400, end=0403, memspace=0, bank=0
    assert fake.received[0][1] == bytes([0, 0x00, 0x04, 0x03, 0x04, 0, 0, 0])


def test_events_are_queued_not_returned():
    def handle(body, rid):
        stopped = resp_frame(0x62, 0, 0xFFFFFFFF, b"\x01\x08")  # unsolicited
        return [stopped, resp_frame(0x81, 0, rid)]

    fake = FakeVice({Command.PING: handle})
    with _client(fake) as c:
        c.ping()
        assert len(c.events) == 1
        assert c.events[0].response_type == 0x62


def test_error_code_raises_monitor_error():
    fake = FakeVice({Command.MEMORY_GET: lambda b, rid: [resp_frame(0x01, 0x02, rid)]})
    with _client(fake) as c:
        with pytest.raises(MonitorError, match="INVALID_MEMSPACE"):
            c.memory_read(0x0400, 1)


def test_resume_sends_exit():
    fake = FakeVice({Command.EXIT: lambda b, rid: [resp_frame(0xAA, 0, rid)]})
    with _client(fake) as c:
        c.resume()
    assert fake.received[0][0] == Command.EXIT


def test_connect_refused_raises_after_deadline():
    c = MonitorClient(port=1, timeout=0.2)  # nothing listens on port 1
    with pytest.raises(ConnectionError):
        c.connect(deadline=0.5)


def test_monitor_error_unknown_code_formats_hex():
    e = MonitorError(Command.MEMORY_GET, 0xEE)     # 0xEE is no ErrorCode member
    assert "0xee" in str(e)


def test_keyboard_feed_chunks_long_text():
    calls = []

    def handle(body, rid):
        calls.append(body)
        return [resp_frame(0x72, 0, rid)]          # KEYBOARD_FEED ok

    fake = FakeVice({Command.KEYBOARD_FEED: handle})
    with _client(fake) as c:
        c.keyboard_feed(b"A" * 450)                # 200-byte chunks -> 3 requests
    assert len(calls) == 3
    assert calls[0][0] == 200 and calls[2][0] == 50


def test_vice_info_parses_version():
    def handle(body, rid):
        return [resp_frame(0x85, 0, rid, bytes([2, 3, 5]))]   # "3.5"

    fake = FakeVice({Command.VICE_INFO: handle})
    with _client(fake) as c:
        assert c.vice_info() == "3.5"


def test_quit_swallows_no_reply():
    fake = FakeVice({Command.QUIT: lambda b, rid: []})   # VICE exits silently
    with _client(fake) as c:
        c.timeout = 0.3
        c.quit()                                          # must not raise


def test_request_times_out_without_response():
    fake = FakeVice({Command.PING: lambda b, rid: []})   # server never replies
    with _client(fake) as c:
        assert c._sock is not None       # `_client` connected it
        c._sock.settimeout(0.3)          # recv gives up quickly -> TimeoutError
        with pytest.raises(TimeoutError):
            c.ping()


def test_closed_connection_raises():
    def handle(body, rid):
        fake.close()          # slam the server mid-request
        return []

    fake = FakeVice({Command.PING: handle})
    with _client(fake) as c:
        with pytest.raises((ConnectionError, OSError)):
            c.ping()
