"""Шаг 1 из docs/repo-triage.md: найти репо на GitHub, применить стоп-правила, посчитать баллы.

Usage: repo-scout --task "<English task description>" "query one" "query two" [--min-closeness 0.6] [--months 6] [--new-days 60] [--limit 50] [--lang X] [--exclude RE] [--must RE] [--no-round2] [--round2-k 10] [--stars-k 10] [--no-stars-check] [--all] [--json]
Each query is GitHub search syntax (language:python, topic:x ...). Needs an authenticated `gh`.
"""
import argparse
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from repo_scout import github, runs, semantic, stars
from repo_scout import log as logmod
from repo_scout.command import parse_command, search_params, to_argv  # noqa: F401  (реэкспорт)
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
from repo_scout.log import log
from repo_scout.noise import is_template, noise_stop
from repo_scout.round2 import ROUND2_K, pick_topics
from repo_scout.triage import triage, verdict

MAX_TEXT_CHARS, MAX_OPERATORS = 256, 5
TOKEN = re.compile(r'-?[\w-]+:"[^"]*"|"[^"]*"|\S+')
QUALIFIER = re.compile(r"-?[A-Za-z-]+:(?!//).+")
OPERATORS = {"AND", "OR", "NOT"}
MUST_STOP = "нет обязательного"
STARS_K = 10
FROM_INDEX = 50  # сколько ближайших из Индекса добавлять в Пул
last_round2_topics: list[str] = []  # слаги второго круга последнего run(); для сохранения в Прогон


def _has(tokens: list[str], name: str) -> bool:
    return any(t.startswith(f"{name}:") for t in tokens)


def build_query(q: str, *, months: int, since: str, lang: str | None) -> str:
    tokens = TOKEN.findall(q)
    parts = [q]
    if not _has(tokens, "in") and not all(QUALIFIER.fullmatch(t) for t in tokens):  # `in:` относится к тексту
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
    log.info("Близость: эмбеддинг %d кандидатов", len(todo))
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
        if name not in fresh and name not in github.last_failed:
            index.forget(name)  # удалено на GitHub
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
    return (-(-1.0 if c is None else c), -r.get("score", 0), r.get("pushed_days", 0))


def _process(nodes: dict, live: set[str], source: str, *, now: datetime, new_days: int, lang: str | None,
             exclude: list[re.Pattern], must: list[re.Pattern], task: str | None, min_closeness: float,
             index: Index | None, known: dict[str, dict]) -> list[dict]:
    """Конвейер для набора узлов: триаж, шум, условия, детали, Близость, порог, запись в Индекс."""
    log.info("конвейер (%s): %d кандидатов", source, len(nodes))
    rows = [triage(n, now, new_days) for n in nodes.values()]
    for r in rows:
        r["source"] = source if r["repo"] in live else "индекс"
    _screen_meta(rows, nodes, lang, exclude)
    readmes = _screen_details(rows, nodes, now, new_days, exclude, must, known)
    if task:
        vecs = add_closeness(rows, readmes, task)
        if index:
            for r in rows:
                if r["repo"] in vecs and readmes.get(r["repo"]):
                    index.upsert(r, readmes[r["repo"]], vecs[r["repo"]], now)
        apply_closeness(rows, min_closeness)
    return rows


def _search_all(queries: list[str], *, months: int, since: str, lang: str | None, limit: int, into: dict) -> None:
    for i, q in enumerate(queries, 1):
        full = build_query(q, months=months, since=since, lang=lang)
        validate_query(full)
        found = github.search(full, min(limit, 100))
        for r in found:
            into.setdefault(r["nameWithOwner"], r)
        log.info("поиск %d/%d: %s → %d (пул %d)", i, len(queries), q, len(found), len(into))


def _round2(rows: list[dict], queries: list[str], pool: dict, *, k: int, floor: float, lang: str | None,
            months: int, since: str, limit: int) -> tuple[dict, list[str]]:
    """Новые узлы по `topic:`-Запросам из топ-k прошедших строк (Близость не ниже floor)."""
    top = sorted((r for r in rows if not r["stop"] and (r.get("closeness") or 0) >= floor), key=sort_key)[:k]
    topics = pick_topics(top, queries)
    found: dict = {}
    _search_all([f"topic:{t}" for t in topics], months=months, since=since, lang=lang, limit=limit, into=found)
    lower = {n.lower() for n in pool}
    return {n: v for n, v in found.items() if n.lower() not in lower}, topics


def run(queries: list[str], *, months: int, new_days: int, limit: int, lang: str | None, now: datetime,
        exclude: list[re.Pattern] = (), must: list[re.Pattern] = (), task: str | None = None,
        min_closeness: float = semantic.MIN_CLOSENESS, index: Index | None = None,
        from_index: int = FROM_INDEX, round2: bool = True, round2_k: int = ROUND2_K, stars_k: int = 0) -> list[dict]:
    """Все строки триажа (включая отсеянные), отсортированы по Близости, потом по баллам."""
    global last_round2_topics
    last_round2_topics = []
    since = (now - timedelta(days=30 * months)).date().isoformat()
    nodes: dict = {}
    _search_all(queries, months=months, since=since, lang=lang, limit=limit, into=nodes)
    live = set(nodes)
    known = _from_index(index, task, nodes, from_index) if index and task and from_index else {}
    kw = {"now": now, "new_days": new_days, "lang": lang, "exclude": list(exclude), "must": list(must),
          "task": task, "min_closeness": min_closeness, "index": index}
    rows = _process(nodes, live, "запрос", known=known, **kw)
    if task and round2:
        extra, topics = _round2(rows, queries, nodes, k=round2_k, floor=max(min_closeness, semantic.MIN_CLOSENESS),
                                lang=lang, months=months, since=since, limit=limit)
        last_round2_topics = topics
        log.info("второй круг: topics %s → новых %d", ", ".join(topics) or "—", len(extra))
        rows += _process(extra, set(extra), "второй круг", known={}, **kw)
    if index:
        seen = index.seen([r["repo"] for r in rows])
        for r in rows:
            r["seen"] = seen.get(r["repo"].lower(), "")
    rows.sort(key=sort_key)
    add_stars_flag(rows, stars_k, now)
    return rows


def add_stars_flag(rows: list[dict], k: int, now: datetime) -> None:
    """Флаг «всплеск★» топ-k выжившим строкам с ≥50★ (после Близости; баллы не меняет)."""
    top = [r for r in rows if not r["stop"] and r["stars"] >= stars.MIN_STARS][:k]
    for r in top:
        try:
            text = stars.flag(stars.history(r["repo"], now))
        except GitHubError as e:  # флаг вторичен: сбой не должен ронять прогон
            log.warning("предупреждение: флаг «всплеск★» для %s пропущен: %s", r["repo"], e)
            continue
        if text:
            r["flags"].append(text)


def draft_params(d, need: str) -> dict:
    """Параметры поиска из Черновика LLM (остальное по умолчанию парсера)."""
    params = search_params(_parser().parse_args(["--task", "x", "q"]))
    params.update(task=d.task, queries=list(d.queries), must=list(d.must), exclude=list(d.exclude),
                  lang=d.lang, need=need.strip())
    return params


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


def draft_main(argv: list[str]) -> None:
    """`repo-scout draft "<потребность>"`: Черновик LLM одной строкой `repo-scout …`."""
    import shlex

    from repo_scout import llm
    ap = argparse.ArgumentParser(prog="repo-scout draft")
    ap.add_argument("need", help="Потребность своими словами, на любом языке")
    a = ap.parse_args(argv)
    if not llm.available():
        sys.exit(f"draft: {llm.NO_KEY}")
    logmod.setup(quiet=True)
    try:
        d = llm.draft(a.need)
    except llm.LLMError as e:
        sys.exit(f"draft: {e}")
    print(shlex.join(["repo-scout", *to_argv(draft_params(d, a.need))]))


def main() -> None:
    if sys.argv[1:2] == ["eval"]:
        from repo_scout import evaluate
        return evaluate.main(sys.argv[2:])
    if sys.argv[1:2] == ["gui"] or not sys.argv[1:]:  # без аргументов — GUI
        from repo_scout.gui import app  # лениво: CLI не импортирует nicegui
        return app.main(sys.argv[2:])
    if sys.argv[1:2] == ["verdict"]:
        return verdict_main(sys.argv[2:])
    if sys.argv[1:2] == ["draft"]:
        return draft_main(sys.argv[2:])
    a = _parser().parse_args()
    logmod.setup(quiet=a.quiet)
    _main(a)


class _Parser(argparse.ArgumentParser):
    raise_errors = False  # parse_command: ошибки — ValueError, без SystemExit и stderr

    def error(self, message: str):
        if self.raise_errors:
            raise ValueError(message)
        super().error(message)


def _parser() -> argparse.ArgumentParser:
    ap = _Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
    ap.add_argument("--round2-k", type=int, default=ROUND2_K, metavar="K",
                    help="второй круг берёт topics из топ-K (по умолчанию %(default)s)")
    ap.add_argument("--stars-k", type=int, default=STARS_K, metavar="K",
                    help="флаг «всплеск★» для топ-K с ≥50★ (по умолчанию %(default)s)")
    ap.add_argument("--no-stars-check", action="store_true", help="без флага «всплеск★» (REST-история звёзд)")
    ap.add_argument("--no-round2", action="store_true", help="без второго круга (`topic:` из топ-K)")
    ap.add_argument("--project", help="проект, для которого поиск (сохраняется в Прогон)")
    ap.add_argument("--need", metavar="TEXT", help="Потребность своими словами (только сохраняется в Прогон, поиск не использует)")
    ap.add_argument("--out", metavar="PATH", help="путь файла Прогона (по умолчанию каталог Прогонов)")
    ap.add_argument("--no-save", action="store_true", help="не сохранять Прогон")
    ap.add_argument("--all", action="store_true", help="показать и отсеянных стоп-правилами")
    ap.add_argument("--json", action="store_true")
    snap = ap.add_mutually_exclusive_group()
    snap.add_argument("--record", metavar="DIR", help="писать ответы GitHub в DIR")
    snap.add_argument("--replay", metavar="DIR", help="читать ответы из DIR без сети")
    ap.add_argument("-q", "--quiet", action="store_true", help="ход работы только в лог-файл, в stderr — предупреждения")
    return ap


def _save_run(a: argparse.Namespace, rows: list[dict], now: datetime) -> None:
    if a.no_save or a.record or a.replay:
        return
    try:
        path = runs.save(search_params(a), rows, last_round2_topics, now, Path(a.out) if a.out else None)
    except OSError as e:
        log.warning("Прогон не сохранён: %s", e)
        return
    log.info("Прогон сохранён: %s", path)


def _main(a: argparse.Namespace) -> None:
    try:
        exclude, must = compile_all("--exclude", a.exclude), compile_all("--must", a.must)
        github.configure("record" if a.record else "replay" if a.replay else None, a.record or a.replay)
        now = github.recorded_at() if a.replay else datetime.now(UTC)
        rows = run(a.queries, months=a.months, new_days=a.new_days, limit=a.limit, lang=a.lang, now=now,
                   exclude=exclude, must=must, task=a.task, min_closeness=a.min_closeness,
                   index=None if a.record or a.replay else Index(default_path()), from_index=a.from_index,
                   round2=not a.no_round2, round2_k=a.round2_k,
                   stars_k=0 if a.no_stars_check else a.stars_k)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    except GitHubError as e:
        sys.exit(f"GitHub: {e}")
    if github.last_rate_limit and not a.replay:
        rl = github.last_rate_limit
        log.info("rate limit: осталось %s, сброс %s", rl["remaining"], rl["resetAt"])

    kept = [r for r in rows if not r["stop"]]
    by_must = [r for r in rows if (r["stop"] or "").startswith(MUST_STOP)]
    shown = [r for r in (rows if a.all else kept) if r not in by_must]
    if a.json:
        print(json.dumps({"rows": shown, "dropped_by_must": by_must}, ensure_ascii=False, indent=1))
        _save_run(a, rows, now)
        return
    print(to_markdown(shown))
    if by_must:
        print("\nотсеяно по --must: " + ", ".join(r["repo"] for r in by_must))
    print(f"\nнайдено {len(rows)}, прошло стоп-правила {len(kept)}, отсеяно {len(rows) - len(kept)}"
          + ("" if a.all else " (--all чтобы показать)"))
    _save_run(a, rows, now)
