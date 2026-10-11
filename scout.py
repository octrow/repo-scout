#!/usr/bin/env python3
"""Step 1 of ~/dev/docs/repo-triage.md: find GitHub repos, apply stop rules, score them.

Usage: scout.py "query one" "query two" [--months 6] [--new-days 60] [--limit 50] [--all] [--json]
Each query is GitHub search syntax (language:python, topic:x ...). Needs an authenticated `gh`.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

GQL = """query($q:String!,$n:Int!){search(query:$q,type:REPOSITORY,first:$n){nodes{... on Repository{
nameWithOwner url description stargazerCount forkCount pushedAt createdAt isArchived isFork
parent{nameWithOwner} primaryLanguage{name}
defaultBranchRef{target{... on Commit{history{totalCount}}}}}}}}"""

FRESH = [(7, 4), (14, 3), (30, 2), (90, 1)]  # (days since push <=, points)
POP = [(100_000, 5), (50_000, 4), (10_000, 3), (1_000, 2), (100, 1)]  # (stars >=, points)
HYPE_RATIO, HYPE_MIN_STARS = 20, 1_000  # "stars≫commits"


def search(query: str, limit: int) -> list[dict]:
    out = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={GQL}", "-f", f"q={query}", "-F", f"n={limit}"],
        capture_output=True, text=True,
    )
    if out.returncode:
        sys.exit(f"gh failed for {query!r}: {out.stderr.strip()}")
    return [n for n in json.loads(out.stdout)["data"]["search"]["nodes"] if n]


def days_since(iso: str, now: datetime) -> int:
    return (now - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days


def triage(r: dict, now: datetime, new_days: int) -> dict:
    """Return the row dict with score, flags and stop reason (None = passes)."""
    stars, pushed = r["stargazerCount"], days_since(r["pushedAt"], now)
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
        "lang": (r.get("primaryLanguage") or {}).get("name", ""),
        "desc": (r.get("description") or "").replace("|", "/").replace("\n", " "),
        "score": fresh + pop, "fresh": fresh, "pop": pop, "flags": flags, "stop": stop,
    }


def verdict(r: dict) -> str:
    return ", ".join(r["flags"] + ([f"**отсев: {r['stop']}**"] if r["stop"] else [])) or "—"


def to_markdown(rows: list[dict]) -> str:
    head = "| баллы | repo | ★ | forks | комм | push, дн | создан | язык | флаги / отсев | описание |\n" + "|---" * 10 + "|"
    lines = [
        f"| {r['score']} (свеж {r['fresh']}, поп {r['pop']}) | [{r['repo']}]({r['url']}) | {r['stars']} | {r['forks']} "
        f"| {r['commits']} | {r['pushed_days']} | {r['created']} | {r['lang']} "
        f"| {verdict(r)} "
        f"| {r['desc'][:120]} |"
        for r in rows
    ]
    return "\n".join([head, *lines])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", nargs="+")
    ap.add_argument("--months", type=int, default=6, help="only repos pushed within N months (0 = no filter)")
    ap.add_argument("--new-days", type=int, default=60, help="flag repos created within N days")
    ap.add_argument("--limit", type=int, default=50, help="results per query (max 100)")
    ap.add_argument("--all", action="store_true", help="also list repos dropped by stop rules")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=30 * a.months)).date().isoformat()
    seen = {}
    for q in a.queries:
        full = q if "pushed:" in q or not a.months else f"{q} pushed:>={since}"
        for r in search(full, min(a.limit, 100)):
            seen.setdefault(r["nameWithOwner"], r)

    rows = sorted((triage(r, now, a.new_days) for r in seen.values()), key=lambda x: (-x["score"], x["pushed_days"]))
    kept = [r for r in rows if not r["stop"]]
    shown = rows if a.all else kept
    if a.json:
        print(json.dumps(shown, ensure_ascii=False, indent=1))
        return
    print(to_markdown(shown))
    print(f"\nнайдено {len(rows)}, прошло стоп-правила {len(kept)}, отсеяно {len(rows) - len(kept)}"
          + ("" if a.all else " (--all чтобы показать)"))


if __name__ == "__main__":
    main()
