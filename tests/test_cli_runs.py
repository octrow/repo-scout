"""Run from CLI, parse_command / to_argv, python -m repo_scout."""
import os
import shlex
import subprocess
import sys

import pytest

from repo_scout import cli, runs

ROW = {"repo": "a/b", "stop": None, "url": "u", "score": 1, "fresh": 1, "pop": 0, "stars": 1, "forks": 0,
       "commits": 1, "pushed_days": 1, "created": "2020", "lang": "Py", "desc": "d", "source": "query",
       "flags": [], "closeness": 0.9}
DROPPED = {**ROW, "repo": "c/d", "stop": "dead"}


def _argv(*extra):
    return ["repo-scout", "--task", "Find X", "q1", *extra]


def _fake_run(monkeypatch):
    def fake(*a, **k):
        cli.last_round2_topics = ["asr"]
        return [ROW, DROPPED]
    monkeypatch.setattr(cli, "run", fake)
    monkeypatch.setattr(cli, "Index", lambda p: None)


def _go(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()


def test_main_saves_run(monkeypatch, capsys):
    _fake_run(monkeypatch)
    _go(monkeypatch, [*_argv("--project", "p", "-q")])
    [s] = runs.list_runs()
    d = runs.load(s.path)
    assert len(d["rows"]) == 2 and d["round2_topics"] == ["asr"]
    assert d["params"]["project"] == "p" and d["params"]["queries"] == ["q1"]
    assert "out" not in d["params"] and "json" not in d["params"]


def test_main_out_path(monkeypatch, tmp_path):
    _fake_run(monkeypatch)
    out = tmp_path / "sub" / "r.json"
    _go(monkeypatch, [*_argv("--out", str(out))])
    assert out.exists() and runs.list_runs() == []


@pytest.mark.parametrize("extra", [["--no-save"], ["--replay", "/nonexistent"]])
def test_main_no_save(monkeypatch, extra):
    _fake_run(monkeypatch)
    monkeypatch.setattr(cli.github, "configure", lambda *a: None)
    monkeypatch.setattr(cli.github, "recorded_at", lambda: cli.datetime.now(cli.UTC))
    _go(monkeypatch, _argv(*extra))
    assert runs.list_runs() == []


def test_parse_command_strips_prefix():
    a = cli.parse_command('$ repo-scout --task "Find X" "q one" --months 3')
    assert a.queries == ["q one"] and a.task == "Find X" and a.months == 3
    assert cli.parse_command("repo_scout --task t q").queries == ["q"]


@pytest.mark.parametrize("text", ["repo-scout q", "repo-scout --task t", "--task t q --bogus 1", "--task t --months x q",
                                  "--task 'unclosed q", "--task t '" + "x " * 200 + "'"])
def test_parse_command_errors(text, capsys):
    with pytest.raises(ValueError):
        cli.parse_command(text)
    assert capsys.readouterr().err == ""


PARAM_SETS = [
    {},
    {"months": 3, "lang": "rust", "project": "p"},
    {"exclude": ["a b", "c"], "must": ["x|y"], "no_round2": True, "no_stars_check": True},
    {"min_closeness": 0.7, "from_index": 0, "round2_k": 5, "stars_k": 3, "limit": 20, "new_days": 10},
    {"queries": ["-language:go foo", "topic:x"], "task": "- weird task"},
]


@pytest.mark.parametrize("over", PARAM_SETS)
def test_to_argv_roundtrip(over):
    base = cli.search_params(cli.parse_command("--task t q"))
    p = {**base, **over}
    argv = cli.to_argv(p)
    assert cli.search_params(cli.parse_command(shlex.join(["repo-scout", *argv]))) == p


def test_to_argv_omits_defaults():
    p = cli.search_params(cli.parse_command("--task t q"))
    assert "--months" not in " ".join(cli.to_argv(p))


def test_python_dash_m():
    out = subprocess.run([sys.executable, "-m", "repo_scout", "verdict", "-h"], capture_output=True, text=True)
    assert out.returncode == 0 and "owner/repo" in out.stdout


def test_to_argv_extra_goes_before_separator():
    p = cli.search_params(cli.parse_command("--task t q1 q2"))
    a = cli._parser().parse_args(cli.to_argv(p, extra=["--out", "/x/r.json"]))
    assert a.out == "/x/r.json" and a.queries == ["q1", "q2"]


def test_main_prints_before_save_and_survives_oserror(monkeypatch, capsys):
    _fake_run(monkeypatch)

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(cli.runs, "save", boom)
    _go(monkeypatch, _argv())
    assert "a/b" in capsys.readouterr().out


def test_help_survives_legacy_code_page():
    """Windows with redirected output encodes stdout as cp1252, which has no ★ or →."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    r = subprocess.run([sys.executable, "-m", "repo_scout", "--help"], capture_output=True, env=env)
    assert r.returncode == 0, r.stderr.decode(errors="replace")
