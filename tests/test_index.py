"""Индекс, Вердикты, источник строк и экспорт (без модели и сети)."""
from datetime import UTC, datetime

import numpy as np
import pytest

from repo_scout import cli, evaluate, github, semantic
from repo_scout.index import Index, validate_verdict
from tests.test_conditions import NOW, node

ROW = {"repo": "O/Name", "url": "u", "desc": "d", "topics": ["t"], "stars": 3, "lang": "Go"}


@pytest.fixture
def fake_embed(monkeypatch):
    monkeypatch.setattr(semantic, "embed_task", lambda t: np.array([1, 0], dtype=np.float32))
    monkeypatch.setattr(semantic, "embed_docs",
                        lambda ts: np.array([[1, 0] if "match" in t else [0, 1] for t in ts], dtype=np.float32))


def test_roundtrip_and_top(tmp_path, fake_embed):
    idx = Index(tmp_path / "sub" / "i.db", model="m1")
    idx.upsert(ROW, "readme", np.array([0, 1]))
    idx.upsert({**ROW, "repo": "o/best"}, None, np.array([1, 0]))
    idx.upsert({**ROW, "repo": "O/NAME"}, "again", np.array([0.5, 0.5]))  # upsert по имени без регистра
    assert idx.top("task", 5) == ["o/best", "O/NAME"]
    assert idx.top("task", 1) == ["o/best"]
    assert Index(tmp_path / "empty.db").top("t", 3) == []


def test_model_change_recomputes_from_stored_text(tmp_path, fake_embed):
    path = tmp_path / "i.db"
    idx = Index(path, model="old")
    idx.upsert({**ROW, "desc": "x"}, "a match here", np.array([0, 1]))
    idx.db.close()
    idx = Index(path, model="new")
    assert idx.db.execute("SELECT model FROM repos").fetchone() == ("new",)
    assert idx.top("t", 1) == ["O/Name"]
    assert np.frombuffer(idx.db.execute("SELECT vec FROM repos").fetchone()[0], dtype=np.float32).tolist() == [1, 0]


def test_verdict_validation():
    validate_verdict("a/b", "→ Разбор (цель)", "p", "t")
    validate_verdict("a/b.c_d", "отсев (шум)", "p", "t")
    for repo, verdict, project, task, msg in [
        ("a/b", "ок", "p", "t", "вердикт"), ("a/b", "→ Разбор", "p", "t", "вердикт"),
        ("a/b", "отсев (x)\nещё", "p", "t", "вердикт"), ("ab", "→ Осмотр", "p", "t", "owner/repo"),
        ("a/..", "→ Осмотр", "p", "t", "owner/repo"), ("a/b c", "→ Осмотр", "p", "t", "owner/repo"),
        ("a/b", "→ Осмотр", "", "t", "проект"), ("a/b", "→ Осмотр", "p", "x\ny", "задача"),
    ]:
        with pytest.raises(ValueError, match=msg):
            validate_verdict(repo, verdict, project, task)


def test_forget_and_rename(tmp_path):
    idx = Index(tmp_path / "i.db")
    idx.upsert(ROW, "r", np.array([1, 0]))
    idx.add_verdict("o/name", "→ Осмотр", "p", "t")
    idx.rename("O/Name", "new/name")
    assert idx.db.execute("SELECT COUNT(*) FROM repos").fetchone() == (0,)
    assert "new/name" in idx.seen(["new/name"])
    idx.upsert({**ROW, "repo": "x/y"}, "r", np.array([1, 0]))
    idx.forget("X/Y")
    assert idx.db.execute("SELECT COUNT(*) FROM repos").fetchone() == (0,)


def test_export_collapses_whitespace(tmp_path):
    idx = Index(tmp_path / "i.db")
    idx.add_verdict("a/b", "→ Осмотр", "p  q", "t\t\u2028x")
    assert evaluate.export_verdicts(idx, None).count("\n") == 4 and "# проект: p q" in evaluate.export_verdicts(idx, None)


def test_seen_latest_per_project_and_export(tmp_path):
    idx = Index(tmp_path / "i.db")
    d = lambda day: datetime(2026, 10, day, tzinfo=UTC)
    idx.add_verdict("A/b", "→ Осмотр", "p1", "t1", d(1))
    idx.add_verdict("a/b", "отсев (шум)", "p1", "t1", d(2))
    idx.add_verdict("a/b", "→ Разбор (x)", "p2", "t2", d(3))
    assert idx.seen(["a/B", "z/z"]) == {"a/b": "p2: → Разбор (x) (2026-10-03); p1: отсев (шум) (2026-10-02)"}
    out = evaluate.export_verdicts(idx, None)
    assert '# проект: p1\n[[expected]]\nrepo = "a/b"\nverdict = "→ Осмотр"' in out and "# проект: p2" in out
    assert "p2" not in evaluate.export_verdicts(idx, "p1")


def test_run_writes_index_pulls_from_index_and_marks_seen(tmp_path, fake_embed, monkeypatch):
    idx = Index(tmp_path / "i.db")
    idx.upsert({**ROW, "repo": "old/repo"}, "match", np.array([1, 0]))
    idx.upsert({**ROW, "repo": "a/live"}, "match", np.array([0, 1]))  # уже в живой выдаче: не тянем
    idx.add_verdict("old/repo", "→ Осмотр", "proj", "t", NOW)
    fetched = []
    monkeypatch.setattr(github, "search", lambda q, n: [node("a/live")])
    monkeypatch.setattr(github, "details", lambda names: {n: {"readme": "match", "commits": []} for n in names})
    monkeypatch.setattr(github, "refresh", lambda names: fetched.extend(names) or
                        {n: {"node": node(n), "details": {"readme": "match", "commits": []}} for n in names})
    rows = {r["repo"]: r for r in cli.run(["q"], months=6, new_days=60, limit=5, lang=None, now=NOW, task="t",
                                          index=idx, from_index=5)}
    assert fetched == ["old/repo"]
    assert rows["old/repo"]["source"] == "индекс" and rows["a/live"]["source"] == "запрос"
    assert "proj: → Осмотр" in rows["old/repo"]["seen"] and rows["a/live"]["seen"] == ""
    assert idx.db.execute("SELECT readme FROM repos WHERE name='a/live'").fetchone() == ("match",)
    md = cli.to_markdown(list(rows.values()))
    assert "источник" in md and "уже смотрели" in md and "proj: → Осмотр" in md
    cli.run(["q"], months=6, new_days=60, limit=5, lang=None, now=NOW, task="t", index=idx, from_index=0)
    assert fetched == ["old/repo"]  # from_index=0 выключает


def test_refresh_splits_node_and_details(monkeypatch):
    repo = {**node("a/b"), "m0": {"text": "# hi"}, "m1": None,
            "recent": {"target": {"history": {"nodes": [{"message": "x"}]}}}}
    monkeypatch.setattr(github, "_graphql_live", lambda q, v, **_: {"data": {"r0": repo, "r1": None}})
    out = github.refresh(["a/b", "a/gone"])
    assert list(out) == ["a/b"] and out["a/b"]["details"] == {"readme": "# hi", "commits": [{"message": "x"}]}
    assert out["a/b"]["node"]["nameWithOwner"] == "a/b" and "m0" not in out["a/b"]["node"]


def _pipeline(monkeypatch, idx, refresh, readme="match"):
    monkeypatch.setattr(github, "search", lambda q, n: [node("a/live")])
    monkeypatch.setattr(github, "details", lambda names: {n: {"readme": readme, "commits": []} for n in names})
    monkeypatch.setattr(github, "refresh", refresh)
    return cli.run(["q"], months=6, new_days=60, limit=5, lang=None, now=NOW, task="t", index=idx, from_index=5)


def test_gone_and_renamed_index_rows(tmp_path, fake_embed, monkeypatch):
    idx = Index(tmp_path / "i.db")
    for n in ("gone/repo", "old/name"):
        idx.upsert({**ROW, "repo": n}, "match", np.array([1, 0]))
    idx.add_verdict("old/name", "→ Осмотр", "p", "t")
    _pipeline(monkeypatch, idx, lambda names: {"old/name": {"node": node("new/name"),
                                                           "details": {"readme": "match", "commits": []}}})
    names = {r[0] for r in idx.db.execute("SELECT name FROM repos")}
    assert names == {"a/live", "new/name"}  # gone забыт, old/name переименован и записан заново
    assert "new/name" in idx.seen(["new/name"])


def test_empty_readme_not_indexed(tmp_path, fake_embed, monkeypatch):
    idx = Index(tmp_path / "i.db")
    _pipeline(monkeypatch, idx, lambda names: {}, readme=None)
    assert idx.db.execute("SELECT COUNT(*) FROM repos").fetchone() == (0,)


def test_conftest_isolates_user_index(tmp_path):
    from repo_scout.index import default_path
    assert default_path() == tmp_path / "user-index.db"


def test_record_and_replay_use_no_index(monkeypatch):
    import sys
    seen = []
    monkeypatch.setattr(cli, "run", lambda *a, **k: seen.append(k["index"]) or [])
    monkeypatch.setattr(github, "configure", lambda *a: None)
    monkeypatch.setattr(github, "recorded_at", lambda: NOW)
    for flag in ("--replay", "--record"):
        monkeypatch.setattr(sys, "argv", ["repo-scout", "q", "--task", "t", flag, "d"])
        cli.main()
    monkeypatch.setattr(sys, "argv", ["repo-scout", "q", "--task", "t"])
    cli.main()
    assert seen[:2] == [None, None] and isinstance(seen[2], Index)
