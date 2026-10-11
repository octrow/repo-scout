import re
from datetime import UTC, datetime

import pytest

from repo_scout import cli, github
from repo_scout.conditions import compile_all, exclude_stop, lang_stop, must_stop

NOW = datetime(2026, 10, 11, tzinfo=UTC)


def test_lang():
    assert lang_stop({"lang": "Go"}, "go") is None
    assert lang_stop({"lang": ""}, "go") is None
    assert lang_stop({"lang": "Rust"}, None) is None
    assert lang_stop({"lang": "Rust"}, "go") == "не тот язык (Rust)"


def test_exclude_and_must():
    assert exclude_stop("a WordPress plugin", compile_all("--exclude", ["wordpress"])) == "запрещено: WordPress"
    assert exclude_stop("clean", compile_all("--exclude", ["wordpress"])) is None
    assert must_stop("kaspi and ozon", compile_all("--must", ["kaspi", "OZON"])) is None
    assert must_stop("kaspi", compile_all("--must", ["kaspi", "ozon"])) == "нет обязательного: ozon"


def test_bad_regex_is_value_error_with_flag_name():
    with pytest.raises(ValueError, match=r"--must '\(': "):
        compile_all("--must", ["("])
    assert isinstance(compile_all("--must", ["a"])[0], re.Pattern)


def node(name, readme_hint=""):
    return {"nameWithOwner": name, "url": "u", "description": "tool", "stargazerCount": 10, "forkCount": 0,
            "pushedAt": "2026-10-09T00:00:00Z", "createdAt": "2020-01-01T00:00:00Z", "isArchived": False,
            "isFork": False, "parent": None, "primaryLanguage": {"name": "Go"}, "repositoryTopics": {"nodes": []},
            "defaultBranchRef": {"target": {"history": {"totalCount": 100}}}}


def commit(msg, date, login="alice"):
    return {"committedDate": date, "message": msg, "additions": 50, "deletions": 0,
            "author": {"name": login, "user": {"login": login}}}


def run_pipeline(monkeypatch, details, **kw):
    monkeypatch.setattr(github, "search", lambda q, n: [node(k) for k in details])
    monkeypatch.setattr(github, "details", lambda names: {n: details[n] for n in names if details.get(n)})
    rows = cli.run(["q"], months=6, new_days=60, limit=5, lang=None, now=NOW, **kw)
    return {r["repo"]: r for r in rows}


def test_pipeline_must_exclude_readme_and_cosmetic(monkeypatch):
    fresh = [commit("feat: x", "2026-10-09T00:00:00Z")]
    details = {
        "a/ok": {"readme": "kaspi parser", "commits": fresh},
        "a/nomust": {"readme": "something else", "commits": fresh},
        "a/banned": {"readme": "kaspi wordpress", "commits": fresh},
        "a/noreadme": {"readme": None, "commits": fresh},
        "a/cosmetic": {"readme": "kaspi", "commits": [commit("docs: x", "2025-01-01T00:00:00Z")]},
        "a/stale": {"readme": "kaspi", "commits": [commit("feat: x", "2026-01-01T00:00:00Z")]},
    }
    rows = run_pipeline(monkeypatch, details, must=compile_all("--must", ["kaspi"]), exclude=compile_all("--exclude", ["wordpress"]))
    assert rows["a/ok"]["stop"] is None
    assert rows["a/nomust"]["stop"] == "нет обязательного: kaspi"
    assert rows["a/banned"]["stop"] == "запрещено: wordpress"
    assert rows["a/noreadme"]["stop"] is None and "нет README" in rows["a/noreadme"]["flags"]
    assert "только косметика" in rows["a/cosmetic"]["flags"]
    assert rows["a/cosmetic"]["stop"].startswith("мёртвый")
    assert rows["a/stale"]["stop"].startswith("мёртвый")


def test_pipeline_missing_details_flag(monkeypatch):
    rows = run_pipeline(monkeypatch, {"a/gone": None}, must=compile_all("--must", ["x"]))
    assert rows["a/gone"]["stop"] is None and "нет деталей" in rows["a/gone"]["flags"]


def test_json_output_has_dropped_by_must(monkeypatch, capsys):
    import json
    import sys
    rows = [{"repo": "a/ok", "stop": None, "score": 1, "pushed_days": 1},
            {"repo": "a/no", "stop": "нет обязательного: x", "score": 1, "pushed_days": 1}]
    monkeypatch.setattr(cli, "run", lambda *a, **k: rows)
    monkeypatch.setattr(sys, "argv", ["repo-scout", "q", "--json"])
    cli.main()
    out = json.loads(capsys.readouterr().out)
    assert [r["repo"] for r in out["rows"]] == ["a/ok"] and [r["repo"] for r in out["dropped_by_must"]] == ["a/no"]


def test_pipeline_noise_and_lang_skip_details(monkeypatch):
    seen = []
    monkeypatch.setattr(github, "search", lambda q, n: [node("a/awesome-x"), node("a/real")])
    monkeypatch.setattr(github, "details", lambda names: seen.extend(names) or {})
    rows = cli.run(["q"], months=6, new_days=60, limit=5, lang="rust", now=NOW)
    assert {r["repo"]: r["stop"] for r in rows}["a/real"] == "не тот язык (Go)"
    assert seen == []
