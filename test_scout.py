"""Run: python3 test_scout.py (or pytest). Checks stop rules, flags and score axes."""
from datetime import datetime, timedelta, timezone

from scout import triage

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def repo(stars=0, commits=100, pushed=1, created=400, fork=False):
    iso = lambda d: (NOW - timedelta(days=d)).isoformat().replace("+00:00", "Z")
    return {"nameWithOwner": "a/b", "url": "u", "description": None, "stargazerCount": stars,
            "forkCount": 0, "pushedAt": iso(pushed), "createdAt": iso(created), "isArchived": False,
            "isFork": fork, "parent": {"nameWithOwner": "o/b"} if fork else None, "primaryLanguage": None,
            "defaultBranchRef": {"target": {"history": {"totalCount": commits}}}}


def test_triage():
    assert triage(repo(pushed=130, commits=499), NOW, 60)["stop"].startswith("мёртвый")
    assert triage(repo(pushed=130, commits=500), NOW, 60)["stop"] is None
    assert triage(repo(pushed=190, commits=5000), NOW, 60)["stop"].startswith("мёртвый")
    assert triage(repo(commits=49, stars=0), NOW, 60)["stop"].startswith("игрушка")
    assert triage(repo(commits=49, stars=1), NOW, 60)["stop"] is None
    r = triage(repo(stars=5000, commits=30, pushed=7, created=10, fork=True), NOW, 60)
    assert (r["fresh"], r["pop"], r["score"]) == (4, 2, 6)
    assert r["flags"] == ["форк o/b", "stars≫commits", "новый"]
    assert triage(repo(pushed=91), NOW, 60)["fresh"] == 0


if __name__ == "__main__":
    test_triage()
    print("ok")
