"""index_rows: Index table rows with project, Verdict kind and text filters (no GUI)."""

from datetime import UTC, datetime

import numpy as np
import pytest

from repo_scout.gui.index_page import index_rows
from repo_scout.index import Index

NOW = datetime(2026, 5, 1, 12, 30, 5, tzinfo=UTC)


@pytest.fixture
def idx(tmp_path):
    idx = Index(tmp_path / "i.db", model="m1")
    meta = {
        "repo": "a/Alpha",
        "url": "https://x/a",
        "desc": ":rocket: alpha tool",
        "topics": [],
        "stars": 7,
        "lang": "Go",
    }
    idx.upsert(meta, "# readme", np.array([1, 0]), NOW)
    idx.upsert({**meta, "repo": "b/beta", "url": "", "desc": "beta", "lang": None}, None, np.array([0, 1]), NOW)
    idx.upsert({**meta, "repo": "c/gamma", "desc": "gamma", "lang": "Rust"}, "r", np.array([0, 1]), NOW)
    idx.add_verdict("a/alpha", "→ Inspect", "p1", "task", NOW)
    idx.add_verdict("c/gamma", "→ Study (why)", "p2", "task", NOW)
    return idx


def names(rows):
    return [r["name"] for r in rows]


def test_index_rows_builds_every_column(idx):
    rows = index_rows(idx)
    assert names(rows) == ["a/Alpha", "b/beta", "c/gamma"]
    assert rows[0] == {
        "key": "a/alpha",
        "name": "a/Alpha",
        "desc": "\U0001f680 alpha tool",
        "stars": 7,
        "lang": "Go",
        "date": "2026-05-01",
        "readme": True,
        "seen": "p1: → Inspect (2026-05-01)",
        "url": "https://x/a",
    }
    assert rows[1]["lang"] == "—" and rows[1]["readme"] is False and rows[1]["seen"] == "—"
    assert rows[1]["url"] == "https://github.com/b/beta"


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"project": "p1"}, ["a/Alpha"]),
        ({"project": "p2"}, ["c/gamma"]),
        ({"project": "none"}, []),
        ({"kind": "dig"}, ["c/gamma"]),
        ({"kind": "watch"}, ["a/Alpha"]),
        ({"kind": "drop"}, []),
        ({"kind": "unknown"}, ["a/Alpha", "b/beta", "c/gamma"]),
        ({"project": "p1", "kind": "dig"}, []),
        ({"text": "  RUST "}, ["c/gamma"]),
        ({"text": "BETA"}, ["b/beta"]),
        ({"text": "tool"}, ["a/Alpha"]),
        ({"text": "go", "kind": "dig"}, []),
        ({"text": " "}, ["a/Alpha", "b/beta", "c/gamma"]),
    ],
)
def test_index_rows_filters(idx, filters, expected):
    assert names(index_rows(idx, **filters)) == expected
