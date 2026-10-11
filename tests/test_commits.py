from datetime import UTC, datetime

import pytest

from repo_scout.commits import (
    is_cosmetic,
    is_service_bot,
    is_substantive,
    last_substantive,
)
from repo_scout.triage import triage
from tests.test_triage import NOW, repo


def c(msg="feat: add x", login="alice", date="2026-10-01T00:00:00Z", size=50, name=None):
    return {"committedDate": date, "message": msg, "additions": size, "deletions": 0,
            "author": {"name": name or login, "user": {"login": login} if login else None}}


@pytest.mark.parametrize("login", ["dependabot[bot]", "renovate", "github-actions[bot]", "pre-commit-ci[bot]",
                                   "some-new-app[bot]"])
def test_service_bots(login):
    assert is_service_bot(c(login=login))


@pytest.mark.parametrize("login", ["claude", "copilot-swe-agent[bot]", "devin-ai-integration[bot]", "alice"])
def test_ai_agents_and_humans_are_not_bots(login):
    assert not is_service_bot(c(login=login))


def test_bot_by_author_name_when_no_user():
    assert is_service_bot(c(login=None, name="dependabot[bot]"))


@pytest.mark.parametrize("msg", ["docs: update", "chore(deps): bump x", "ci(github): fix", "Merge branch 'x'",
                                 "Fix typo", "release 1.2", "Update README"])
def test_cosmetic_messages(msg):
    assert is_cosmetic(c(msg=msg))


def test_tiny_text_edit_is_cosmetic_but_tiny_code_fix_is_not():
    assert is_cosmetic(c(msg="fix wording in comments", size=3))
    assert not is_cosmetic(c(msg="fix off-by-one", size=2))
    assert is_substantive(c(msg="feat: add parser", login="claude"))


def test_last_substantive_picks_latest():
    commits = [c(date="2026-10-05T00:00:00Z", login="dependabot[bot]"), c(date="2026-09-01T00:00:00Z"),
               c(date="2026-08-01T00:00:00Z")]
    assert last_substantive(commits, NOW) == ("2026-09-01T00:00:00Z", False)


def test_only_cosmetic_uses_oldest():
    commits = [c("docs: a", date="2026-10-05T00:00:00Z"), c("docs: b", date="2026-01-01T00:00:00Z")]
    assert last_substantive(commits, NOW) == ("2026-01-01T00:00:00Z", True)
    assert last_substantive([], NOW) is None


def test_triage_recomputes_from_last_push():
    node = repo(pushed=1, commits=100)
    assert triage(node, NOW, 60)["stop"] is None
    row = triage(node, NOW, 60, last_push=datetime(2026, 1, 1, tzinfo=UTC).isoformat())
    assert row["stop"].startswith("мёртвый") and row["pushed_days"] > 180


def test_big_commit_mentioning_readme_is_substantive():
    assert not is_cosmetic(c(msg="(v1) Update author contact and enhance README", size=600))
    assert is_cosmetic(c(msg="Update README", size=10))
    assert is_cosmetic(c(msg="docs: rewrite everything", size=900))


def test_cosmetic_words_need_boundaries():
    assert not is_cosmetic(c(msg="Fix typography rendering", size=3))
    assert not is_cosmetic(c(msg="release lock on error", size=3))
    assert not is_cosmetic(c(msg="Handle unreleased state", size=3))
    assert is_cosmetic(c(msg="Release v1.2.0", size=3))
    assert is_cosmetic(c(msg="Bump version", size=3))


def test_future_commits_ignored_and_pushed_days_clamped():
    now = datetime(2026, 10, 11, tzinfo=UTC)
    assert last_substantive([c(date="2026-12-01T00:00:00Z"), c(date="2026-09-01T00:00:00Z")], now) == (
        "2026-09-01T00:00:00Z", False)
    assert last_substantive([c(date="2026-12-01T00:00:00Z")], now) is None
    assert triage(repo(), NOW, 60, last_push="2027-01-01T00:00:00Z")["pushed_days"] == 0
