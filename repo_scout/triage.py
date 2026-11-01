"""Stop rules, flags, and Step 1 scoring from docs/repo-triage.md."""

from datetime import datetime

FRESH = [(7, 4), (14, 3), (30, 2), (90, 1)]  # (days since push <=, points)
POP = [(100_000, 5), (50_000, 4), (10_000, 3), (1_000, 2), (100, 1)]  # (stars >=, points)
HYPE_RATIO, HYPE_MIN_STARS = 20, 1_000  # "stars≫commits"


def days_since(iso: str, now: datetime) -> int:
    return max(0, (now - datetime.fromisoformat(iso)).days)


def topics_of(r: dict) -> list[str]:
    nodes = (r.get("repositoryTopics") or {}).get("nodes") or []
    return [n["topic"]["name"] for n in nodes]


def _commits(r: dict) -> int:
    target = (r.get("defaultBranchRef") or {}).get("target") or {}
    return (target.get("history") or {}).get("totalCount", 0)


def _stop(pushed: int, commits: int, stars: int) -> str | None:
    """First matching stop rule, in order: dead, toy, no code."""
    if pushed > 180 or (pushed > 120 and commits < 500):
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


def triage(r: dict, now: datetime, new_days: int, last_push: str | None = None) -> dict:
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
        "stop": _stop(pushed, commits, stars),
    }


def verdict(r: dict) -> str:
    return ", ".join(r["flags"] + ([f"**dropped: {r['stop']}**"] if r["stop"] else [])) or "—"
