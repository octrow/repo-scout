"""Стоп-правила, флаги и баллы Шага 1 из docs/repo-triage.md."""
from datetime import datetime

FRESH = [(7, 4), (14, 3), (30, 2), (90, 1)]  # (days since push <=, points)
POP = [(100_000, 5), (50_000, 4), (10_000, 3), (1_000, 2), (100, 1)]  # (stars >=, points)
HYPE_RATIO, HYPE_MIN_STARS = 20, 1_000  # "stars≫commits"


def days_since(iso: str, now: datetime) -> int:
    return max(0, (now - datetime.fromisoformat(iso)).days)


def topics_of(r: dict) -> list[str]:
    nodes = (r.get("repositoryTopics") or {}).get("nodes") or []
    return [n["topic"]["name"] for n in nodes]


def triage(r: dict, now: datetime, new_days: int, last_push: str | None = None) -> dict:
    """Return the row dict with score, flags and stop reason (None = passes).

    last_push: дата последнего содержательного коммита вместо pushedAt."""
    stars, pushed = r["stargazerCount"], days_since(last_push or r["pushedAt"], now)
    target = (r.get("defaultBranchRef") or {}).get("target") or {}
    commits = (target.get("history") or {}).get("totalCount", 0)

    stop = None
    if pushed > 180 or (pushed > 120 and commits < 500):
        stop = f"мёртвый ({pushed} дн)"
    elif commits < 50 and stars == 0:
        stop = f"игрушка ({commits} комм, 0★)"
    elif not commits:
        stop = "нет кода"

    flags = []
    if r["isFork"]:
        flags.append(f"форк {(r.get('parent') or {}).get('nameWithOwner', '?')}")
    if stars >= HYPE_MIN_STARS and stars > HYPE_RATIO * max(commits, 1):
        flags.append("stars≫commits")
    if r["isArchived"]:
        flags.append("archived")
    if days_since(r["createdAt"], now) <= new_days:
        flags.append("новый")

    fresh = next((p for d, p in FRESH if pushed <= d), 0)
    pop = next((p for s, p in POP if stars >= s), 0)
    return {
        "repo": r["nameWithOwner"], "url": r["url"], "stars": stars, "forks": r["forkCount"],
        "commits": commits, "pushed_days": pushed, "created": r["createdAt"][:10],
        "topics": topics_of(r), "lang": (r.get("primaryLanguage") or {}).get("name", ""),
        "desc": (r.get("description") or "").replace("|", "/").replace("\n", " "),
        "score": fresh + pop, "fresh": fresh, "pop": pop, "flags": flags, "stop": stop,
    }


def verdict(r: dict) -> str:
    return ", ".join(r["flags"] + ([f"**отсев: {r['stop']}**"] if r["stop"] else [])) or "—"
