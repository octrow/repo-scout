"""Выбор порта для GUI: свободен — берём; занят нашим GUI — ссылка и (по желанию) перезапуск;
занят чужой программой — предлагаем следующий свободный. Без nicegui: вызывается до его импорта."""
import json
import os
import signal
import socket
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

HOST = "127.0.0.1"
HEALTH_PATH = "/_repo-scout"  # отвечает {"app": APP_ID, "pid": …}
APP_ID = "repo-scout"
PORT_SCAN = 50
STOP_WAIT_SECONDS = 10.0

Ask = Callable[[str, bool], bool]


def is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # как uvicorn: TIME_WAIT не мешает, LISTEN — да
        try:
            s.bind((HOST, port))
        except OSError:
            return False
    return True


def next_free(port: int) -> int:
    for p in range(port + 1, port + 1 + PORT_SCAN):
        if is_free(p):
            return p
    raise RuntimeError(f"нет свободного порта в {port + 1}–{port + PORT_SCAN}")


def our_pid(port: int) -> int | None:
    """PID нашего GUI на порту или None, если там чужая программа."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}{HEALTH_PATH}", timeout=1) as r:
            data = json.loads(r.read())
    except (OSError, ValueError):
        return None
    pid = data.get("pid") if isinstance(data, dict) and data.get("app") == APP_ID else None
    return pid if isinstance(pid, int) and pid > 1 and pid != os.getpid() else None


def _is_repo_scout(pid: int) -> bool:
    """Проверка по командной строке процесса, прежде чем слать ему сигнал."""
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return False
    return "repo-scout" in cmd or "repo_scout" in cmd


def stop(pid: int, port: int) -> None:
    if not _is_repo_scout(pid):
        raise RuntimeError(f"процесс {pid} не похож на repo-scout — не трогаю")
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while time.monotonic() < deadline:
        if is_free(port):
            return
        time.sleep(0.2)
    raise RuntimeError(f"порт {port} не освободился за {STOP_WAIT_SECONDS:.0f} с")


def ask_tty(question: str, default: bool) -> bool:
    """[Y/n] / [y/N]; без терминала — ответ по умолчанию."""
    if not sys.stdin.isatty():
        return default
    answer = input(f"{question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    return default if not answer else answer in ("y", "yes", "д", "да")


def choose(port: int, ask: Ask = ask_tty) -> int | None:
    """Порт для запуска или None — GUI уже работает и перезапуск не нужен."""
    if is_free(port):
        return port
    if (pid := our_pid(port)) is not None:
        print(f"GUI уже запущен: http://{HOST}:{port}/")
        if not ask("Перезапустить его?", False):
            return None
        stop(pid, port)
        return port
    alt = next_free(port)
    if ask(f"Порт {port} занят другой программой. Запустить на {alt}?", True):
        return alt
    return None
