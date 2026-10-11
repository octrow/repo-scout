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
    assert len(calls) == 1 and rows[0]["repo"] == "a/b"
    assert "recorded_at" in json.loads((tmp_path / "meta.json").read_text())

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("network in replay"))
    github.configure("replay", tmp_path)
    assert run(["q"], months=6, new_days=60, limit=5, lang=None, now=github.recorded_at()) == rows


def test_replay_missing_snapshot(tmp_path):
    (tmp_path / "meta.json").write_text('{"recorded_at": "2026-10-11T00:00:00+00:00"}')
    github.configure("replay", tmp_path)
    with pytest.raises(github.GitHubError, match="снапшот"):
        github.search("q", 5)
