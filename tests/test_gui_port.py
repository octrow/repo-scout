import socket

import pytest

from repo_scout.gui import port as portmod


@pytest.fixture
def busy_port():
    s = socket.socket()
    s.bind((portmod.HOST, 0))
    s.listen()
    yield s.getsockname()[1]
    s.close()


def _never(_q: str, _d: bool) -> bool:
    raise AssertionError("не должно спрашивать")


def test_free_port_is_used_without_asking():
    with socket.socket() as s:
        s.bind((portmod.HOST, 0))
        free = s.getsockname()[1]
    assert portmod.choose(free, ask=_never) == free


def test_foreign_program_offers_next_free_port(busy_port, monkeypatch):
    monkeypatch.setattr(portmod, "our_pid", lambda p: None)
    asked = []
    chosen = portmod.choose(busy_port, ask=lambda q, d: asked.append(d) or d)
    assert asked == [True] and chosen > busy_port and portmod.is_free(chosen)


def test_foreign_program_declined_returns_none(busy_port, monkeypatch):
    monkeypatch.setattr(portmod, "our_pid", lambda p: None)
    assert portmod.choose(busy_port, ask=lambda q, d: False) is None


def test_our_gui_shows_link_and_does_not_restart_by_default(busy_port, monkeypatch, capsys):
    monkeypatch.setattr(portmod, "our_pid", lambda p: 4242)
    monkeypatch.setattr(portmod, "stop", lambda pid, p: pytest.fail("перезапуск без согласия"))
    asked = []
    assert portmod.choose(busy_port, ask=lambda q, d: asked.append(d) or d) is None
    assert asked == [False]
    assert f"http://{portmod.HOST}:{busy_port}/" in capsys.readouterr().out


def test_our_gui_restart_when_confirmed(busy_port, monkeypatch):
    monkeypatch.setattr(portmod, "our_pid", lambda p: 4242)
    stopped = []
    monkeypatch.setattr(portmod, "stop", lambda pid, p: stopped.append((pid, p)))
    assert portmod.choose(busy_port, ask=lambda q, d: True) == busy_port
    assert stopped == [(4242, busy_port)]


def test_stop_refuses_foreign_process(monkeypatch):
    monkeypatch.setattr(portmod, "_is_repo_scout", lambda pid: False)
    monkeypatch.setattr(portmod.os, "kill", lambda *a: pytest.fail("сигнал чужому процессу"))
    with pytest.raises(RuntimeError):
        portmod.stop(4242, 1)


def test_our_pid_none_for_non_http_listener(busy_port):
    assert portmod.our_pid(busy_port) is None
