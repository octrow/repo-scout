"""Port selection for GUI: free — use it; occupied by our GUI — show link and (optionally) restart;
occupied by another program — offer next free port. Without NiceGUI: runs before import."""
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
HEALTH_PATH = "/_repo-scout"  # responds with {"app": APP_ID, "pid": …}
APP_ID = "repo-scout"
PORT_SCAN = 50
STOP_WAIT_SECONDS = 10.0

Ask = Callable[[str, bool], bool]


def is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # like uvicorn: TIME_WAIT is fine, LISTEN is not
        try:
            s.bind((HOST, port))
        except OSError:
            return False
    return True


def next_free(port: int) -> int:
    for p in range(port + 1, port + 1 + PORT_SCAN):
        if is_free(p):
            return p
    raise RuntimeError(f"no free port in {port + 1}-{port + PORT_SCAN}")


def our_pid(port: int) -> int | None:
    """PID of our GUI on port or None if occupied by another program."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}{HEALTH_PATH}", timeout=1) as r:
            data = json.loads(r.read())
    except (OSError, ValueError):
        return None
    pid = data.get("pid") if isinstance(data, dict) and data.get("app") == APP_ID else None
    return pid if isinstance(pid, int) and pid > 1 and pid != os.getpid() else None


def _is_repo_scout(pid: int) -> bool:
    """Verify process command line before sending signal."""
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return False
    return "repo-scout" in cmd or "repo_scout" in cmd


def stop(pid: int, port: int) -> None:
    if not _is_repo_scout(pid):
        raise RuntimeError(f"process {pid} is not repo-scout, so it was not stopped")
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while time.monotonic() < deadline:
        if is_free(port):
            return
        time.sleep(0.2)
    raise RuntimeError(f"port {port} was not freed within {STOP_WAIT_SECONDS:.0f}s")


def ask_tty(question: str, default: bool) -> bool:
    """[Y/n] / [y/N]; default answer if no TTY."""
    if not sys.stdin.isatty():
        return default
    answer = input(f"{question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    return default if not answer else answer in ("y", "yes")


def choose(port: int, ask: Ask = ask_tty) -> int | None:
    """Port to run on or None if GUI is already running and restart was declined."""
    if is_free(port):
        return port
    if (pid := our_pid(port)) is not None:
        print(f"GUI is already running: http://{HOST}:{port}/")
        if not ask("Restart it?", False):
            return None
        stop(pid, port)
        return port
    alt = next_free(port)
    if ask(f"Port {port} is in use by another program. Launch on {alt}?", True):
        return alt
    return None
