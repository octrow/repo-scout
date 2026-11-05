"""Run logging: stderr and file. Each invocation writes to its own logs/<timestamp>-<pid>.log
next to run.log ($REPO_SCOUT_LOG or ~/.local/state/repo-scout/run.log), while run.log symlinks to the latest:
concurrent runs do not overwrite each other, and `tail -F run.log` follows the latest.
Old logs are pruned until the total size is within LOG_DIR_MAX_BYTES; one run file is capped by
RUN_MAX_BYTES x (1 + RUN_BACKUPS). Secrets are masked in every record; uncaught errors go through the logger."""

import functools
import logging
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

log = logging.getLogger("repo_scout")

LIVE_SECONDS = 3600  # a log touched within the last hour may belong to a running process
MB = 1 << 20
LOG_DIR_MAX_BYTES = 50 * MB  # budget for the whole logs/ folder (pruned at start-up)
RUN_MAX_BYTES, RUN_BACKUPS = 20 * MB, 1  # one run: log + one rotated .log.1 = 40 MB at most
MIN_SECRET_LEN = 8  # shorter values would match ordinary text
SECRET_VARS = ("LLM_API_KEY", "TYPESAFE_API_KEY", "GH_TOKEN", "GITHUB_TOKEN")  # masked by value in every record
NEWLINE_MARK = " ⏎ "  # one record = one line (file tracebacks stay multi-line)
_secrets: set[str] = set()


def register_secrets() -> None:
    """Mask the configured keys by value (call after config load: .env values count, not only os.environ)."""
    from repo_scout import llm

    _secrets.update(v for v in (llm.setting(n) for n in SECRET_VARS) if len(v) >= MIN_SECRET_LEN)


def _redact(text: str) -> str:
    for sec in _secrets:
        text = text.replace(sec, "***")
    return text


class RedactFilter(logging.Filter):
    """Masks secrets (args and traceback included); newlines in the message become NEWLINE_MARK."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if _secrets or "\n" in msg:
            record.msg, record.args = _redact(msg).replace("\n", NEWLINE_MARK), None
        if _secrets and record.exc_info and not record.exc_text:  # Formatter reuses exc_text
            record.exc_text = _redact(logging.Formatter().formatException(record.exc_info))
        return True


def _excepthook(et, ev, tb) -> None:
    if issubclass(et, KeyboardInterrupt):
        sys.__excepthook__(et, ev, tb)
        return
    log.critical("uncaught exception", exc_info=(et, ev, tb))


def log_path() -> Path:
    return Path(os.environ.get("REPO_SCOUT_LOG") or Path.home() / ".local/state/repo-scout/run.log")


def prune(logs: Path, keep: Path, limit: int = LOG_DIR_MAX_BYTES, now: float | None = None) -> None:
    """Delete oldest log files while total size > limit. The current log and logs written within
    LIVE_SECONDS (likely a parallel run) are kept; files removed by a parallel prune are skipped."""
    now = time.time() if now is None else now
    stats = []
    for p in logs.glob("*.log*"):
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
    register_secrets()
    file = RotatingFileHandler(path, maxBytes=RUN_MAX_BYTES, backupCount=RUN_BACKUPS, encoding="utf-8")
    file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    err = logging.StreamHandler(sys.stderr)
    err.setLevel(logging.WARNING if quiet else logging.INFO)
    err.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    for h in (file, err):
        h.addFilter(RedactFilter())
        log.addHandler(h)
    sys.excepthook = _excepthook
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
