"""Substantive commit detection and freshness recalculation (CONTEXT.md)."""
import re
from datetime import datetime

SERVICE_BOTS = {"dependabot", "renovate", "github-actions", "pre-commit-ci", "allcontributors", "imgbot",
                "semantic-release-bot"}
AI_AGENTS = ("claude", "copilot", "codex", "devin", "cursor", "openai", "deepseek")
COSMETIC_PREFIX = re.compile(r"^(docs|chore\(deps\)|ci|style)(\(.*\))?:|^merge", re.IGNORECASE)
COSMETIC_WORDS = re.compile(r"\b(bump(ed)?|release\s+v?\d|typos?|readme)\b", re.IGNORECASE)  # small edits only
TEXT_WORDS = re.compile(r"\b(text|docs?|comments?|wording|spelling|changelog|license|format\w*)\b", re.IGNORECASE)
TINY_CHANGE = 5
WORDS_MAX_CHANGE = 100  # large commit mentioning README is treated as substantive


def is_service_bot(commit: dict) -> bool:
    author = commit.get("author") or {}
    ident = ((author.get("user") or {}).get("login") or author.get("name") or "").lower()
    if any(a in ident for a in AI_AGENTS):
        return False
    return ident.removesuffix("[bot]") in SERVICE_BOTS or ident.endswith("[bot]")


def is_cosmetic(commit: dict) -> bool:
    msg = commit.get("message") or ""
    first = msg.splitlines()[0] if msg else ""
    size = (commit.get("additions") or 0) + (commit.get("deletions") or 0)
    return (bool(COSMETIC_PREFIX.search(first))
            or (size <= WORDS_MAX_CHANGE and bool(COSMETIC_WORDS.search(first)))
            or (size <= TINY_CHANGE and bool(TEXT_WORDS.search(msg))))


def is_substantive(commit: dict) -> bool:
    return not is_service_bot(commit) and not is_cosmetic(commit)


def last_substantive(commits: list[dict], now: datetime) -> tuple[str, bool] | None:
    """(date, is_only_cosmetic): latest substantive commit or oldest in the list.
    Commits from the future (recorded snapshots after `now`) are ignored. None if no commits."""
    commits = [c for c in commits if datetime.fromisoformat(c["committedDate"]) <= now]
    if not commits:
        return None
    for c in sorted(commits, key=lambda c: c["committedDate"], reverse=True):
        if is_substantive(c):
            return c["committedDate"], False
    return min(c["committedDate"] for c in commits), True
