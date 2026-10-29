"""Search GitHub for repos you can build on, drop dead and off-topic ones, rank the rest by closeness to your task.

Usage: repo-scout --task "<task in English>" "query one" "query two" [options]
Each query uses GitHub search syntax (language:python, topic:x ...).
Needs the GitHub CLI (gh), logged in. Check with: repo-scout doctor
Other commands: repo-scout gui | doctor | config | draft | verdict | eval
"""
import argparse
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from repo_scout import github, runs, semantic, stars, systemone
from repo_scout import log as logmod
from repo_scout.command import parse_command, search_params, to_argv  # noqa: F401  (re-export)
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
MUST_STOP = "missing required"
STARS_K = 10
FROM_INDEX = 50  # number of closest repos from Index to add to pool
last_round2_topics: list[str] = []  # round two slugs from last run(); saved to Run


def _has(tokens: list[str], name: str) -> bool:
    return any(t.startswith(f"{name}:") for t in tokens)


def build_query(q: str, *, months: int, since: str, lang: str | None) -> str:
    tokens = TOKEN.findall(q)
    parts = [q]
    if not _has(tokens, "in") and not all(QUALIFIER.fullmatch(t) for t in tokens):
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
        raise ValueError(f"query {q!r}: the text without qualifiers has {len(text)} chars. GitHub allows {MAX_TEXT_CHARS}")
    ops = sum(t in OPERATORS for t in tokens)
    if ops > MAX_OPERATORS:
        raise ValueError(f"query {q!r}: {ops} AND/OR/NOT operators. GitHub allows {MAX_OPERATORS}")


def _fmt_close(r: dict) -> str:
    return "—" if r.get("closeness") is None else f"{r['closeness']:.2f}"


def _fmt_fit(r: dict) -> str:
    return f" {r.get('fit', '—')} |"


def to_markdown(rows: list[dict]) -> str:
    fit = any("fit" in r for r in rows)  # advanced mode: a fit column right after closeness
    cols = ["close", *(["fit"] if fit else []), "source", "score", "repo", "★", "forks", "commits", "pushed, d",
            "created", "lang", "flags / stop", "seen", "desc"]
    head = "| " + " | ".join(cols) + " |\n" + "|---" * len(cols) + "|"
    lines = [
        f"| {_fmt_close(r)} |{_fmt_fit(r) if fit else ''} {r['source']} "
        f"| {r['score']} (fresh {r['fresh']}, pop {r['pop']}) | [{r['repo']}]({r['url']}) | {r['stars']} | {r['forks']} "
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
    """Noise, template, language, and forbidden words based on metadata."""
    for row in filter(lambda r: not r["stop"], rows):
        node = nodes[row["repo"]]
        if is_template(node):
            row["flags"].append("template")
        _stop(row, noise_stop(node))
        _stop(row, lang_stop(row, lang))
        _stop(row, exclude_stop(meta_text(row), exclude))


def _screen_details(rows: list[dict], nodes: dict, now: datetime, new_days: int,
                    exclude: list[re.Pattern], must: list[re.Pattern],
                    known: dict[str, dict]) -> dict[str, str | None]:
    """README and commits for survivors: freshness recheck, forbidden and required words. Returns READMEs."""
    readmes: dict[str, str | None] = {}
    alive = [r for r in rows if not r["stop"]]
    names = [r["repo"] for r in alive]
    info = {n: known[n] for n in names if n in known}
    info.update(github.details([n for n in names if n not in known]))
    for row in alive:
        d = info.get(row["repo"])
        if d is None:
            row["flags"].append("no details")
            continue
        if found := last_substantive(d["commits"], now):
            date, cosmetic_only = found
            new = triage(nodes[row["repo"]], now, new_days, last_push=date)
            row.update({k: new[k] for k in ("pushed_days", "fresh", "score", "stop")})
            if cosmetic_only:
                row["flags"].append("cosmetic only")
        readme = readmes[row["repo"]] = d["readme"]
        if readme is None:
            row["flags"].append("no README")
        _stop(row, exclude_stop(readme or "", exclude))
        if readme is not None:
            _stop(row, must_stop(" ".join([readme, meta_text(row)]), must))
    return readmes


def add_closeness(rows: list[dict], readmes: dict[str, str | None], task: str) -> dict[str, np.ndarray]:
    """Compute closeness for non-dropped rows (name, desc, topics if no README). Returns vectors."""
    todo = [r for r in rows if not r["stop"]]
    if not todo:
        return {}
    log.info("closeness: embedding %d candidates", len(todo))
    docs = semantic.embed_docs([semantic.candidate_text(r, readmes.get(r["repo"])) for r in todo])
    for r, c in zip(todo, semantic.closeness(semantic.embed_task(task), docs)):
        r["closeness"] = float(c)
    return {r["repo"]: d for r, d in zip(todo, docs)}


def _from_index(index: Index, task: str, nodes: dict, n: int) -> dict[str, dict]:
    """Top-n from Index not in live results: fresh metadata and details via a single batch request."""
    live = {k.lower() for k in nodes}
    wanted = [m for m in index.top(task, n) if m.lower() not in live]
    fresh = github.refresh(wanted)
    for name in wanted:
        if name in fresh:
            if (new := fresh[name]["node"]["nameWithOwner"]).lower() != name.lower():
                index.rename(name, new)
        elif name not in github.last_failed:
            index.forget(name)  # deleted on GitHub
    for d in fresh.values():
        nodes.setdefault(d["node"]["nameWithOwner"], d["node"])
    return {d["node"]["nameWithOwner"]: d["details"] for d in fresh.values()}


def apply_closeness(rows: list[dict], min_closeness: float) -> None:
    for r in rows:
        if r.get("closeness") is not None and r["closeness"] < min_closeness:
            _stop(r, f"off-topic ({r['closeness']:.2f})")


def sort_key(r: dict) -> tuple:
    c = r.get("closeness")
    return (-(-1.0 if c is None else c), -r.get("score", 0), r.get("pushed_days", 0))


def _process(nodes: dict, live: set[str], source: str, *, now: datetime, new_days: int, lang: str | None,
             exclude: list[re.Pattern], must: list[re.Pattern], task: str | None, min_closeness: float,
             index: Index | None, known: dict[str, dict], texts: dict[str, str] | None = None) -> list[dict]:
    """Pipeline for a set of nodes: triage, noise, conditions, details, closeness, threshold, index upsert.
    `texts` collects candidate texts of rows that passed, for the optional fit column."""
    log.info("pipeline (%s): %d candidates", source, len(nodes))
    rows = [triage(n, now, new_days) for n in nodes.values()]
    for r in rows:
        r["source"] = source if r["repo"] in live else "index"
    _screen_meta(rows, nodes, lang, exclude)
    readmes = _screen_details(rows, nodes, now, new_days, exclude, must, known)
    if task:
        vecs = add_closeness(rows, readmes, task)
        if index:
            for r in rows:
                if r["repo"] in vecs and readmes.get(r["repo"]):
                    index.upsert(r, readmes[r["repo"]], vecs[r["repo"]], now)
        apply_closeness(rows, min_closeness)
        if texts is not None:
            texts.update({r["repo"]: semantic.candidate_text(r, readmes.get(r["repo"])) for r in rows if not r["stop"]})
    return rows


def _search_all(queries: list[str], *, months: int, since: str, lang: str | None, limit: int, into: dict) -> None:
    for i, q in enumerate(queries, 1):
        full = build_query(q, months=months, since=since, lang=lang)
        validate_query(full)
        found = github.search(full, min(limit, 100))
        for r in found:
            into.setdefault(r["nameWithOwner"], r)
        log.info("search %d/%d: %s → %d (pool %d)", i, len(queries), q, len(found), len(into))


def _round2(rows: list[dict], queries: list[str], pool: dict, *, k: int, floor: float, lang: str | None,
            months: int, since: str, limit: int) -> tuple[dict, list[str]]:
    """New nodes via `topic:` queries from top-k surviving rows (closeness not below floor)."""
    top = sorted((r for r in rows if not r["stop"] and (r.get("closeness") or 0) >= floor), key=sort_key)[:k]
    topics = pick_topics(top, queries)
    found: dict = {}
    _search_all([f"topic:{t}" for t in topics], months=months, since=since, lang=lang, limit=limit, into=found)
    lower = {n.lower() for n in pool}
    return {n: v for n, v in found.items() if n.lower() not in lower}, topics


def run(queries: list[str], *, months: int, new_days: int, limit: int, lang: str | None, now: datetime,
        exclude: list[re.Pattern] = (), must: list[re.Pattern] = (), task: str | None = None,
        min_closeness: float = semantic.MIN_CLOSENESS, index: Index | None = None,
        from_index: int = FROM_INDEX, round2: bool = True, round2_k: int = ROUND2_K, stars_k: int = 0,
        fit_k: int = 0) -> list[dict]:
    """All triage rows (including dropped), sorted by closeness, then score."""
    global last_round2_topics
    last_round2_topics = []
    since = (now - timedelta(days=30 * months)).date().isoformat()
    nodes: dict = {}
    _search_all(queries, months=months, since=since, lang=lang, limit=limit, into=nodes)
    live = set(nodes)
    known = _from_index(index, task, nodes, from_index) if index and task and from_index else {}
    kw = {"now": now, "new_days": new_days, "lang": lang, "exclude": list(exclude), "must": list(must),
          "task": task, "min_closeness": min_closeness, "index": index, "texts": {} if fit_k else None}
    rows = _process(nodes, live, "query", known=known, **kw)
    if task and round2:
        extra, topics = _round2(rows, queries, nodes, k=round2_k, floor=max(min_closeness, semantic.MIN_CLOSENESS),
                                lang=lang, months=months, since=since, limit=limit)
        last_round2_topics = topics
        log.info("round two: topics %s → %d new", ", ".join(topics) or "—", len(extra))
        rows += _process(extra, set(extra), "round two", known={}, **kw)
    if index:
        seen = index.seen([r["repo"] for r in rows])
        for r in rows:
            r["seen"] = seen.get(r["repo"].lower(), "")
    rows.sort(key=sort_key)
    add_stars_flag(rows, stars_k, now)
    if fit_k:
        systemone.add_fit(rows, task, kw["texts"], fit_k)
    return rows


def add_stars_flag(rows: list[dict], k: int, now: datetime) -> None:
    """'burst★' flag for top-k surviving rows with >=50★ (after closeness; does not alter score)."""
    top = [r for r in rows if not r["stop"] and r["stars"] >= stars.MIN_STARS][:k]
    for r in top:
        try:
            text = stars.flag(stars.history(r["repo"], now))
        except GitHubError as e:
            log.warning("warning: 'burst★' flag for %s skipped: %s", r["repo"], e)
            continue
        if text:
            r["flags"].append(text)


def draft_params(d, need: str) -> dict:
    """Search parameters from LLM draft (remaining values default to parser defaults)."""
    params = search_params(_parser().parse_args(["--task", "x", "q"]))
    params.update(task=d.task, queries=list(d.queries), must=list(d.must), exclude=list(d.exclude),
                  lang=d.lang, need=need.strip())
    return params


def verdict_main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="repo-scout verdict")
    ap.add_argument("repo", metavar="owner/repo")
    ap.add_argument("verdict", help="'→ Inspect', '→ Study (goal)', 'drop (reason)', 'doubt (details)'")
    ap.add_argument("--project", required=True)
    ap.add_argument("--task", required=True, help="the project task in a few words")
    a = ap.parse_args(argv)
    try:
        validate_verdict(a.repo, a.verdict, a.project, a.task)
    except ValueError as e:
        sys.exit(f"verdict: {e}")
    Index(default_path()).add_verdict(a.repo, a.verdict, a.project, a.task)
    print(f"recorded: {a.repo} — {a.verdict} ({a.project})")


def draft_main(argv: list[str]) -> None:
    """`repo-scout draft "<need>"`: LLM draft output as a single runnable `repo-scout …` command."""
    import shlex

    from repo_scout import llm
    ap = argparse.ArgumentParser(prog="repo-scout draft")
    ap.add_argument("need", help="what you are looking for, in any language")
    a = ap.parse_args(argv)
    if not llm.available():
        sys.exit(f"draft: {llm.NO_KEY}")
    logmod.setup(quiet=True)
    try:
        d = llm.draft(a.need)
    except llm.LLMError as e:
        sys.exit(f"draft: {e}")
    print(shlex.join(["repo-scout", *to_argv(draft_params(d, a.need))]))


@logmod.logged_exit
def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # ★/✓/→ on a legacy Windows code page (redirected output) must not crash
        stream.reconfigure(errors="replace")
    if sys.argv[1:2] == ["eval"]:
        from repo_scout import evaluate
        return evaluate.main(sys.argv[2:])
    if sys.argv[1:2] == ["gui"] or not sys.argv[1:]:
        from repo_scout.gui import app
        return app.main(sys.argv[2:] if sys.argv[1:] else ["--open"])  # bare run (or double-click) opens the browser
    if sys.argv[1:2] == ["verdict"]:
        return verdict_main(sys.argv[2:])
    if sys.argv[1:2] == ["draft"]:
        return draft_main(sys.argv[2:])
    if sys.argv[1:2] == ["config"]:
        from repo_scout import config
        return config.main(sys.argv[2:])
    if sys.argv[1:2] == ["doctor"]:
        from repo_scout import doctor
        return doctor.main(sys.argv[2:])
    a = _parser().parse_args()
    logmod.setup(quiet=a.quiet)
    _main(a)


class _Parser(argparse.ArgumentParser):
    raise_errors = False  # parse_command: errors raise ValueError without SystemExit or stderr

    def error(self, message: str):
        if self.raise_errors:
            raise ValueError(message)
        super().error(message)


def _parser() -> argparse.ArgumentParser:
    ap = _Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", nargs="+")
    ap.add_argument("--task", required=True, metavar="TEXT",
                    help="the task in 1-3 English sentences; closeness is measured against it")
    ap.add_argument("--min-closeness", type=float, default=semantic.MIN_CLOSENESS, metavar="FLOAT",
                    help="rows below this closeness are dropped as 'off-topic' (default %(default)s)")
    ap.add_argument("--months", type=int, default=6, help="only repos pushed to within N months (0 = any)")
    ap.add_argument("--new-days", type=int, default=60, help="flag repos younger than N days as 'new'")
    ap.add_argument("--limit", type=int, default=50, help="results per query (max 100)")
    ap.add_argument("--lang", help="add language:<X> to each query")
    ap.add_argument("--exclude", action="append", default=[], metavar="REGEX",
                    help="drop a repo if REGEX matches its name, description, topics or README (repeatable)")
    ap.add_argument("--must", action="append", default=[], metavar="REGEX",
                    help="words the README, topics or description must contain; every --must must match (repeatable)")
    ap.add_argument("--from-index", type=int, default=FROM_INDEX, metavar="N",
                    help="add the N closest repos from the Index (0 = off, default %(default)s)")
    ap.add_argument("--round2-k", type=int, default=ROUND2_K, metavar="K",
                    help="round two takes topics from the top K rows (default %(default)s)")
    ap.add_argument("--stars-k", type=int, default=STARS_K, metavar="K",
                    help="check the top K rows with 50+ stars for a star burst (default %(default)s)")
    ap.add_argument("--no-stars-check", action="store_true", help="skip the star burst check")
    ap.add_argument("--no-round2", action="store_true", help="skip round two (`topic:` queries from the top rows)")
    ap.add_argument("--no-fit", action="store_true",
                    help="skip the fit column (advanced mode, on when TYPESAFE_API_KEY is set)")
    ap.add_argument("--project", help="project name, saved with the run")
    ap.add_argument("--need", metavar="TEXT", help="your request in your own words, saved with the run (the search ignores it)")
    ap.add_argument("--out", metavar="PATH", help="where to save the run (default: the runs folder)")
    ap.add_argument("--no-save", action="store_true", help="do not save the run")
    ap.add_argument("--all", action="store_true", help="show dropped rows too")
    ap.add_argument("--json", action="store_true")
    snap = ap.add_mutually_exclusive_group()
    snap.add_argument("--record", metavar="DIR", help="record GitHub responses to DIR")
    snap.add_argument("--replay", metavar="DIR", help="replay responses from DIR without network")
    ap.add_argument("-q", "--quiet", action="store_true", help="write progress to the log file only; the terminal shows warnings only")
    return ap


def _save_run(a: argparse.Namespace, rows: list[dict], now: datetime) -> None:
    if a.no_save or a.record or a.replay:
        return
    try:
        path = runs.save(search_params(a), rows, last_round2_topics, now, Path(a.out) if a.out else None)
    except OSError as e:
        log.warning("Run not saved: %s", e)
        return
    log.info("Run saved: %s", path)


def _main(a: argparse.Namespace) -> None:
    try:
        exclude, must = compile_all("--exclude", a.exclude), compile_all("--must", a.must)
        github.configure("record" if a.record else "replay" if a.replay else None, a.record or a.replay)
        now = github.recorded_at() if a.replay else datetime.now(UTC)
        rows = run(a.queries, months=a.months, new_days=a.new_days, limit=a.limit, lang=a.lang, now=now,
                   exclude=exclude, must=must, task=a.task, min_closeness=a.min_closeness,
                   index=None if a.record or a.replay else Index(default_path()), from_index=a.from_index,
                   round2=not a.no_round2, round2_k=a.round2_k,
                   stars_k=0 if a.no_stars_check else a.stars_k,
                   fit_k=0 if a.no_fit or a.record or a.replay else systemone.FIT_K)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    except GitHubError as e:
        sys.exit(f"GitHub: {e}")
    github.log_usage()

    kept = [r for r in rows if not r["stop"]]
    by_must = [r for r in rows if (r["stop"] or "").startswith((MUST_STOP, "\u043d\u0435\u0442 \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0433\u043e"))]
    shown = [r for r in (rows if a.all else kept) if r not in by_must]
    if a.json:
        print(json.dumps({"rows": shown, "dropped_by_must": by_must}, ensure_ascii=False, indent=1))
        _save_run(a, rows, now)
        return
    print(to_markdown(shown))
    if by_must:
        print("\ndropped by --must: " + ", ".join(r["repo"] for r in by_must))
    print(f"\nfound {len(rows)}, passed stop rules {len(kept)}, dropped {len(rows) - len(kept)}"
          + ("" if a.all else " (--all to show)"))
    _save_run(a, rows, now)
