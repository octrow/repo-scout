"""Шаг 1 из docs/repo-triage.md: найти репо на GitHub, применить стоп-правила, посчитать баллы.

Usage: repo-scout --task "<English task description>" "query one" "query two" [--min-closeness 0.6] [--months 6] [--new-days 60] [--limit 50] [--lang X] [--exclude RE] [--must RE] [--all] [--json]
Each query is GitHub search syntax (language:python, topic:x ...). Needs an authenticated `gh`.
"""
import argparse
import json
import re
import sys
from datetime import UTC, datetime, timedelta

import numpy as np

from repo_scout import github, semantic
from repo_scout.commits import last_substantive
from repo_scout.conditions import (
    compile_all,
    exclude_stop,
    lang_stop,
    meta_text,
    must_stop,
)
from repo_scout.github import GitHubError
from repo_scout.index import Index, default_path, validate_verdict
from repo_scout.noise import is_template, noise_stop
from repo_scout.triage import triage, verdict

MAX_TEXT_CHARS, MAX_OPERATORS = 256, 5
TOKEN = re.compile(r'-?[\w-]+:"[^"]*"|"[^"]*"|\S+')
QUALIFIER = re.compile(r"-?[A-Za-z-]+:(?!//).+")
OPERATORS = {"AND", "OR", "NOT"}
MUST_STOP = "нет обязательного"
FROM_INDEX = 50  # сколько ближайших из Индекса добавлять в Пул


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


def _fmt_close(r: dict) -> str:
    return "—" if r.get("closeness") is None else f"{r['closeness']:.2f}"


def to_markdown(rows: list[dict]) -> str:
    head = "| близ | источник | баллы | repo | ★ | forks | комм | push, дн | создан | язык | флаги / отсев | уже смотрели | описание |\n" + "|---" * 13 + "|"
    lines = [
        f"| {_fmt_close(r)} | {r['source']} | {r['score']} (свеж {r['fresh']}, поп {r['pop']}) | [{r['repo']}]({r['url']}) | {r['stars']} | {r['forks']} "
        f"| {r['commits']} | {r['pushed_days']} | {r['created']} | {r['lang']} "
        f"| {verdict(r)} | {r.get('seen') or '—'} "
        f"| {r['desc'][:120]} |"
        for r in rows
    ]
    return "\n".join([head, *lines])


def _stop(row: dict, reason: str | None) -> None:
    if reason and not row["stop"]:
        row["stop"] = reason


def _screen_meta(rows: list[dict], nodes: dict, lang: str | None, exclude: list[re.Pattern]) -> None:
    """Шум, шаблон, язык и запрещённые слова по метаданным."""
    for row in filter(lambda r: not r["stop"], rows):
        node = nodes[row["repo"]]
        if is_template(node):
            row["flags"].append("шаблон")
        _stop(row, noise_stop(node))
        _stop(row, lang_stop(row, lang))
        _stop(row, exclude_stop(meta_text(row), exclude))


def _screen_details(rows: list[dict], nodes: dict, now: datetime, new_days: int,
                    exclude: list[re.Pattern], must: list[re.Pattern],
                    known: dict[str, dict]) -> dict[str, str | None]:
    """README и коммиты выживших: пересчёт свежести, запрещённые и обязательные слова. Возвращает README."""
    readmes: dict[str, str | None] = {}
    alive = [r for r in rows if not r["stop"]]
    names = [r["repo"] for r in alive]
    info = {n: known[n] for n in names if n in known}
    info.update(github.details([n for n in names if n not in known]))
    for row in alive:
        d = info.get(row["repo"])
        if d is None:
            row["flags"].append("нет деталей")
            continue
        if found := last_substantive(d["commits"], now):
            date, cosmetic_only = found
            new = triage(nodes[row["repo"]], now, new_days, last_push=date)
            row.update({k: new[k] for k in ("pushed_days", "fresh", "score", "stop")})
            if cosmetic_only:
                row["flags"].append("только косметика")
        readme = readmes[row["repo"]] = d["readme"]
        if readme is None:
            row["flags"].append("нет README")
        _stop(row, exclude_stop(readme or "", exclude))
        if readme is not None:
            _stop(row, must_stop(" ".join([readme, meta_text(row)]), must))
    return readmes


def add_closeness(rows: list[dict], readmes: dict[str, str | None], task: str) -> dict[str, np.ndarray]:
    """Близость строкам, не отсеянным к этому моменту (нет README: имя, описание, topics). Возвращает векторы."""
    todo = [r for r in rows if not r["stop"]]
    if not todo:
        return {}
    docs = semantic.embed_docs([semantic.candidate_text(r, readmes.get(r["repo"])) for r in todo])
    for r, c in zip(todo, semantic.closeness(semantic.embed_task(task), docs)):
        r["closeness"] = float(c)
    return {r["repo"]: d for r, d in zip(todo, docs)}


def _from_index(index: Index, task: str, nodes: dict, n: int) -> dict[str, dict]:
    """Топ-n из Индекса, которых нет в живой выдаче: свежие метаданные и детали одним пакетным запросом."""
    live = {k.lower() for k in nodes}
    wanted = [m for m in index.top(task, n) if m.lower() not in live]
    fresh = github.refresh(wanted)
    for name in wanted:
        if name not in fresh:
            index.forget(name)  # удалено (или недоступно) на GitHub
        elif (new := fresh[name]["node"]["nameWithOwner"]).lower() != name.lower():
            index.rename(name, new)
    for d in fresh.values():
        nodes.setdefault(d["node"]["nameWithOwner"], d["node"])
    return {d["node"]["nameWithOwner"]: d["details"] for d in fresh.values()}


def apply_closeness(rows: list[dict], min_closeness: float) -> None:
    for r in rows:
        if r.get("closeness") is not None and r["closeness"] < min_closeness:
            _stop(r, f"не по теме ({r['closeness']:.2f})")


def sort_key(r: dict) -> tuple:
    c = r.get("closeness")
    return (-(-1.0 if c is None else c), -r["score"], r["pushed_days"])


def run(queries: list[str], *, months: int, new_days: int, limit: int, lang: str | None, now: datetime,
        exclude: list[re.Pattern] = (), must: list[re.Pattern] = (), task: str | None = None,
        min_closeness: float = semantic.MIN_CLOSENESS, index: Index | None = None,
        from_index: int = FROM_INDEX) -> list[dict]:
    """Все строки триажа (включая отсеянные), отсортированы по Близости, потом по баллам."""
    since = (now - timedelta(days=30 * months)).date().isoformat()
    nodes = {}
    for q in queries:
        full = build_query(q, months=months, since=since, lang=lang)
        validate_query(full)
        for r in github.search(full, min(limit, 100)):
            nodes.setdefault(r["nameWithOwner"], r)
    live = set(nodes)
    known = _from_index(index, task, nodes, from_index) if index and task and from_index else {}
    rows = [triage(n, now, new_days) for n in nodes.values()]
    for r in rows:
        r["source"] = "запрос" if r["repo"] in live else "индекс"
    _screen_meta(rows, nodes, lang, list(exclude))
    readmes = _screen_details(rows, nodes, now, new_days, list(exclude), list(must), known)
    if task:
        vecs = add_closeness(rows, readmes, task)
        if index:
            for r in rows:
                if r["repo"] in vecs and readmes.get(r["repo"]):
                    index.upsert(r, readmes[r["repo"]], vecs[r["repo"]], now)
        apply_closeness(rows, min_closeness)
    if index:
        seen = index.seen([r["repo"] for r in rows])
        for r in rows:
            r["seen"] = seen.get(r["repo"].lower(), "")
    return sorted(rows, key=sort_key)


def verdict_main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="repo-scout verdict")
    ap.add_argument("repo", metavar="owner/repo")
    ap.add_argument("verdict", help="«→ Осмотр», «→ Разбор (цель)», «отсев (причина)», «спорно (что уточнить)»")
    ap.add_argument("--project", required=True)
    ap.add_argument("--task", required=True, help="кратко, о какой задаче проекта")
    a = ap.parse_args(argv)
    try:
        validate_verdict(a.repo, a.verdict, a.project, a.task)
    except ValueError as e:
        sys.exit(f"verdict: {e}")
    Index(default_path()).add_verdict(a.repo, a.verdict, a.project, a.task)
    print(f"записано: {a.repo} — {a.verdict} ({a.project})")


def main() -> None:
    if sys.argv[1:2] == ["eval"]:
        from repo_scout import evaluate
        return evaluate.main(sys.argv[2:])
    if sys.argv[1:2] == ["verdict"]:
        return verdict_main(sys.argv[2:])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", nargs="+")
    ap.add_argument("--task", required=True, metavar="TEXT",
                    help="Описание задачи (1-3 фразы на английском): по нему считается Близость")
    ap.add_argument("--min-closeness", type=float, default=semantic.MIN_CLOSENESS, metavar="FLOAT",
                    help="ниже порога Близости: стоп «не по теме» (по умолчанию %(default)s)")
    ap.add_argument("--months", type=int, default=6, help="только репо с push за N месяцев (0 = без фильтра)")
    ap.add_argument("--new-days", type=int, default=60, help="флаг «новый» для репо младше N дней")
    ap.add_argument("--limit", type=int, default=50, help="результатов на запрос (макс 100)")
    ap.add_argument("--lang", help="добавить language:<X> к каждому запросу")
    ap.add_argument("--exclude", action="append", default=[], metavar="REGEX",
                    help="отсев, если REGEX найден в имени, описании, topics или README (можно повторять)")
    ap.add_argument("--must", action="append", default=[], metavar="REGEX",
                    help="группа обязательных слов в README, topics, описании; нужны все группы (можно повторять)")
    ap.add_argument("--from-index", type=int, default=FROM_INDEX, metavar="N",
                    help="добавить в Пул N ближайших из Индекса (0 = выключить, по умолчанию %(default)s)")
    ap.add_argument("--all", action="store_true", help="показать и отсеянных стоп-правилами")
    ap.add_argument("--json", action="store_true")
    snap = ap.add_mutually_exclusive_group()
    snap.add_argument("--record", metavar="DIR", help="писать ответы GitHub в DIR")
    snap.add_argument("--replay", metavar="DIR", help="читать ответы из DIR без сети")
    a = ap.parse_args()

    try:
        exclude, must = compile_all("--exclude", a.exclude), compile_all("--must", a.must)
        github.configure("record" if a.record else "replay" if a.replay else None, a.record or a.replay)
        now = github.recorded_at() if a.replay else datetime.now(UTC)
        rows = run(a.queries, months=a.months, new_days=a.new_days, limit=a.limit, lang=a.lang, now=now,
                   exclude=exclude, must=must, task=a.task, min_closeness=a.min_closeness,
                   index=None if a.record or a.replay else Index(default_path()), from_index=a.from_index)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    except GitHubError as e:
        sys.exit(f"GitHub: {e}")
    if github.last_rate_limit and not a.replay:
        rl = github.last_rate_limit
        print(f"rate limit: осталось {rl['remaining']}, сброс {rl['resetAt']}", file=sys.stderr)

    kept = [r for r in rows if not r["stop"]]
    by_must = [r for r in rows if (r["stop"] or "").startswith(MUST_STOP)]
    shown = [r for r in (rows if a.all else kept) if r not in by_must]
    if a.json:
        print(json.dumps({"rows": shown, "dropped_by_must": by_must}, ensure_ascii=False, indent=1))
        return
    print(to_markdown(shown))
    if by_must:
        print("\nотсеяно по --must: " + ", ".join(r["repo"] for r in by_must))
    print(f"\nнайдено {len(rows)}, прошло стоп-правила {len(kept)}, отсеяно {len(rows) - len(kept)}"
          + ("" if a.all else " (--all чтобы показать)"))
