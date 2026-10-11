import json
from datetime import UTC, datetime

import pytest

from repo_scout import runs

NOW = datetime(2026, 5, 1, 12, 30, 5, tzinfo=UTC)
PARAMS = {"task": "Find a CLI tool for X!", "queries": ["q"], "project": "p"}
ROWS = [{"repo": "a/b", "stop": None}, {"repo": "c/d", "stop": "мёртвый"}]


def test_save_load_roundtrip():
    path = runs.save(PARAMS, ROWS, ["t1"], NOW)
    assert path.parent == runs.runs_dir() and path.name == "20260501-123005-find-a-cli-tool-for-x.json"
    data = runs.load(path)
    assert data["version"] == 1 and data["params"] == PARAMS
    assert data["rows"] == ROWS and data["round2_topics"] == ["t1"]
    assert data["created_at"] == NOW.isoformat()


def test_slug_fallback_and_limit():
    assert runs.slug("Привет, мир") == "run"
    assert len(runs.slug("a" * 100)) == 40


def test_no_collision():
    assert runs.save(PARAMS, ROWS, [], NOW) != runs.save(PARAMS, ROWS, [], NOW)


def test_non_ascii_not_escaped():
    path = runs.save(PARAMS, ROWS, [], NOW)
    assert "мёртвый" in path.read_text(encoding="utf-8")


def test_list_runs_with_broken_file():
    good = runs.save(PARAMS, ROWS, [], NOW)
    bad = runs.runs_dir() / "20260101-000000-bad.json"
    bad.write_text("{не json")
    s = {x.path: x for x in runs.list_runs()}
    assert s[good].error is None and s[good].n_total == 2 and s[good].n_kept == 1
    assert s[good].task == PARAMS["task"] and s[good].project == "p"
    assert s[bad].error


def test_list_runs_no_dir():
    assert runs.list_runs() == []


@pytest.mark.parametrize("data", [{"version": 2, "created_at": "", "params": {}, "round2_topics": [], "rows": []},
                                  {"version": 1}])
def test_load_invalid(tmp_path, data):
    p = tmp_path / "x.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        runs.load(p)


def test_delete():
    path = runs.save(PARAMS, ROWS, [], NOW)
    runs.delete(path)
    assert not path.exists()


@pytest.mark.parametrize("bad", [
    {"version": 1, "created_at": "", "params": [], "round2_topics": [], "rows": []},
    {"version": 1, "created_at": "", "params": {}, "round2_topics": [], "rows": [1]},
    {"version": 1, "created_at": "", "params": {}, "round2_topics": [1], "rows": []},
    {"version": 1, "created_at": "", "params": {}, "round2_topics": [], "rows": {}}])
def test_load_rejects_wrong_shapes_and_list_runs_survives(tmp_path, bad):
    runs.save(PARAMS, ROWS, [], NOW)
    p = runs.runs_dir() / "20260101-000000-bad.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        runs.load(p)
    s = {x.path: x for x in runs.list_runs()}
    assert s[p].error and len(s) == 2
