import json
import re
import subprocess

import pytest

from repo_scout import github

OK = json.dumps(
    {
        "data": {
            "search": {"nodes": [{"nameWithOwner": "a/b"}, None]},
            "rateLimit": {"cost": 1, "remaining": 9, "resetAt": "t"},
        }
    }
)


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
    assert github.last_rate_limit is not None
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


def test_partial_errors_return_data(monkeypatch, caplog):
    body = json.dumps(
        {
            "data": {"search": {"nodes": [{"nameWithOwner": "a/b"}]}},
            "errors": [{"type": "FORBIDDEN", "message": "boom"}],
        }
    )
    run_with(monkeypatch, [(1, body, "")])
    assert github.search("q", 5) == [{"nameWithOwner": "a/b"}]
    assert "boom" in caplog.text


def test_retry_on_502(monkeypatch):
    calls, _ = run_with(monkeypatch, [(1, "", "gh: HTTP 502"), (0, OK, "")])
    assert github.search("q", 5)
    assert len(calls) == 2


def _flaky_live(bad: set[str]):
    """Chunk containing repo from bad fails with 502; single bad repos also fail."""

    def live(query, variables, **_):
        names = re.findall(r'r(\d+): repository\(owner: "(\w+)", name: "(\w+)"\)', query)
        if any(f"{o}/{n}" in bad for _, o, n in names):
            raise github.GitHubError("GitHub failed to respond: gh: HTTP 502")
        return {"data": {f"r{i}": {"m0": {"text": f"{o}/{n}"}} for i, o, n in names}}

    return live


def test_details_splits_chunk_on_502_and_skips_failing_repo(monkeypatch, caplog):
    monkeypatch.setattr(github, "_graphql_live", _flaky_live({"a/bad"}))
    out = github.details(["a/one", "a/bad", "a/two", "a/three"])
    assert set(out) == {"a/one", "a/two", "a/three"}
    assert "a/bad" in caplog.text


def test_refresh_failed_repo_is_not_reported_as_deleted(monkeypatch):
    monkeypatch.setattr(github, "_graphql_live", _flaky_live({"a/bad"}))
    out = github.refresh(["a/one", "a/bad"])
    assert "a/bad" not in out and github.last_failed == {"a/bad"}


def test_skipped_repo_is_recorded_so_replay_repeats_the_skip(monkeypatch, tmp_path):
    monkeypatch.setattr(github, "_graphql_live", _flaky_live({"a/bad"}))
    github.last_failed.clear()
    try:
        github.configure("record", tmp_path)
        assert set(github.details(["a/one", "a/bad"])) == {"a/one"}
        github.configure("replay", tmp_path)
        assert set(github.details(["a/one", "a/bad"])) == {"a/one"}
    finally:
        github.configure(None, None)


def test_retry_on_null_data(monkeypatch):
    calls, _ = run_with(monkeypatch, [(0, json.dumps({"data": None}), ""), (0, OK, "")])
    assert github.search("q", 5)
    assert len(calls) == 2


def test_alias_error_other_than_not_found_is_a_failure_not_a_deletion(monkeypatch):
    github.last_failed.clear()
    monkeypatch.setattr(
        github,
        "_graphql_live",
        lambda q, v, **_: {
            "data": {"r0": None, "r1": None, "r2": {"m0": {"text": "ok"}}},
            "errors": [{"type": "NOT_FOUND", "path": ["r0"]}, {"type": "TIMEOUT", "path": ["r1"]}],
        },
    )
    got = github._batch(["a/gone", "a/slow", "a/ok"], github._alias)
    assert got == {"a/gone": None, "a/ok": {"m0": {"text": "ok"}}}
    assert github.last_failed == {"a/slow"}
    github.last_failed.clear()


def test_batch_retries_only_single_repos_and_less_when_recording_shared_details(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(github, "_graphql_live", lambda q, v, retries=None: seen.append(retries) or {"data": {}})
    github._batch(["a/one", "a/two"], github._alias)
    github._batch(["a/one"], github._alias)
    try:
        github.configure("record", tmp_path, details_dir=tmp_path / "details")
        github._batch(["a/one"], github._alias)
        github.configure("record", tmp_path)
        github._batch(["a/one"], github._alias)
    finally:
        github.configure(None, None)
    assert seen == [0, github.MAX_RETRIES, github.EVAL_SINGLE_RETRIES, github.MAX_RETRIES]


def test_graphql_errors_without_data_fail_fast(monkeypatch):
    body = json.dumps({"data": None, "errors": [{"type": "FORBIDDEN", "message": "nope"}]})
    calls, sleeps = run_with(monkeypatch, [(0, body, "")])
    with pytest.raises(github.GitHubError, match="GraphQL: nope"):
        github.search("q", 5)
    assert len(calls) == 1 and not sleeps


def test_failed_gh_without_stderr_reports_stdout(monkeypatch):
    run_with(monkeypatch, [(1, "plain failure", "")])
    with pytest.raises(github.GitHubError, match="gh failed: plain failure"):
        github.search("q", 5)


def _counting_live(fetched: list[str]):
    """Each alias returns a full node; a/gone is deleted (null)."""

    def live(query, variables, **_):
        names = re.findall(r'r(\d+): repository\(owner: "(\w+)", name: "(\w+)"\)', query)
        fetched.extend(f"{o}/{n}" for _, o, n in names)
        nodes = {f"r{i}": {"nameWithOwner": f"{o}/{n}", "m1": {"text": "hi"}} for i, o, n in names}
        return {"data": {k: None if v["nameWithOwner"] == "a/gone" else v for k, v in nodes.items()}}

    return live


def test_refresh_record_then_replay_reads_snapshots(monkeypatch, tmp_path):
    fetched = []
    monkeypatch.setattr(github, "_graphql_live", _counting_live(fetched))
    want = {"a/one": {"node": {"nameWithOwner": "a/one"}, "details": {"readme": "hi", "commits": []}}}
    try:
        github.configure("record", tmp_path)
        assert github.refresh(["a/one", "a/gone", "not a name"]) == want
        written = sorted(p.name for p in (tmp_path / "refresh").iterdir())
        assert written == sorted(f"{github._key(n)}.json.gz" for n in ("a/one", "a/gone"))
        github.configure("replay", tmp_path)
        assert github.refresh(["a/one", "a/gone"]) == want
        assert fetched == ["a/one", "a/gone"]
        with pytest.raises(github.GitHubError, match="missing refresh snapshot for a/new"):
            github.refresh(["a/new"])
    finally:
        github.configure(None, None)


def test_refresh_rechecks_deleted_marker_once_with_shared_details(monkeypatch, tmp_path):
    fetched = []
    monkeypatch.setattr(github, "_graphql_live", _counting_live(fetched))
    monkeypatch.setattr(github, "_rechecked", set())
    try:
        github.configure("record", tmp_path / "set", details_dir=tmp_path / "details")
        for _ in range(3):
            assert set(github.refresh(["a/one", "a/gone"])) == {"a/one"}
        assert fetched == ["a/one", "a/gone", "a/gone"]
    finally:
        github.configure(None, None)


def test_rate_limit_in_details_stops_instead_of_skipping(monkeypatch):
    """A rate-limited batch is retried with backoff, then stops the run: no rows kept unscreened as `no details`."""
    calls, sleeps = run_with(monkeypatch, [(1, "", "HTTP 429")] * 4)
    with pytest.raises(github.RateLimited):
        github.details(["a/one", "a/two"])
    assert len(calls) == 4 and sleeps == [5, 10, 20]


def test_missing_gh_is_a_github_error(monkeypatch):
    def no_gh(cmd, **kw):
        raise FileNotFoundError(2, "No such file or directory", "gh")

    monkeypatch.setattr(subprocess, "run", no_gh)
    with pytest.raises(github.GitHubError, match="cli.github.com"):
        github.search("q", 5)
    from repo_scout import stars

    with pytest.raises(github.GitHubError, match="cli.github.com"):
        stars._rest("repos/a/b/stargazers")


def test_gh_timeout_is_passed_and_retried_as_transient(monkeypatch):
    seen, sleeps = [], []
    results = iter([subprocess.TimeoutExpired("gh", 1), subprocess.CompletedProcess("gh", 0, OK, "")])

    def fake_run(cmd, **kw):
        seen.append(kw.get("timeout"))
        r = next(results)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(github.time, "sleep", sleeps.append)
    assert github.search("q", 5)
    assert seen == [github.GH_TIMEOUT_S] * 2 and len(sleeps) == 1
