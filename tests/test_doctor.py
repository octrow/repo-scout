"""`repo-scout doctor`: readiness checks with fix hints; --fix downloads the embedding model."""
import subprocess

import pytest

from repo_scout import doctor


def _env(monkeypatch, *, gh=True, auth=True, cached=True):
    loads = []
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/gh" if gh else None)
    monkeypatch.setattr(doctor.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0 if auth else 1))

    def load(local_only):
        loads.append(local_only)
        if local_only and not cached:
            raise ValueError("not in cache")
    monkeypatch.setattr(doctor, "_load_model", load)
    return loads


def test_all_ok_exits_zero(monkeypatch, capsys):
    _env(monkeypatch)
    doctor.main([])
    out = capsys.readouterr().out
    assert out.count("✓") == 3
    assert "LLM draft (optional): off" in out and "repo-scout config" in out


def test_llm_key_shows_draft_on_without_failing(monkeypatch, capsys):
    _env(monkeypatch)
    monkeypatch.setenv("OMNIROUTE_API_KEY", "k")
    doctor.main([])
    assert "LLM draft (optional): on" in capsys.readouterr().out


def test_missing_gh_fails_with_hint_and_skips_auth(monkeypatch, capsys):
    _env(monkeypatch, gh=False)
    with pytest.raises(SystemExit) as e:
        doctor.main([])
    out = capsys.readouterr().out
    assert e.value.code == 1
    assert "https://cli.github.com/" in out
    assert "gh auth login" in out


def test_not_logged_in_hints_login(monkeypatch, capsys):
    _env(monkeypatch, auth=False)
    with pytest.raises(SystemExit):
        doctor.main([])
    assert "gh auth login" in capsys.readouterr().out


def test_fix_downloads_missing_model(monkeypatch, capsys):
    loads = _env(monkeypatch, cached=False)
    doctor.main(["--fix"])
    assert loads == [True, False]  # cache probe, then download
    assert capsys.readouterr().out.count("✓") == 3  # optional LLM line is "○" when off


def test_failed_download_is_reported_not_raised(monkeypatch, capsys):
    _env(monkeypatch, cached=False)

    def boom(local_only):
        raise OSError("network down")
    monkeypatch.setattr(doctor, "_load_model", boom)
    with pytest.raises(SystemExit) as e:
        doctor.main(["--fix"])
    assert e.value.code == 1
    assert "network down" in capsys.readouterr().out
