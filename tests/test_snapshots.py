import json
import subprocess
from datetime import UTC, datetime

import pytest

from repo_scout import github
from repo_scout.cli import run

NODE = {"nameWithOwner": "a/b", "url": "u", "description": None, "stargazerCount": 5, "forkCount": 0,
        "pushedAt": "2026-10-10T00:00:00Z", "createdAt": "2020-01-01T00:00:00Z", "isArchived": False,
        "isFork": False, "parent": None, "primaryLanguage": None,
        "defaultBranchRef": {"target": {"history": {"totalCount": 100}}}}
RESP = json.dumps({"data": {"search": {"nodes": [NODE]}, "rateLimit": {"cost": 1, "remaining": 9, "resetAt": "t"}}})


@pytest.fixture(autouse=True)
def reset():
    yield
    github.configure(None, None)


def test_record_then_replay(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or
                        subprocess.CompletedProcess(cmd, 0, RESP, ""))
    now = datetime(2026, 10, 11, tzinfo=UTC)
    github.configure("record", tmp_path)
    (tmp_path / "meta.json").write_text(json.dumps({"recorded_at": now.isoformat()}))
    rows = run(["q"], months=6, new_days=60, limit=5, lang=None, now=now)
    assert len(calls) == 2 and rows[0]["repo"] == "a/b"  # search + details
    assert "recorded_at" in json.loads((tmp_path / "meta.json").read_text())

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("network in replay"))
    github.configure("replay", tmp_path)
    assert run(["q"], months=6, new_days=60, limit=5, lang=None, now=github.recorded_at()) == rows


def test_replay_missing_snapshot(tmp_path):
    (tmp_path / "meta.json").write_text('{"recorded_at": "2026-10-11T00:00:00+00:00"}')
    github.configure("replay", tmp_path)
    with pytest.raises(github.GitHubError, match="snapshot"):
        github.search("q", 5)


def test_record_reuses_existing_and_keeps_meta(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or
                        subprocess.CompletedProcess(cmd, 0, RESP, ""))
    github.configure("record", tmp_path)
    first = (tmp_path / "meta.json").read_text()
    github.search("q", 5)
    github.configure("record", tmp_path)
    github.search("q", 5)
    assert len(calls) == 1 and (tmp_path / "meta.json").read_text() == first


def fake_live(sent):
    def live(query, variables, **_):
        sent.append(query)
        aliases = [i for i in range(10) if f"r{i}:" in query]
        repo = {"m0": None, "m1": {"text": "hello"}, "defaultBranchRef": {"target": {
            "history": {"nodes": [{"message": "x"}]}}}}
        return {"data": {f"r{i}": (None if i == 1 else repo) for i in aliases}}
    return live


def test_details_batches_and_parses(monkeypatch):
    sent = []
    monkeypatch.setattr(github, "_graphql_live", fake_live(sent))
    out = github.details(["a/b", "c/d", "bad name"])
    assert out == {"a/b": {"readme": "hello", "commits": [{"message": "x"}]}}
    assert len(sent) == 1 and 'owner: "a"' in sent[0] and "HEAD:README.md" in sent[0]
    monkeypatch.setattr(github, "DETAILS_CHUNK", 1)
    sent.clear()
    github.details(["a/b", "c/d"])
    assert len(sent) == 2


def test_details_per_repo_snapshots(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(github, "_graphql_live", fake_live(sent))
    github.configure("record", tmp_path)
    github.details(["a/b", "c/d"])
    assert len(sent) == 1 and len(list((tmp_path / "details").glob("*.json.gz"))) == 2
    github.details(["a/b", "c/d", "e/f"])  # append: missing only
    assert len(sent) == 2 and "e0:" not in sent[1] and sent[1].count("repository(") == 1
    monkeypatch.setattr(github, "_graphql_live", lambda *a: pytest.fail("network in replay"))
    github.configure("replay", tmp_path)
    assert github.details(["e/f", "a/B"]).keys() == {"e/f", "a/B"}
    with pytest.raises(github.GitHubError, match="snapshot"):
        github.details(["x/y"])


def test_readme_text_is_capped(monkeypatch):
    big = json.dumps({"data": {"r0": {"m0": {"text": "x" * 20_000}}}})
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, big, ""))
    assert len(github.graphql("q", {})["data"]["r0"]["m0"]["text"]) == github.README_MAX_CHARS


def test_shared_details_dir(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(github, "_rechecked", set())
    monkeypatch.setattr(github, "_graphql_live", fake_live(sent))
    shared = tmp_path / "_shared" / "details"
    github.configure("record", tmp_path / "set1", shared)
    github.details(["a/b", "c/d"])  # c/d deleted: None mark also in shared cache
    github.configure("record", tmp_path / "set2", shared)
    assert github.details(["A/b", "c/d"]).keys() == {"A/b", "c/d"}  # None mark rechecked and resurrected
    assert len(sent) == 2 and '"b"' not in sent[1] and len(list(shared.glob("*.json.gz"))) == 2
    assert not (tmp_path / "set1" / "details").exists()
    monkeypatch.setattr(github, "_graphql_live", lambda *a, **k: pytest.fail("network in replay"))
    github.configure("replay", tmp_path / "set3", shared)
    assert github.details(["a/b"]).keys() == {"a/b"}


def test_record_single_repo_retries_once(monkeypatch, tmp_path):
    got = []
    monkeypatch.setattr(github, "last_failed", set())
    monkeypatch.setattr(github, "_graphql_live", lambda q, v, retries: got.append(retries) or (_ for _ in ()).throw(
        github.GitHubError("502")))
    github.configure("record", tmp_path, tmp_path / "shared")
    assert github.details(["a/b"]) == {}
    github.configure("record", tmp_path / "plain")  # standard eval --record
    github.details(["a/b"])
    assert got == [github.EVAL_SINGLE_RETRIES, github.MAX_RETRIES]


def test_detail_chunks_fetched_concurrently(monkeypatch, tmp_path):
    import threading
    barrier = threading.Barrier(github.DETAILS_WORKERS, timeout=5)  # without concurrency — BrokenBarrierError
    live = fake_live([])
    monkeypatch.setattr(github, "_graphql_live", lambda q, v, **k: barrier.wait() is not None and live(q, v))
    monkeypatch.setattr(github, "DETAILS_CHUNK", 1)
    github.configure("record", tmp_path, tmp_path / "shared")
    names = [f"o/r{i}" for i in range(github.DETAILS_WORKERS)]
    assert list(github.details(names)) == names


def test_spent_points_counted_for_live_calls_only(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(github, "spent", 0)
    monkeypatch.setattr(github, "_attempt", lambda q, v: (
        {"data": {"rateLimit": {"cost": 2, "remaining": 4990, "resetAt": "x"}}}, None))
    github.configure("record", tmp_path)
    github.graphql("q", {})
    github.graphql("q", {})  # second from snapshot: does not spend limit
    assert github.spent == 2
    caplog.set_level("INFO", logger="repo_scout")
    github.log_usage()
    assert "spent 2 GraphQL points" in caplog.text
