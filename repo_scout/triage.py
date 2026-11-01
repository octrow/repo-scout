"""Stop rules, flags, and Step 1 scoring from docs/repo-triage.md."""

from datetime import datetime

FRESH = [(7, 4), (14, 3), (30, 2), (90, 1)]  # (days since push <=, points)
POP = [(100_000, 5), (50_000, 4), (10_000, 3), (1_000, 2), (100, 1)]  # (stars >=, points)
HYPE_RATIO, HYPE_MIN_STARS = 20, 1_000  # "stars≫commits"
DEAD_DAYS, DEAD_MIN_COMMITS = 180, 500  # no push for 6 months; 4 months (2/3 of it) with < 500 commits


def dead_days(months: int) -> int:
    """Dead limit for --months: 0 (any age) turns the rule off; above 6 months it grows with --months."""
    return 0 if months == 0 else max(DEAD_DAYS, 30 * months)


def days_since(iso: str, now: datetime) -> int:
    return max(0, (now - datetime.fromisoformat(iso)).days)


def topics_of(r: dict) -> list[str]:
    nodes = (r.get("repositoryTopics") or {}).get("nodes") or []
    return [n["topic"]["name"] for n in nodes]


def _commits(r: dict) -> int:
    target = (r.get("defaultBranchRef") or {}).get("target") or {}
    return (target.get("history") or {}).get("totalCount", 0)


def _stop(pushed: int, commits: int, stars: int, dead: int) -> str | None:
    """First matching stop rule, in order: dead (off when dead == 0), toy, no code."""
    if dead and (pushed > dead or (pushed > dead * 2 // 3 and commits < DEAD_MIN_COMMITS)):
        return f"dead ({pushed}d)"
    if commits < 50 and stars == 0:
        return f"toy ({commits} commits, 0★)"
    if not commits:
        return "no code"
    return None


def _flags(r: dict, stars: int, commits: int, new: bool) -> list[str]:
    parent = (r.get("parent") or {}).get("nameWithOwner", "?")
    checks = [
        (r["isFork"], f"fork {parent}"),
        (stars >= HYPE_MIN_STARS and stars > HYPE_RATIO * max(commits, 1), "stars≫commits"),
        (r["isArchived"], "archived"),
        (new, "new"),
    ]
    return [flag for hit, flag in checks if hit]


def triage(r: dict, now: datetime, new_days: int, last_push: str | None = None, dead_days: int = DEAD_DAYS) -> dict:
    """Return the row dict with score, flags, and stop reason (None = passes).

    last_push: date of the latest substantive commit instead of pushedAt."""
    stars, commits = r["stargazerCount"], _commits(r)
    pushed = days_since(last_push or r.get("pushedAt") or r["createdAt"], now)  # pushedAt is null on never-pushed repos
    fresh = next((p for d, p in FRESH if pushed <= d), 0)
    pop = next((p for s, p in POP if stars >= s), 0)
    return {
        "repo": r["nameWithOwner"],
        "url": r["url"],
        "stars": stars,
        "forks": r["forkCount"],
        "commits": commits,
        "pushed_days": pushed,
        "created": r["createdAt"][:10],
        "topics": topics_of(r),
        "lang": (r.get("primaryLanguage") or {}).get("name", ""),
        "desc": (r.get("description") or "").replace("|", "/").replace("\n", " "),
        "score": fresh + pop,
        "fresh": fresh,
        "pop": pop,
        "flags": _flags(r, stars, commits, days_since(r["createdAt"], now) <= new_days),
        "stop": _stop(pushed, commits, stars, dead_days),
    }


def verdict(r: dict) -> str:
    return ", ".join(r["flags"] + ([f"**dropped: {r['stop']}**"] if r["stop"] else [])) or "—"
