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


def test_failure_is_a_warning(monkeypatch, caplog):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")

    def boom(body):
        raise systemone.SystemOneError("HTTP error 401; check TYPESAFE_API_KEY")
    monkeypatch.setattr(systemone, "_post", boom)
    rows = _rows("a/a")
    systemone.add_fit(rows, "t", {"a/a": "A"}, 20)
    assert "fit" not in rows[0]
    assert "fit column skipped" in caplog.text
