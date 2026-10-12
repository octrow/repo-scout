"""Run logging: stderr and file. Each invocation writes to its own logs/<timestamp>-<pid>.log
next to run.log ($REPO_SCOUT_LOG or ~/.local/state/repo-scout/run.log), while run.log symlinks to the latest:
concurrent runs do not overwrite each other, and `tail -F run.log` follows the latest.
Old logs are pruned until the total size is within LOG_DIR_MAX_BYTES."""
import functools
import logging
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

log = logging.getLogger("repo_scout")

LIVE_SECONDS = 3600  # a log touched within the last hour may belong to a running process
LOG_DIR_MAX_BYTES = 1 << 30  # 1 GiB for all logs; single large run is never truncated


def log_path() -> Path:
    return Path(os.environ.get("REPO_SCOUT_LOG") or Path.home() / ".local/state/repo-scout/run.log")


def prune(logs: Path, keep: Path, limit: int = LOG_DIR_MAX_BYTES, now: float | None = None) -> None:
    """Delete oldest log files while total size > limit. The current log and logs written within
    LIVE_SECONDS (likely a parallel run) are kept; files removed by a parallel prune are skipped."""
    now = time.time() if now is None else now
    stats = []
    for p in logs.glob("*.log"):
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        stats.append((st.st_mtime, st.st_size, p))
    total = sum(size for _, size, _ in stats)
    for mtime, size, p in sorted(stats):
        if total <= limit:
            break
        if p != keep and now - mtime > LIVE_SECONDS:
            p.unlink(missing_ok=True)
            total -= size


def _link(link: Path, target: Path) -> None:
    tmp = link.with_name(f".{link.name}.{os.getpid()}")
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(target.relative_to(link.parent))
    os.replace(tmp, link)  # atomic; replaces old plain run.log file as well


def setup(quiet: bool = False) -> Path:
    link = log_path()
    logs = link.parent / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / f"{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}.log"
    for h in log.handlers:
        h.close()
    log.handlers.clear()
    log.setLevel(logging.INFO)
    file = logging.FileHandler(path, encoding="utf-8")
    file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    err = logging.StreamHandler(sys.stderr)
    err.setLevel(logging.WARNING if quiet else logging.INFO)
    err.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    log.addHandler(file)
    log.addHandler(err)
    _link(link, path)
    prune(logs, path)
    log.info("log: %s · command: %s", path, " ".join(sys.argv))
    return path


def logged_exit(fn: Callable[[], None]) -> Callable[[], None]:
    """Ensure fatal `sys.exit("text")` errors are logged to file as ERROR, not only stderr."""
    @functools.wraps(fn)
    def run() -> None:
        try:
            fn()
        except SystemExit as e:
            file = [h for h in log.handlers if isinstance(h, logging.FileHandler)]
            if isinstance(e.code, str) and file:
                record = log.makeRecord(log.name, logging.ERROR, __file__, 0, e.code, (), None)
                for h in file:
                    h.handle(record)
            raise
    return run
