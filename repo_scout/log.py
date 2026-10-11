"""Лог хода работы: stderr и файл ($REPO_SCOUT_LOG или ~/.local/state/repo-scout/run.log, перезаписывается
каждым запуском) — чтобы долгий прогон можно было смотреть `tail -f` из другого терминала."""
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("repo_scout")


def log_path() -> Path:
    return Path(os.environ.get("REPO_SCOUT_LOG") or Path.home() / ".local/state/repo-scout/run.log")


def setup(quiet: bool = False) -> Path:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S")
    log.handlers.clear()
    log.setLevel(logging.INFO)
    file = logging.FileHandler(path, mode="w", encoding="utf-8")
    err = logging.StreamHandler(sys.stderr)
    err.setLevel(logging.WARNING if quiet else logging.INFO)
    for h in (file, err):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.info("лог: %s", path)
    return path
