from repo_scout.evaluate import metrics, summary_table

SPEC = {"name": "s", "expected": [
    {"repo": "A/one", "verdict": "→ Разбор (x)"},
    {"repo": "a/two", "verdict": "→ Осмотр"},
    {"repo": "a/three", "verdict": "→ Осмотр"},
    {"repo": "a/four", "verdict": "→ Осмотр"},
    {"repo": "a/noise", "verdict": "отсев (мусор)"},
    {"repo": "a/maybe", "verdict": "спорно (?)"},
]}
ROWS = [
    {"repo": "x/first", "stop": None},
    {"repo": "a/ONE", "stop": None},
    {"repo": "a/two", "stop": "мёртвый (200 дн)"},
    {"repo": "a/noise", "stop": None},
]


def test_metrics():
    m = metrics(SPEC, ROWS)
    assert m["positives"] == 4 and m["found"] == 2
    assert m["kept"] == [("A/one", 2)]
    assert m["false_drops"] == [("a/two", "мёртвый (200 дн)")]
    assert m["not_found"] == ["a/three", "a/four"]
    assert m["negatives_passed"] == ["a/noise"]


def test_summary_table():
    t = summary_table([metrics(SPEC, ROWS)])
    assert "| s | 4 | 2 | 1 | 2 | 1 | 2 | 1 |" in t
