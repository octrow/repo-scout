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
