import io
import logging
import os

from repo_scout import log as logmod


def test_runs_do_not_overwrite_each_other(tmp_path, monkeypatch):
    first = logmod.setup(quiet=True)
    logmod.log.info("first")
    monkeypatch.setattr(os, "getpid", lambda: 999_999)  # second process in the same second
    second = logmod.setup(quiet=True)
    logmod.log.info("second")
    assert first != second and "first" in first.read_text() and "second" not in first.read_text()
    assert logmod.log_path().resolve() == second.resolve()  # run.log points to the latest


def test_prune_keeps_total_under_limit_and_current(tmp_path):
    files = []
    for i in range(4):
        p = tmp_path / f"{i}.log"
        p.write_bytes(b"x" * 100)
        os.utime(p, (i, i))
        files.append(p)
    logmod.prune(tmp_path, keep=files[0], limit=250, now=3 + logmod.LIVE_SECONDS - 1)
    assert [p.exists() for p in files] == [True, False, True, True]  # 3.log is fresh: maybe a live run


def test_fatal_exit_message_goes_to_log_file():
    import pytest

    path = logmod.setup(quiet=True)

    @logmod.logged_exit
    def main() -> None:
        raise SystemExit("eval: LLM unavailable")

    with pytest.raises(SystemExit):
        main()
    assert "ERROR eval: LLM unavailable" in path.read_text()


def _sparse(path, size, mtime):
    with path.open("wb") as fh:
        fh.truncate(size)  # sparse: no real disk used
    os.utime(path, (mtime, mtime))


def test_prune_cap_sparse_files(tmp_path):
    """1.1 GB of sparse logs (rotated .log.1 included) -> under the cap; the current log survives."""
    old = 1_000_000.0
    for i, name in enumerate(("a.log", "a.log.1", "b.log", "c.log.1", "d.log", "cur.log")):
        _sparse(tmp_path / name, (1 if name == "cur.log" else 200) * logmod.MB, old + i)
    logmod.prune(tmp_path, keep=tmp_path / "cur.log", now=old + 10 * logmod.LIVE_SECONDS)
    left = {p.name for p in tmp_path.iterdir()}
    assert sum(p.stat().st_size for p in tmp_path.iterdir()) <= logmod.LOG_DIR_MAX_BYTES, left
    assert "cur.log" in left and "a.log" not in left, left


def test_run_log_rotates(tmp_path, monkeypatch):
    monkeypatch.setattr(logmod, "RUN_MAX_BYTES", 1000)
    path = logmod.setup(quiet=True)
    for _ in range(200):
        logmod.log.info("x" * 100)
    assert path.stat().st_size <= 1000 and path.with_name(path.name + ".1").exists()


def test_secret_redacted_and_one_line():
    logmod._secrets.add("SECRETKEY123")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.addFilter(logmod.RedactFilter())
    logmod.log.addHandler(h)
    try:
        logmod.log.warning("url ?key=%s\nnext", "SECRETKEY123")
        try:
            raise ValueError("bad SECRETKEY123")
        except ValueError:
            logmod.log.exception("failed")
    finally:
        logmod.log.removeHandler(h)
        logmod._secrets.discard("SECRETKEY123")
    out = buf.getvalue()
    assert "SECRETKEY123" not in out and "url ?key=***" + logmod.NEWLINE_MARK + "next" in out
