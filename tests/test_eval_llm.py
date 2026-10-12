from datetime import UTC, datetime
from pathlib import Path

from repo_scout import eval_llm, evaluate, github, llm


def test_variants_union_and_draft():
    spec = {"queries": ["a", "b"]}
    d = llm.Draft("T", ("b", "c"), None, ("m",), ())
    v = eval_llm.variants(spec, d)
    assert v["agent"] is None and v["union"]["queries"] == ["a", "b", "c"]
    assert v["draft"] == {"task": "T", "queries": ["b", "c"], "lang": "", "must": ["m"], "exclude": []}


def test_skips_set_without_need(tmp_path: Path, capsys):
    p = tmp_path / "s.toml"
    p.write_text('name = "s"\ntask = "t"\nqueries = ["q"]\n')
    assert eval_llm.report([p], "replay") == "no sets with a need field"
    assert "without need field" in capsys.readouterr().err


def test_table_totals():
    def m(f, k):
        return {"found": f, "kept": [0] * k, "positives": 4}
    t = eval_llm.table([{"name": "s", "agent": m(2, 1), "draft": m(3, 2), "union": m(4, 3),
                         "stats": {"tokens": 600, "seconds": 8.0}}])
    assert "| s | 4 | 2/1 | 3/2 | 4/3 | 600 | 8.0 |" in t and "total found" in t


def test_eval_one_end_to_end(tmp_path: Path, monkeypatch):
    p = tmp_path / "s.toml"
    p.write_text('name = "s"\nneed = "n"\ntask = "t"\nqueries = ["q"]\n')
    d = llm.Draft("T", ("z",), None, (), ())

    def fake_draft(need):
        llm.last_stats.update(tokens=5, seconds=1.5)
        return d
    seen = []
    monkeypatch.setattr(llm, "draft", fake_draft)
    monkeypatch.setattr(eval_llm, "_metrics", lambda path, mode, snap, ov: seen.append(ov) or {"found": 1, "kept": [], "positives": 2})
    try:
        r = eval_llm.eval_one(p, "replay")
    finally:
        github.configure(None, None)
    assert r["name"] == "s" and r["stats"] == {"tokens": 5, "seconds": 1.5}
    assert [o and o.get("queries") for o in seen] == [None, ["z"], ["q", "z"]]
    assert "| s | 2 | 1/0 | 1/0 | 1/0 | 5 | 1.5 |" in eval_llm.table([r])


def test_report_lists_draft_queries(monkeypatch, tmp_path):
    from repo_scout.llm import Draft
    m = {"positives": 2, "found": 1, "kept": []}
    r = {"name": "s", "llm_draft": Draft("T", ("q1", "q2"), None, (), ()), "stats": {"tokens": 5, "seconds": 1.5},
         "agent": m, "draft": m, "union": m}
    monkeypatch.setattr(eval_llm, "eval_one", lambda p, mode: r)
    out = eval_llm.report([tmp_path / "s.toml"], "replay")
    assert "s: q1 | q2" in out


def test_metrics_use_shared_details_and_no_stars(monkeypatch, tmp_path):
    p = tmp_path / "s.toml"
    p.write_text('name = "s"\ntask = "t"\nqueries = ["q"]\nexpected = []\n')
    seen = {}
    monkeypatch.setattr(github, "configure", lambda *a: seen.update(args=a))
    monkeypatch.setattr(evaluate, "run", lambda *a, **k: seen.update(kw=k) or [])
    monkeypatch.setattr(github, "recorded_at", lambda: datetime(2026, 1, 1, tzinfo=UTC))
    eval_llm._metrics(p, "replay", tmp_path / "snap", None)
    assert seen["args"] == ("replay", tmp_path / "snap", tmp_path / "_shared" / "details")
    assert not seen["kw"].get("stars_k")
