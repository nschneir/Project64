"""Session/daemon lifecycle units: circuit breaker + socket-path guard."""

import time

import pytest

from c64lib.session import (
    RESPAWN_LIMIT,
    RESPAWN_WINDOW,
    Session,
    SessionError,
    _default_socket_path,
)


def _s(tmp_path, monkeypatch, name="cb"):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    return Session(name=name, pid=1, port=1, model="c64")


def test_respawn_circuit_breaker_trips(tmp_path, monkeypatch):
    s = _s(tmp_path, monkeypatch)
    for _ in range(RESPAWN_LIMIT - 1):
        s._record_respawn_and_check()
    with pytest.raises(SessionError):
        s._record_respawn_and_check()


def test_respawn_breaker_ignores_old_crashes(tmp_path, monkeypatch):
    s = _s(tmp_path, monkeypatch, name="cb2")
    old = time.time() - (RESPAWN_WINDOW * 4)
    s._respawns_path().write_text(
        "\n".join(f"{old + i:.3f}" for i in range(RESPAWN_LIMIT - 1)), encoding="utf-8")
    s._record_respawn_and_check()   # 5th overall, but the window has passed


def test_socket_path_prefers_sessions_dir(monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", "/tmp/c64-sockpath-test")
    p = _default_socket_path("snake")
    assert p == "/tmp/c64-sockpath-test/sessions/snake.sock"


def test_socket_path_length_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path / ("x" * 120)))
    p = _default_socket_path("verylongname")
    assert len(p.encode()) <= 100 and p.endswith(".sock")


def test_breaker_error_includes_recovery_command(tmp_path, monkeypatch):
    # FT4(c): the dead-daemon error tells you the one-line fix
    s = _s(tmp_path, monkeypatch, name="cb3")
    for _ in range(RESPAWN_LIMIT - 1):
        s._record_respawn_and_check()
    with pytest.raises(SessionError, match="c64 session ensure"):
        s._record_respawn_and_check()


def test_ensure_attaches_existing(monkeypatch):
    from unittest.mock import Mock
    from unittest.mock import patch as _patch
    existing = Mock()
    with _patch.object(Session, "attach", return_value=existing), \
         _patch.object(Session, "launch") as launch:
        s, started = Session.ensure(model="c64")
    assert s is existing and started is False
    launch.assert_not_called()


def test_ensure_launches_when_absent(monkeypatch):
    from unittest.mock import Mock
    from unittest.mock import patch as _patch
    fresh = Mock()
    with _patch.object(Session, "attach", side_effect=SessionError("none")), \
         _patch.object(Session, "launch", return_value=fresh) as launch:
        s, started = Session.ensure(model="c64", warp=True, headless=True)
    assert s is fresh and started is True
    launch.assert_called_once_with(model="c64", name=None,
                                   headless=True, warp=True)
