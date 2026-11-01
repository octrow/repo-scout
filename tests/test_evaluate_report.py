"""Characterization tests: pin the exact `repo-scout eval` report text and metric values."""

import atexit
from pathlib import Path

import pytest

from repo_scout import eval_llm, evaluate, fake_stars
from repo_scout.github import GitHubError

SPEC_A = {
    "name": "a",
    "calls": {"search": 3, "details": 2},
    "expected": [
        {"repo": "o/study", "verdict": "→ Study (deep)"},
        {"repo": "o/razbor", "verdict": "→ Разбор"},
        {"repo": "o/look", "verdict": "-> Inspect"},
        {"repo": "o/dropped", "verdict": "→ Inspect"},
        {"repo": "o/missing", "verdict": "→ Inspect"},
        {"repo": "o/noise", "verdict": "drop (junk)"},
        {"repo": "o/rej", "verdict": "rejected"},
        {"repo": "o/otsev", "verdict": "отсев"},
        {"repo": "o/doubt", "verdict": "doubt"},
    ],
}
ROWS_A = [
    {"repo": "x/other", "stop": None, "closeness": 0.9},
    {"repo": "O/Study", "stop": None, "closeness": 0.70},
    {"repo": "o/razbor", "stop": None, "closeness": 0.66},
    {"repo": "o/look", "stop": None, "closeness": 0.82},
    {"repo": "o/dropped", "stop": "dead (200d)", "closeness": 0.8},
    {"repo": "o/noise", "stop": None, "closeness": 0.55},
    {"repo": "o/rej", "stop": None, "closeness": 0.75},
    {"repo": "x/low", "stop": None, "closeness": 0.60},
    {"repo": "x/none", "stop": None},
]
SPEC_B = {
    "name": "b",
    "calls": {},
    "expected": [{"repo": "p/one", "verdict": "→ Study"}, {"repo": "p/two", "verdict": "-> Study"}],
}
ROWS_B = [{"repo": "p/one", "stop": "fork", "closeness": 0.7}, {"repo": "p/two", "stop": None, "closeness": 0.5}]
SETS = {"a.toml": (SPEC_A, ROWS_A), "b.toml": (SPEC_B, ROWS_B)}


def test_metrics_full_values():
    rows = [*ROWS_A[:3], {"repo": "o/look", "stop": None, "closeness": None}, *ROWS_A[4:]]
    assert evaluate.metrics(SPEC_A, rows) == {
        "name": "a",
        "positives": 5,
        "found": 4,
        "kept": [("o/study", 2), ("o/razbor", 3), ("o/look", 4)],
        "false_drops": [("o/dropped", "dead (200d)")],
        "not_found": ["o/missing"],
        "negatives_passed": ["o/noise", "o/rej"],
        "min_close": 0.66,
    }
    assert evaluate.metrics(SPEC_B, ROWS_B)["min_close"] == 0.5
    assert evaluate.metrics({"name": "e", "expected": []}, [])["min_close"] is None


def test_detail_text():
    assert evaluate.detail(evaluate.metrics(SPEC_A, ROWS_A)) == DETAIL_A


DETAIL_A = (
    "\n"
    "### a\n"
    "- passed, rank 2: o/study\n"
    "- passed, rank 3: o/razbor\n"
    "- passed, rank 4: o/look\n"
    "- false drop: o/dropped (dead (200d))\n"
    "- not found: o/missing\n"
    "- negative passed: o/noise\n"
    "- negative passed: o/rej"
)


@pytest.fixture
def usage(monkeypatch):
    registered = []
    monkeypatch.setattr(atexit, "register", registered.append)
    return registered


@pytest.fixture
def fake_sets(monkeypatch, usage):
    calls = []

    def fake_eval_set(path, mode, task=None, round2=True):
        calls.append((str(path), mode, task, round2))
        spec, rows = SETS[str(path)]
        return dict(spec), [dict(r) for r in rows]

    monkeypatch.setattr(evaluate, "eval_set", fake_eval_set)
    return calls


def test_report_all_sections(fake_sets, usage, capsys):
    argv = ["a.toml", "b.toml", "--calls", "--sweep", "--top", "2", "--detail", "--task", "T", "--no-round2"]
    evaluate.main(argv)
    assert capsys.readouterr().out == REPORT_ALL
    assert fake_sets == [("a.toml", "replay", "T", False), ("b.toml", "replay", "T", False)]
    assert usage == [evaluate.github.log_usage]


REPORT_ALL = (
    "| set | positives | found | passed | positions | false drops | not found | negatives passed | min closeness |\n"
    "|---|---|---|---|---|---|---|---|---|\n"
    "| a | 5 | 4 | 3 | 2, 3, 4 | 1 | 1 | 1 | 0.66 |\n"
    "| b | 2 | 2 | 0 | — | 2 | 0 | 0 | — |\n"
    "\n"
    "a: search 3, details 2\n"
    "b: search 0, details 0\n"
    "\n"
    "| threshold | lost → Study | lost all → | remaining rows |\n"
    "|---|---|---|---|\n"
    "| 0.50 | 0 | 0 | 8 |\n"
    "| 0.51 | 1 | 1 | 7 |\n"
    "| 0.52 | 1 | 1 | 7 |\n"
    "| 0.53 | 1 | 1 | 7 |\n"
    "| 0.54 | 1 | 1 | 7 |\n"
    "| 0.55 | 1 | 1 | 7 |\n"
    "| 0.56 | 1 | 1 | 6 |\n"
    "| 0.57 | 1 | 1 | 6 |\n"
    "| 0.58 | 1 | 1 | 6 |\n"
    "| 0.59 | 1 | 1 | 6 |\n"
    "| 0.60 | 1 | 1 | 6 |\n"
    "| 0.61 | 1 | 1 | 5 |\n"
    "| 0.62 | 1 | 1 | 5 |\n"
    "| 0.63 | 1 | 1 | 5 |\n"
    "| 0.64 | 1 | 1 | 5 |\n"
    "| 0.65 | 1 | 1 | 5 |\n"
    "| 0.66 | 1 | 1 | 5 |\n"
    "| 0.67 | 2 | 2 | 4 |\n"
    "| 0.68 | 2 | 2 | 4 |\n"
    "| 0.69 | 2 | 2 | 4 |\n"
    "| 0.70 | 2 | 2 | 4 |\n"
    "| 0.71 | 3 | 3 | 3 |\n"
    "| 0.72 | 3 | 3 | 3 |\n"
    "| 0.73 | 3 | 3 | 3 |\n"
    "| 0.74 | 3 | 3 | 3 |\n"
    "| 0.75 | 3 | 3 | 3 |\n"
    "| 0.76 | 3 | 3 | 2 |\n"
    "| 0.77 | 3 | 3 | 2 |\n"
    "| 0.78 | 3 | 3 | 2 |\n"
    "| 0.79 | 3 | 3 | 2 |\n"
    "| 0.80 | 3 | 3 | 2 |\n"
    "| 0.81 | 3 | 3 | 2 |\n"
    "| 0.82 | 3 | 3 | 2 |\n"
    "| 0.83 | 3 | 4 | 1 |\n"
    "| 0.84 | 3 | 4 | 1 |\n"
    "| 0.85 | 3 | 4 | 1 |\n"
    "| 0.86 | 3 | 4 | 1 |\n"
    "| 0.87 | 3 | 4 | 1 |\n"
    "| 0.88 | 3 | 4 | 1 |\n"
    "| 0.89 | 3 | 4 | 1 |\n"
    "| 0.90 | 3 | 4 | 1 |\n"
    "\n"
    "a top-2: x/other, O/Study\n"
    "\n"
    "### a\n"
    "- passed, rank 2: o/study\n"
    "- passed, rank 3: o/razbor\n"
    "- passed, rank 4: o/look\n"
    "- false drop: o/dropped (dead (200d))\n"
    "- not found: o/missing\n"
    "- negative passed: o/rej\n"
    "\n"
    "### b\n"
    "- false drop: p/one (fork)\n"
    "- false drop: p/two (off-topic (0.50))\n"
)


def test_report_plain(fake_sets, capsys):
    evaluate.main(["a.toml", "--record"])
    assert capsys.readouterr().out == REPORT_PLAIN
    assert fake_sets == [("a.toml", "record", None, True)]


REPORT_PLAIN = (
    "| set | positives | found | passed | positions | false drops | not found | negatives passed | min closeness |\n"
    "|---|---|---|---|---|---|---|---|---|\n"
    "| a | 5 | 4 | 3 | 2, 3, 4 | 1 | 1 | 1 | 0.66 |\n"
)


def test_report_top_zero_prints_no_top_lines(fake_sets, capsys):
    evaluate.main(["a.toml", "--top", "0"])
    assert capsys.readouterr().out == REPORT_PLAIN


def test_report_eval_set_error_exits(monkeypatch, usage):
    def boom(*_a, **_k):
        raise GitHubError("rate limit")

    monkeypatch.setattr(evaluate, "eval_set", boom)
    with pytest.raises(SystemExit) as e:
        evaluate.main(["a.toml"])
    assert e.value.code == "eval: rate limit"


def test_report_needs_sets(usage, capsys):
    with pytest.raises(SystemExit) as e:
        evaluate.main([])
    assert e.value.code == 2
    assert "eval/*.toml sets required" in capsys.readouterr().err
    assert usage == []


def test_report_fake_stars(monkeypatch, capsys):
    monkeypatch.setattr(fake_stars, "run", lambda mode, show_all: f"{mode} {show_all}")
    evaluate.main(["--fake-stars", "--record", "--all-grid"])
    evaluate.main(["--fake-stars"])
    assert capsys.readouterr().out == "record True\nreplay False\n"


def test_report_fake_stars_error(monkeypatch):
    def boom(*_a):
        raise ValueError("no set")

    monkeypatch.setattr(fake_stars, "run", boom)
    with pytest.raises(SystemExit) as e:
        evaluate.main(["--fake-stars"])
    assert e.value.code == "eval: no set"


def test_report_llm_draft(monkeypatch, usage, capsys):
    monkeypatch.setattr(eval_llm, "report", lambda paths, mode: f"{[str(p) for p in paths]} {mode}")
    evaluate.main(["a.toml", "--llm-draft", "--record"])
    assert capsys.readouterr().out == "['a.toml'] record\n"
    assert usage == [evaluate.github.log_usage]


def test_report_llm_draft_error(monkeypatch, usage):
    def boom(*_a):
        raise eval_llm.LLMError("no key")

    monkeypatch.setattr(eval_llm, "report", boom)
    with pytest.raises(SystemExit) as e:
        evaluate.main(["a.toml", "--llm-draft"])
    assert e.value.code == "eval: no key"


def test_report_index_check(monkeypatch, usage, capsys):
    seen = []

    def fake_check(path, mode, from_index):
        seen.append((str(path), mode, from_index))
        return "" if str(path) == "a.toml" else f"{path} ok"

    monkeypatch.setattr(evaluate, "index_check", fake_check)
    evaluate.main(["a.toml", "b.toml", "c.toml", "--index-check", "--from-index", "7"])
    assert capsys.readouterr().out == "b.toml ok\nc.toml ok\n"
    assert seen == [("a.toml", "replay", 7), ("b.toml", "replay", 7), ("c.toml", "replay", 7)]


def test_report_index_check_error(monkeypatch, usage):
    def boom(*_a):
        raise ValueError("bad set")

    monkeypatch.setattr(evaluate, "index_check", boom)
    with pytest.raises(SystemExit) as e:
        evaluate.main(["a.toml", "--index-check"])
    assert e.value.code == "eval: bad set"


IC_SPEC = {
    "name": "ic",
    "queries": ["q1", "q2", "q3"],
    "expected": [
        {"repo": "o/live", "verdict": "→ Study"},
        {"repo": "o/idx", "verdict": "-> Inspect"},
        {"repo": "o/stopped", "verdict": "→ Inspect"},
        {"repo": "o/neg", "verdict": "drop"},
    ],
}
IC_FIRST = [{"repo": "o/live", "stop": None}, {"repo": "o/x", "stop": "fork"}, {"repo": "o/y", "stop": None}]
IC_SECOND = [
    {"repo": "O/Live", "stop": None, "source": "query"},
    {"repo": "o/z", "stop": None, "source": "запрос"},
    {"repo": "o/idx", "stop": None, "source": "index"},
    {"repo": "o/stopped", "stop": "dead", "source": "индекс"},
    {"repo": "o/neg", "stop": None, "source": "index"},
    {"repo": "o/other", "stop": None, "source": "round2"},
]


def _fake_index_eval(spec, calls):
    def fake(path, mode, task=None, queries=None, index=None, from_index=evaluate.FROM_INDEX, round2=True):
        calls.append((Path(path).name, mode, task, queries, index is not None, from_index, round2))
        return dict(spec), [dict(r) for r in (IC_SECOND if task else IC_FIRST)]

    return fake


def test_index_check_text(monkeypatch):
    calls = []
    monkeypatch.setattr(evaluate, "eval_set", _fake_index_eval({**IC_SPEC, "alt_task": "alt"}, calls))
    assert evaluate.index_check(Path("s.toml"), "replay", 9) == INDEX_CHECK
    assert calls == [
        ("s.toml", "replay", None, None, True, evaluate.FROM_INDEX, False),
        ("s.toml", "replay", "alt", ["q1", "q2"], True, 9, False),
    ]


INDEX_CHECK = "ic: Index after first run 2 rows; second run (2 queries, alternative task): live search 2, from Index 3 (passed stop rules 2); positives in live ['O/Live'], positives from Index ['o/idx'] of 3"


def test_index_check_without_alt_task_is_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(evaluate, "eval_set", _fake_index_eval(IC_SPEC, calls))
    assert evaluate.index_check(Path("s.toml"), "replay") == ""
    assert len(calls) == 1


def test_index_check_without_hits_uses_dash(monkeypatch):
    calls = []
    spec = {**IC_SPEC, "alt_task": "alt", "expected": [{"repo": "o/nope", "verdict": "→ Study"}]}
    monkeypatch.setattr(evaluate, "eval_set", _fake_index_eval(spec, calls))
    assert evaluate.index_check(Path("s.toml"), "replay").endswith("positives in live —, positives from Index — of 1")
