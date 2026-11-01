"""Checks stop rules, flags and score axes."""

from datetime import UTC, datetime, timedelta
from typing import Any

from repo_scout.triage import triage

NOW = datetime(2026, 10, 11, tzinfo=UTC)


def repo(stars=0, commits=100, pushed=1, created=400, fork=False) -> dict[str, Any]:
    def iso(d):
        return (NOW - timedelta(days=d)).isoformat().replace("+00:00", "Z")

    return {
        "nameWithOwner": "a/b",
        "url": "u",
        "description": None,
        "stargazerCount": stars,
        "forkCount": 0,
        "pushedAt": iso(pushed),
        "createdAt": iso(created),
        "isArchived": False,
        "isFork": fork,
        "parent": {"nameWithOwner": "o/b"} if fork else None,
        "primaryLanguage": None,
        "defaultBranchRef": {"target": {"history": {"totalCount": commits}}},
    }


def test_triage():
    assert triage(repo(pushed=130, commits=499), NOW, 60)["stop"].startswith("dead")
    assert triage(repo(pushed=130, commits=500), NOW, 60)["stop"] is None
    assert triage(repo(pushed=190, commits=5000), NOW, 60)["stop"].startswith("dead")
    assert triage(repo(commits=49, stars=0), NOW, 60)["stop"].startswith("toy")
    assert triage(repo(commits=49, stars=1), NOW, 60)["stop"] is None
    r = triage(repo(stars=5000, commits=30, pushed=7, created=10, fork=True), NOW, 60)
    assert (r["fresh"], r["pop"], r["score"]) == (4, 2, 6)
    assert r["flags"] == ["fork o/b", "stars≫commits", "new"]
    assert triage(repo(pushed=91), NOW, 60)["fresh"] == 0


def test_never_pushed_repo_ages_from_creation():
    from tests.test_conditions import NOW, node

    row = triage({**node("a/b"), "pushedAt": None, "createdAt": "2026-10-01T00:00:00Z"}, NOW, 60)
    assert row["pushed_days"] == (NOW - datetime.fromisoformat("2026-10-01T00:00:00Z")).days


def test_zero_commits_with_stars_is_no_code():
    assert triage(repo(commits=0, stars=1), NOW, 60)["stop"] == "no code"


def test_missing_branch_counts_zero_commits():
    row = triage({**repo(stars=0), "defaultBranchRef": None}, NOW, 60)
    assert (row["commits"], row["stop"]) == (0, "toy (0 commits, 0★)")


def test_dead_wins_over_toy():
    assert triage(repo(pushed=200, commits=0, stars=0), NOW, 60)["stop"] == "dead (200d)"


def test_all_flags_in_fixed_order():
    r = {**repo(stars=1_000, commits=49, created=60, fork=True), "isArchived": True, "parent": None}
    assert triage(r, NOW, 60)["flags"] == ["fork ?", "stars≫commits", "archived", "new"]


def test_hype_flag_needs_min_stars_and_ratio():
    assert "stars≫commits" not in triage(repo(stars=999, commits=1), NOW, 60)["flags"]
    assert "stars≫commits" not in triage(repo(stars=2_000, commits=100), NOW, 60)["flags"]
    assert "stars≫commits" in triage(repo(stars=2_001, commits=100), NOW, 60)["flags"]


def test_last_push_overrides_pushed_at():
    row = triage(repo(pushed=1), NOW, 60, last_push=repo(pushed=200)["pushedAt"])
    assert (row["pushed_days"], row["stop"]) == (200, "dead (200d)")


def test_full_row_shape():
    r: dict[str, Any] = {
        **repo(stars=150, commits=80, pushed=20, created=400),
        "description": "a|b\nc",
        "forkCount": 3,
        "primaryLanguage": {"name": "Python"},
        "repositoryTopics": {"nodes": [{"topic": {"name": "cli"}}]},
    }
    assert triage(r, NOW, 60) == {
        "repo": "a/b",
        "url": "u",
        "stars": 150,
        "forks": 3,
        "commits": 80,
        "pushed_days": 20,
        "created": r["createdAt"][:10],
        "topics": ["cli"],
        "lang": "Python",
        "desc": "a/b c",
        "score": 3,
        "fresh": 2,
        "pop": 1,
        "flags": [],
        "stop": None,
    }
