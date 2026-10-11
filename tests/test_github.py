import json
import re
import subprocess

import pytest

from repo_scout import github

OK = json.dumps({"data": {"search": {"nodes": [{"nameWithOwner": "a/b"}, None]},
                          "rateLimit": {"cost": 1, "remaining": 9, "resetAt": "t"}}})


def run_with(monkeypatch, results):
    """results: list of (returncode, stdout, stderr); returns (calls, sleeps)."""
    calls, sleeps = [], []
    it = iter(results)

    def fake_run(cmd, **kw):
        calls.append(cmd)
        rc, out, err = next(it)
        return subprocess.CompletedProcess(cmd, rc, out, err)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(github.time, "sleep", sleeps.append)
    return calls, sleeps


def test_ok_and_args(monkeypatch):
    calls, _ = run_with(monkeypatch, [(0, OK, "")])
    assert github.search("q", 5) == [{"nameWithOwner": "a/b"}]
    assert "-F" in calls[0] and "n=5" in calls[0] and "q=q" in calls[0]
    assert github.last_rate_limit["remaining"] == 9


def test_retry_on_429_then_ok(monkeypatch):
    calls, sleeps = run_with(monkeypatch, [(1, "", "HTTP 429"), (1, "", "secondary rate limit"), (0, OK, "")])
    assert github.search("q", 5)
    assert len(calls) == 3 and sleeps == [5, 10]


def test_retry_on_non_json(monkeypatch):
    calls, _ = run_with(monkeypatch, [(0, "<html>", ""), (0, OK, "")])
    assert github.search("q", 5)
    assert len(calls) == 2


def test_retry_on_graphql_rate_limited(monkeypatch):
    err = json.dumps({"errors": [{"type": "RATE_LIMITED", "message": "x"}]})
    calls, _ = run_with(monkeypatch, [(1, err, ""), (0, OK, "")])
    assert github.search("q", 5)
    assert len(calls) == 2


def test_plain_403_fails_fast(monkeypatch):
    calls, sleeps = run_with(monkeypatch, [(1, "", "HTTP 403: Forbidden")])
    with pytest.raises(github.GitHubError, match="403"):
        github.search("q", 5)
    assert len(calls) == 1 and not sleeps


def test_gives_up_after_max_retries(monkeypatch):
    calls, sleeps = run_with(monkeypatch, [(1, "", "HTTP 429")] * 4)
    with pytest.raises(github.GitHubError):
        github.search("q", 5)
    assert len(calls) == 4 and sleeps == [5, 10, 20]


def test_partial_errors_return_data(monkeypatch, capsys):
    body = json.dumps({"data": {"search": {"nodes": [{"nameWithOwner": "a/b"}]}},
                       "errors": [{"type": "FORBIDDEN", "message": "boom"}]})
    run_with(monkeypatch, [(1, body, "")])
    assert github.search("q", 5) == [{"nameWithOwner": "a/b"}]
    assert "boom" in capsys.readouterr().err


def test_retry_on_502(monkeypatch):
    calls, _ = run_with(monkeypatch, [(1, "", "gh: HTTP 502"), (0, OK, "")])
    assert github.search("q", 5)
    assert len(calls) == 2


def _flaky_live(bad: set[str]):
    """Пачка, где есть репо из bad, падает как 502; одиночные bad тоже."""
    def live(query, variables, **_):
        names = re.findall(r'r(\d+): repository\(owner: "(\w+)", name: "(\w+)"\)', query)
        if any(f"{o}/{n}" in bad for _, o, n in names):
            raise github.GitHubError("GitHub не ответил: gh: HTTP 502")
        return {"data": {f"r{i}": {"m0": {"text": f"{o}/{n}"}} for i, o, n in names}}
    return live


def test_details_splits_chunk_on_502_and_skips_failing_repo(monkeypatch, capsys):
    monkeypatch.setattr(github, "_graphql_live", _flaky_live({"a/bad"}))
    out = github.details(["a/one", "a/bad", "a/two", "a/three"])
    assert set(out) == {"a/one", "a/two", "a/three"}
    assert "a/bad" in capsys.readouterr().err


def test_refresh_failed_repo_is_not_reported_as_deleted(monkeypatch):
    monkeypatch.setattr(github, "_graphql_live", _flaky_live({"a/bad"}))
    out = github.refresh(["a/one", "a/bad"])
    assert "a/bad" not in out and github.last_failed == {"a/bad"}
