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
    rows = run(["q"], months=6, new_days=60, limit=5, lang=None, now=now)
    assert len(calls) == 2 and rows[0]["repo"] == "a/b"  # поиск + details
    assert "recorded_at" in json.loads((tmp_path / "meta.json").read_text())

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("network in replay"))
    github.configure("replay", tmp_path)
    assert run(["q"], months=6, new_days=60, limit=5, lang=None, now=github.recorded_at()) == rows


def test_replay_missing_snapshot(tmp_path):
    (tmp_path / "meta.json").write_text('{"recorded_at": "2026-10-11T00:00:00+00:00"}')
    github.configure("replay", tmp_path)
    with pytest.raises(github.GitHubError, match="снапшот"):
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
    github.details(["a/b", "c/d", "e/f"])  # дозапись: только недостающее
    assert len(sent) == 2 and "e0:" not in sent[1] and sent[1].count("repository(") == 1
    monkeypatch.setattr(github, "_graphql_live", lambda *a: pytest.fail("network in replay"))
    github.configure("replay", tmp_path)
    assert github.details(["e/f", "a/B"]).keys() == {"e/f", "a/B"}  # другой состав пачки, регистр не важен
    with pytest.raises(github.GitHubError, match="снапшот"):
        github.details(["x/y"])


def test_readme_text_is_capped(monkeypatch):
    big = json.dumps({"data": {"r0": {"m0": {"text": "x" * 20_000}}}})
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, big, ""))
    assert len(github.graphql("q", {})["data"]["r0"]["m0"]["text"]) == github.README_MAX_CHARS
