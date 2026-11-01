"""Fit column from a System One model: optional, never drops or reorders, failures are warnings."""

import pytest

from repo_scout import systemone


def _rows(*repos, stop=None):
    return [{"repo": r, "stop": stop} for r in repos]


@pytest.fixture
def posted(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    sent = []

    def fake(body):
        sent.append(body)
        return {"answers": {"r0": {"type": "noul", "noul": 0.91}, "r1": {"noul": "bad"}}}

    monkeypatch.setattr(systemone, "_post", fake)
    return sent


def test_without_key_nothing_is_sent(monkeypatch):
    monkeypatch.setattr(systemone, "_post", lambda body: pytest.fail("must not call"))
    rows = _rows("a/a")
    systemone.add_fit(rows, "task", {"a/a": "text"}, 20)
    assert "fit" not in rows[0]


def test_one_request_with_a_question_per_top_kept_row(posted):
    rows = _rows("a/a", "b/b") + _rows("c/c", stop="dead")
    systemone.add_fit(rows, "find X", {"a/a": "A", "b/b": "B", "c/c": "C"}, 20)
    assert len(posted) == 1
    body = posted[0]
    assert body["model"] == "jev-latest" and body["state"] == {"task": "find X"}
    assert set(body["questions"]) == {"r0", "r1"}  # dropped c/c is not judged
    assert body["questions"]["r0"]["type"] == "noul" and body["questions"]["r0"]["instructions"]["repo"] == "A"
    assert rows[0]["fit"] == 0.91
    assert "fit" not in rows[1]  # malformed answer skipped


def test_k_limits_rows(posted):
    systemone.add_fit(_rows("a/a", "b/b"), "t", {"a/a": "A", "b/b": "B"}, 1)
    assert set(posted[0]["questions"]) == {"r0"}


@pytest.mark.parametrize("task", [None, ""])
def test_without_task_nothing_is_sent(posted, task):
    rows = _rows("a/a")
    systemone.add_fit(rows, task, {"a/a": "A"}, 20)
    assert posted == [] and "fit" not in rows[0]


def test_without_kept_rows_with_text_nothing_is_sent(posted):
    rows = _rows("a/a", stop="dead") + _rows("b/b")
    systemone.add_fit(rows, "t", {"a/a": "A"}, 20)
    assert posted == [] and rows == _rows("a/a", stop="dead") + _rows("b/b")


def test_rows_without_text_do_not_count_toward_k_and_order_stays(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    sent = []
    monkeypatch.setattr(
        systemone, "_post", lambda body: sent.append(body) or {"answers": {"r0": {"noul": 0.123456}, "r1": {"noul": 1}}}
    )
    rows = _rows("a/a", "b/b", "c/c", "d/d")
    systemone.add_fit(rows, "t", {"b/b": "B", "c/c": "C", "d/d": "D"}, 2)
    assert [q["instructions"]["repo"] for q in sent[0]["questions"].values()] == ["B", "C"]
    assert [r.get("fit") for r in rows] == [None, 0.12, 1.0, None]
    assert [r["repo"] for r in rows] == ["a/a", "b/b", "c/c", "d/d"]


def test_failure_is_a_warning(monkeypatch, caplog):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")

    def boom(body):
        raise systemone.SystemOneError("HTTP error 401; check TYPESAFE_API_KEY")

    monkeypatch.setattr(systemone, "_post", boom)
    rows = _rows("a/a")
    systemone.add_fit(rows, "t", {"a/a": "A"}, 20)
    assert "fit" not in rows[0]
    assert "fit column skipped" in caplog.text
