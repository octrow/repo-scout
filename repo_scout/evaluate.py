"""`repo-scout eval`: run golden sets eval/*.toml and report recall metrics."""
import argparse
import atexit
import contextlib
import json
import sys
import tempfile
import tomllib
from pathlib import Path

from repo_scout import github
from repo_scout.cli import FROM_INDEX, apply_closeness, run
from repo_scout.conditions import compile_all
from repo_scout.github import GitHubError
from repo_scout.index import Index, default_path
from repo_scout.semantic import MIN_CLOSENESS

SWEEP = [round(0.50 + 0.01 * i, 2) for i in range(41)]

COLUMNS = ["set", "positives", "found", "passed", "positions", "false drops", "not found", "negatives passed", "min closeness"]


def metrics(spec: dict, rows: list[dict]) -> dict:
    """Compute set metrics from triage rows. Repo names are compared case-insensitively."""
    kept = [r["repo"].lower() for r in rows if not r["stop"]]
    stops = {r["repo"].lower(): r["stop"] for r in rows if r["stop"]}
    close = {r["repo"].lower(): r.get("closeness") for r in rows}
    exp = spec["expected"]
    pos = [e["repo"] for e in exp if e["verdict"].startswith(("→", "->"))]
    neg = [e["repo"] for e in exp if e["verdict"].startswith(("\u043e\u0442\u0441\u0435\u0432", "drop", "rejected"))]
    kept_pos = [(p, kept.index(p.lower()) + 1) for p in pos if p.lower() in kept]
    return {
        "name": spec["name"],
        "positives": len(pos),
        "found": sum(p.lower() in kept or p.lower() in stops for p in pos),
        "kept": kept_pos,
        "false_drops": [(p, stops[p.lower()]) for p in pos if p.lower() in stops],
        "not_found": [p for p in pos if p.lower() not in kept and p.lower() not in stops],
        "negatives_passed": [n for n in neg if n.lower() in kept],
        "min_close": min((close[p.lower()] for p, _ in kept_pos if close[p.lower()] is not None), default=None),
    }


def summary_table(ms: list[dict]) -> str:
    lines = ["| " + " | ".join(COLUMNS) + " |", "|---" * len(COLUMNS) + "|"]
    for m in ms:
        pos = ", ".join(str(i) for _, i in m["kept"]) or "—"
        cells = [m["name"], m["positives"], m["found"], len(m["kept"]), pos,
                 len(m["false_drops"]), len(m["not_found"]), len(m["negatives_passed"]),
                 "—" if m["min_close"] is None else f"{m['min_close']:.2f}"]
        lines.append("| " + " | ".join(map(str, cells)) + " |")
    return "\n".join(lines)


def detail(m: dict) -> str:
    out = [f"\n### {m['name']}"]
    out += [f"- passed, rank {i}: {p}" for p, i in m["kept"]]
    out += [f"- false drop: {p} ({why})" for p, why in m["false_drops"]]
    out += [f"- not found: {p}" for p in m["not_found"]]
    out += [f"- negative passed: {p}" for p in m["negatives_passed"]]
    return "\n".join(out)


def sweep(sets: list[tuple[dict, list[dict]]]) -> str:
    """Threshold 0.50..0.90: count how many positives and total rows would be dropped."""
    lines = ["| threshold | lost → Study | lost all → | remaining rows |", "|---|---|---|---|"]
    for t in SWEEP:
        razbor = pos = kept = 0
        for spec, rows in sets:
            alive = {r["repo"].lower(): r for r in rows if not r["stop"]}
            kept += sum(r["closeness"] >= t for r in alive.values() if r.get("closeness") is not None)
            for e in spec["expected"]:
                r = alive.get(e["repo"].lower())
                if (e["verdict"].startswith("→") or e["verdict"].startswith("->")) and r and r["closeness"] < t:
                    pos += 1
                    razbor += "\u0420\u0430\u0437\u0431\u043e\u0440" in e["verdict"] or "Study" in e["verdict"]
        lines.append(f"| {t:.2f} | {razbor} | {pos} | {kept} |")
    return "\n".join(lines)


def eval_set(path: Path, mode: str, task: str | None = None, queries: list[str] | None = None,
             index: Index | None = None, from_index: int = FROM_INDEX,
             round2: bool = True, overrides: dict | None = None,
             snap_dir: Path | None = None, details_dir: Path | None = None) -> tuple[dict, list[dict]]:
    """Run evaluation for a set. Uses a fresh temporary Index by default to isolate from user's index."""
    spec = {**tomllib.loads(path.read_text()), **(overrides or {})}
    exclude = compile_all("--exclude", spec.get("exclude", []))
    must = compile_all("--must", spec.get("must", []))
    github.configure(mode, snap_dir or path.parent / "snapshots" / spec["name"], details_dir)
    github.calls.clear()
    now = github.recorded_at()
    with tempfile.TemporaryDirectory() as tmp:
        idx = index or Index(Path(tmp) / "index.db")
        rows = run(queries or spec["queries"], months=6, new_days=60, limit=50, lang=spec.get("lang") or None,
                    now=now, exclude=exclude, must=must, task=task or spec["task"], min_closeness=0, index=idx,
                    from_index=from_index, round2=round2)
        if not index:
            idx.db.close()
    spec["calls"] = dict(github.calls)
    return spec, rows


def index_check(path: Path, mode: str, from_index: int = FROM_INDEX) -> str:
    """Phase 5 criterion: alternative wording and fewer queries retrieve repos from Index not in live results."""
    with tempfile.TemporaryDirectory() as tmp:
        idx = Index(Path(tmp) / "index.db")
        spec, first = eval_set(path, mode, index=idx, round2=False)
        if not spec.get("alt_task"):
            idx.db.close()  # an open db keeps the temp dir from being removed on Windows
            return ""
        _, rows = eval_set(path, mode, spec["alt_task"], spec["queries"][:2], idx, from_index, round2=False)
        idx.db.close()
    pos = {e["repo"].lower() for e in spec["expected"] if e["verdict"].startswith(("→", "->"))}
    live = [r for r in rows if r["source"] in ("query", "\u0437\u0430\u043f\u0440\u043e\u0441")]
    from_idx = [r for r in rows if r["source"] in ("index", "\u0438\u043d\u0434\u0435\u043a\u0441")]
    def hit(rs):
        return sorted(r["repo"] for r in rs if r["repo"].lower() in pos and not r["stop"])
    return (f"{spec['name']}: Index after first run {sum(not r['stop'] for r in first)} rows; second run "
            f"(2 queries, alternative task): live search {len(live)}, from Index {len(from_idx)} "
            f"(passed stop rules {sum(not r['stop'] for r in from_idx)}); positives in live {hit(live) or '—'}, "
            f"positives from Index {hit(from_idx) or '—'} of {len(pos)}")


def _one_line(text: str) -> str:
    return " ".join(text.split())


def export_verdicts(index: Index, project: str | None) -> str:
    """Export Index verdicts as [[expected]] blocks for golden sets, grouped by project."""
    out, current = [], None
    for proj, name, verdict, task, date in index.verdicts(project):
        if proj != current:
            out.append(f"\n# project: {_one_line(proj)}")
            current = proj
        out += ["[[expected]]", f"repo = {json.dumps(name, ensure_ascii=False)}",
                f"verdict = {json.dumps(verdict, ensure_ascii=False)}", f"# {date}: {_one_line(task)}"]
    return "\n".join(out).strip()


def main(argv: list[str]) -> None:
    from repo_scout import log
    log.setup(quiet=True)
    ap = argparse.ArgumentParser(prog="repo-scout eval")
    ap.add_argument("sets", nargs="*", type=Path)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--record", action="store_true", help="record snapshots (network)")
    mode.add_argument("--replay", action="store_true", help="replay snapshots (default)")
    ap.add_argument("--detail", action="store_true", help="list repos for each set")
    ap.add_argument("--sweep", action="store_true", help="closeness threshold table 0.50..0.90")
    ap.add_argument("--top", type=int, metavar="N", help="output top-N results of each set")
    ap.add_argument("--task", metavar="TEXT", help="override task description")
    ap.add_argument("--no-round2", action="store_true", help="disable round two")
    ap.add_argument("--calls", action="store_true", help="API call counts (search, details) per set")
    ap.add_argument("--llm-draft", action="store_true",
                    help="Phase 9: recall of agent queries / LLM draft / union (snapshots in eval/snapshots-llm)")
    ap.add_argument("--index-check", action="store_true", help="Phase 5 criterion: rephrased query + Index")
    ap.add_argument("--export-verdicts", action="store_true", help="Index verdicts as [[expected]] (TOML)")
    ap.add_argument("--fake-stars", action="store_true", help="Phase 7: precision/recall/FPR of 'burst★' flag on eval/fake-stars (network with --record)")
    ap.add_argument("--all-grid", action="store_true", help="with --fake-stars: full threshold grid")
    ap.add_argument("--from-index", type=int, default=FROM_INDEX, metavar="N", help="with --index-check")
    ap.add_argument("--project", help="with --export-verdicts: filter by project")
    ap.add_argument("--out", type=Path, metavar="PATH", help="output report to file instead of stdout")
    a = ap.parse_args(argv)
    if not a.out:
        return _report(a, ap)
    with a.out.open("w", encoding="utf-8") as f, contextlib.redirect_stdout(f):
        _report(a, ap)


def _report(a: argparse.Namespace, ap: argparse.ArgumentParser) -> None:
    if a.export_verdicts:
        return print(export_verdicts(Index(default_path()), a.project))
    if a.fake_stars:
        from repo_scout import fake_stars
        try:
            return print(fake_stars.run("record" if a.record else "replay", a.all_grid))
        except (ValueError, GitHubError) as e:
            sys.exit(f"eval: {e}")
    if not a.sets:
        ap.error("eval/*.toml sets required")
    atexit.register(github.log_usage)
    if a.llm_draft:
        from repo_scout import eval_llm
        try:
            return print(eval_llm.report(a.sets, "record" if a.record else "replay"))
        except (ValueError, GitHubError, eval_llm.LLMError) as e:
            sys.exit(f"eval: {e}")
    try:
        if a.index_check:
            return print("\n".join(filter(None, (index_check(p, "record" if a.record else "replay", a.from_index) for p in a.sets))))
        sets = [eval_set(p, "record" if a.record else "replay", a.task, round2=not a.no_round2) for p in a.sets]
    except (ValueError, GitHubError) as e:
        sys.exit(f"eval: {e}")
    ms, tops = [], []
    for spec, rows in sets:
        capped = [dict(r) for r in rows]
        apply_closeness(capped, MIN_CLOSENESS)
        ms.append(metrics(spec, capped))
        tops.append([r["repo"] for r in capped if not r["stop"]][:a.top or 0])
    print(summary_table(ms))
    if a.calls:
        print("\n" + "\n".join(f"{s['name']}: search {s['calls'].get('search', 0)}, details {s['calls'].get('details', 0)}"
                              for s, _ in sets))
    if a.sweep:
        print("\n" + sweep(sets))
    for m, top in zip(ms, tops):
        if top:
            print(f"\n{m['name']} top-{a.top}: " + ", ".join(top))
    if a.detail:
        print("\n".join(detail(m) for m in ms))
