"""README cleaning and Closeness (without loading model)."""
import numpy as np

from repo_scout import cli, semantic

MD = """[![CI](https://x/b.svg)](https://x/ci) [![b](u)](v)
<div align="center">
<h1>Title</h1>
</div>
![logo](a.png)
See [the docs](https://example.com/docs) for <b>more</b>.
<!-- hidden -->
```
<div>keep</div> [a](b)
```
"""


def test_clean_readme():
    out = semantic.clean_readme(MD)
    assert "CI" not in out and "logo" not in out and "hidden" not in out and "https" not in out
    assert "Title" in out and "See the docs for more." in out
    assert "<div>keep</div> [a](b)" in out


def test_candidate_text_truncated():
    row = {"repo": "o/name", "desc": "d", "topics": ["t1", "t2"]}
    t = semantic.candidate_text(row, "x" * 5000)
    assert t.startswith("name\nd\nt1 t2\n") and len(t) == semantic.MAX_CHARS


def test_closeness():
    v = np.array([[1, 0], [0, 1], [0.6, 0.8]], dtype=np.float32)
    assert semantic.closeness(np.array([1, 0], dtype=np.float32), v).tolist() == [1.0, 0.0, np.float32(0.6)]


def _row(repo, closeness, score=0, days=1, stop=None):
    return {"repo": repo, "closeness": closeness, "score": score, "pushed_days": days, "stop": stop}


def test_apply_closeness_and_sort():
    rows = [_row("a", 0.9), _row("b", 0.4), _row("c", None, stop="dead")]
    cli.apply_closeness(rows, 0.5)
    assert rows[1]["stop"] == "off-topic (0.40)" and rows[0]["stop"] is None and rows[2]["stop"] == "dead"
    rows = [_row("lo", 0.7, 9), _row("hi2", 0.8, 1, 5), _row("hi1", 0.8, 1, 2), _row("hi0", 0.8, 3)]
    assert [r["repo"] for r in sorted(rows, key=cli.sort_key)] == ["hi0", "hi1", "hi2", "lo"]


def test_add_closeness_uses_embedder(monkeypatch):
    monkeypatch.setattr(semantic, "embed_task", lambda t: np.array([1, 0], dtype=np.float32))
    monkeypatch.setattr(semantic, "embed_docs",
                        lambda ts: np.array([[1, 0] if "match" in t else [0, 1] for t in ts], dtype=np.float32))
    rows = [{"repo": "o/a", "desc": "match", "topics": [], "stop": None},
            {"repo": "o/b", "desc": "x", "topics": [], "stop": None},
            {"repo": "o/c", "desc": "match", "topics": [], "stop": "dead"}]
    cli.add_closeness(rows, {"o/a": "readme"}, "task")
    assert [r.get("closeness") for r in rows] == [1.0, 0.0, None]


def test_clean_readme_multiline_tags():
    out = semantic.clean_readme('<img\n src="a.png"\n width="9">\n<p\n align="center">Hello</p>\n<!-- a\nb -->\ntext')
    assert out == "Hello\n\ntext" or out.split() == ["Hello", "text"]


def test_clean_readme_hostile_input_is_fast():
    import time
    for bad in ("<div a", "<!--", "![", "[", "[![x](", "<a " * 3):
        t = time.perf_counter()
        semantic.clean_readme(bad * (1_000_000 // len(bad)))
        assert time.perf_counter() - t < 1


def test_embed_docs_reuses_vectors_within_process(monkeypatch):
    seen = []

    class Fake:
        def passage_embed(self, texts, batch_size):
            seen.append(list(texts))
            return [[float(len(t))] + [0.0] * 383 for t in texts]
    monkeypatch.setattr(semantic, "_get", lambda: Fake())
    monkeypatch.setattr(semantic, "_doc_cache", {})
    first = semantic.embed_docs(["a", "bb"])
    again = semantic.embed_docs(["bb", "ccc", "a"])
    assert seen == [["a", "bb"], ["ccc"]] and again.shape == (3, 384)
    assert (again[0] == first[1]).all()
