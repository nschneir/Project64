"""A minimal in-process fake of the VICE binary monitor for unit tests.

Accepts one connection, decodes command frames, and replies from a
programmable handler table. Runs in a background thread on an OS-assigned port.
"""

from __future__ import annotations

import socket
import struct
import threading

from c64lib.protocol import _CMD_HEADER  # test-only import of private struct

RESP_HEADER = struct.Struct("<BBIBBI")


def resp_frame(rtype: int, err: int, rid: int, body: bytes = b"") -> bytes:
    return RESP_HEADER.pack(0x02, 0x02, len(body), rtype, err, rid) + body


class FakeVice:
    """handlers: dict command -> callable(body: bytes, rid: int) -> list[bytes] (frames)."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.received: list[tuple[int, bytes]] = []
        self._srv = socket.create_server(("127.0.0.1", 0))
        self.port = self._srv.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        conn, _ = self._srv.accept()
        buf = bytearray()
        with conn:
            while True:
                try:
                    data = conn.recv(4096)
                except OSError:
                    return
                if not data:
                    return
                buf += data
                while len(buf) >= _CMD_HEADER.size:
                    stx, api, blen, rid, cmd = _CMD_HEADER.unpack_from(buf)
                    if len(buf) < _CMD_HEADER.size + blen:
                        break
                    body = bytes(buf[_CMD_HEADER.size : _CMD_HEADER.size + blen])
                    del buf[: _CMD_HEADER.size + blen]
                    self.received.append((cmd, body))
                    for frame in self.handlers[cmd](body, rid):
                        conn.sendall(frame)

    def close(self):
        self._srv.close()
