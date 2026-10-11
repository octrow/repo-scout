"""Шаг 1 из docs/repo-triage.md: найти репо на GitHub, применить стоп-правила, посчитать баллы.

Usage: repo-scout "query one" "query two" [--months 6] [--new-days 60] [--limit 50] [--lang X] [--all] [--json]
Each query is GitHub search syntax (language:python, topic:x ...). Needs an authenticated `gh`.
"""
import argparse
import json
import re
import sys
from datetime import UTC, datetime, timedelta

from repo_scout import github
from repo_scout.github import GitHubError
from repo_scout.triage import triage, verdict

MAX_TEXT_CHARS, MAX_OPERATORS = 256, 5
TOKEN = re.compile(r'-?[\w-]+:"[^"]*"|"[^"]*"|\S+')
QUALIFIER = re.compile(r"-?[A-Za-z-]+:(?!//).+")
OPERATORS = {"AND", "OR", "NOT"}


def _has(tokens: list[str], name: str) -> bool:
    return any(t.startswith(f"{name}:") for t in tokens)


def build_query(q: str, *, months: int, since: str, lang: str | None) -> str:
    tokens = TOKEN.findall(q)
    parts = [q]
    if not _has(tokens, "in"):
        parts.append("in:name,description,topics,readme")
    if not _has(tokens, "mirror"):
        parts.append("mirror:false")
    if lang and not _has(tokens, "language"):
        parts.append(f"language:{lang}")
    if months and not _has(tokens, "pushed"):
        parts.append(f"pushed:>={since}")
    return " ".join(parts)


def validate_query(q: str) -> None:
    tokens = TOKEN.findall(q)
    text = " ".join(t for t in tokens if not QUALIFIER.fullmatch(t))
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"запрос {q!r}: текст без квалификаторов {len(text)} символов, лимит GitHub {MAX_TEXT_CHARS}")
    ops = sum(t in OPERATORS for t in tokens)
    if ops > MAX_OPERATORS:
        raise ValueError(f"запрос {q!r}: {ops} операторов AND/OR/NOT, лимит GitHub {MAX_OPERATORS}")


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


def run(queries: list[str], *, months: int, new_days: int, limit: int, lang: str | None, now: datetime) -> list[dict]:
    """Все строки триажа (включая отсеянные), отсортированы по баллам."""
    since = (now - timedelta(days=30 * months)).date().isoformat()
    seen = {}
    for q in queries:
        full = build_query(q, months=months, since=since, lang=lang)
        validate_query(full)
        for r in github.search(full, min(limit, 100)):
            seen.setdefault(r["nameWithOwner"], r)
    return sorted((triage(r, now, new_days) for r in seen.values()), key=lambda x: (-x["score"], x["pushed_days"]))


def main() -> None:
    if sys.argv[1:2] == ["eval"]:
        from repo_scout import evaluate
        return evaluate.main(sys.argv[2:])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", nargs="+")
    ap.add_argument("--months", type=int, default=6, help="только репо с push за N месяцев (0 = без фильтра)")
    ap.add_argument("--new-days", type=int, default=60, help="флаг «новый» для репо младше N дней")
    ap.add_argument("--limit", type=int, default=50, help="результатов на запрос (макс 100)")
    ap.add_argument("--lang", help="добавить language:<X> к каждому запросу")
    ap.add_argument("--all", action="store_true", help="показать и отсеянных стоп-правилами")
    ap.add_argument("--json", action="store_true")
    snap = ap.add_mutually_exclusive_group()
    snap.add_argument("--record", metavar="DIR", help="писать ответы GitHub в DIR")
    snap.add_argument("--replay", metavar="DIR", help="читать ответы из DIR без сети")
    a = ap.parse_args()

    try:
        github.configure("record" if a.record else "replay" if a.replay else None, a.record or a.replay)
        now = github.recorded_at() if a.replay else datetime.now(UTC)
        rows = run(a.queries, months=a.months, new_days=a.new_days, limit=a.limit, lang=a.lang, now=now)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    except GitHubError as e:
        sys.exit(f"GitHub: {e}")
    if github.last_rate_limit and not a.replay:
        rl = github.last_rate_limit
        print(f"rate limit: осталось {rl['remaining']}, сброс {rl['resetAt']}", file=sys.stderr)

    kept = [r for r in rows if not r["stop"]]
    shown = rows if a.all else kept
    if a.json:
        print(json.dumps(shown, ensure_ascii=False, indent=1))
        return
    print(to_markdown(shown))
    print(f"\nнайдено {len(rows)}, прошло стоп-правила {len(kept)}, отсеяно {len(rows) - len(kept)}"
          + ("" if a.all else " (--all чтобы показать)"))
