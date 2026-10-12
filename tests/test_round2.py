"""Round 2: topic selection, pool merge, --no-round2 (without model and network)."""
import numpy as np

from repo_scout import cli, github, semantic
from repo_scout.round2 import MAX_TOPICS, pick_topics
from tests.test_conditions import NOW, node


def tnode(name, topics=()):
    return {**node(name), "repositoryTopics": {"nodes": [{"topic": {"name": t}} for t in topics]}}


def rows(*topic_lists):
    return [{"topics": t} for t in topic_lists]


def test_pick_topics_rules():
    top = rows(["python", "asr", "whisper", "once"], ["asr", "whisper", "ai"], ["Python", "ai", "used"], ["used"])
    assert pick_topics(top, ["x topic:used"]) == ["asr", "whisper"]


def test_pick_topics_max_and_threshold():
    top = rows(*[[f"t{i}" for i in range(8)]] * 2)
    assert len(pick_topics(top, [])) == MAX_TOPICS
    assert pick_topics(rows(["a"], ["b"]), []) == []


def _setup(monkeypatch):
    monkeypatch.setattr(semantic, "embed_task", lambda t: np.array([1, 0], dtype=np.float32))
    monkeypatch.setattr(semantic, "embed_docs", lambda ts: np.array([[1, 0]] * len(ts), dtype=np.float32))
    queries = []

    def search(q, n):
        queries.append(q)
        if q.startswith("topic:"):
            return [node("a/one"), node("b/new")]
        return [tnode("a/one", ["asr", "x"]), tnode("a/two", ["asr", "x"])]

    monkeypatch.setattr(github, "search", search)
    monkeypatch.setattr(github, "details", lambda names: {n: {"readme": "r", "commits": []} for n in names})
    return queries


def _run(**kw):
    return cli.run(["q"], months=6, new_days=60, limit=5, lang=None, now=NOW, task="t", **kw)


def test_round2_marks_source_without_duplicates(monkeypatch):
    queries = _setup(monkeypatch)
    out = {r["repo"]: r["source"] for r in _run()}
    assert out == {"a/one": "query", "a/two": "query", "b/new": "round two"}
    assert [q.split()[0] for q in queries] == ["q", "topic:asr", "topic:x"]
    assert "in:" not in queries[1]


def test_no_round2(monkeypatch):
    queries = _setup(monkeypatch)
    assert {r["repo"] for r in _run(round2=False)} == {"a/one", "a/two"}
    assert queries == [queries[0]]


def test_pick_topics_rejects_bad_slugs():
    top = rows(["bad topic", 'x"y', "ok-1"], ["bad topic", 'x"y', "ok-1"])
    assert pick_topics(top, []) == ["ok-1"]


def test_round2_stops_noise_and_indexes_good(monkeypatch, tmp_path):
    from repo_scout.index import Index
    queries = _setup(monkeypatch)
    base = github.search

    def search(q, n):
        if q.startswith("topic:"):
            return [{**tnode("b/bad"), "description": "wordpress plugin"}, tnode("b/good")]
        return base(q, n)

    monkeypatch.setattr(github, "search", search)
    idx = Index(tmp_path / "i.db")
    import re
    out = {r["repo"]: r for r in _run(index=idx, exclude=[re.compile("wordpress")])}
    assert out["b/bad"]["stop"] and not out["b/good"]["stop"]
    assert out["b/good"]["source"] == "round two"
    assert idx.top("t", 10) and "b/good" in idx.top("t", 10) and "b/bad" not in idx.top("t", 10)
    assert queries


def test_round2_topics_exposed(monkeypatch):
    _setup(monkeypatch)
    _run()
    assert cli.last_round2_topics == ["asr", "x"]
    _run(round2=False)
    assert cli.last_round2_topics == []
