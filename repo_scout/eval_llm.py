"""`repo-scout eval --llm-draft`: recall of agent queries, LLM draft, and their union (Phase 9)."""
import sys
import tomllib
from pathlib import Path

from repo_scout import github, llm
from repo_scout.cli import apply_closeness
from repo_scout.evaluate import eval_set, metrics
from repo_scout.llm import LLMError  # noqa: F401  (re-export for evaluate)
from repo_scout.log import log
from repo_scout.semantic import MIN_CLOSENESS

COLUMNS = ["set", "positives", "agent: found/kept", "Draft: found/kept",
           "union: found/kept", "tokens", "Draft time, s"]

VARIANT_NAME = {"agent": "agent", "draft": "Draft", "union": "union"}


def snapshot_dir(path: Path, name: str) -> Path:
    return path.parent / "snapshots-llm" / name


def _metrics(path: Path, mode: str, snap: Path, overrides: dict | None) -> dict:
    shared = snap.parent / "_shared" / "details"  # details shared across sets and variants; stars_k is 0 by default
    spec, rows = eval_set(path, mode, overrides=overrides, snap_dir=snap, details_dir=shared)
    capped = [dict(r) for r in rows]
    apply_closeness(capped, MIN_CLOSENESS)
    return metrics(spec, capped)


def variants(spec: dict, d: llm.Draft) -> dict[str, dict | None]:
    """Dataset overrides for three variants; union: queries of both, conditions from spec."""
    union = list(dict.fromkeys([*spec["queries"], *d.queries]))
    return {"agent": None,
            "draft": {"task": d.task, "queries": list(d.queries), "lang": d.lang or "",
                      "must": list(d.must), "exclude": list(d.exclude)},
            "union": {"queries": union}}


def eval_one(path: Path, mode: str) -> dict | None:
    """Metrics for three variants of a set with `need`; None if no `need`."""
    spec = tomllib.loads(path.read_text(encoding="utf-8"))
    need = spec.get("need")
    if not need:
        print(f"eval: set {spec['name']} without need field, skipped", file=sys.stderr)
        return None
    snap = snapshot_dir(path, spec["name"])
    github.configure(mode, snap)  # llm stores responses in <snap>/llm/
    d = llm.draft(need)
    stats = dict(llm.last_stats)
    res = {}
    for name, ov in variants(spec, d).items():
        log.info("set %s, variant %s", spec["name"], VARIANT_NAME[name])
        res[name] = _metrics(path, mode, snap, ov)
    return {"name": spec["name"], "llm_draft": d, "stats": stats, **res}


def _cell(m: dict) -> str:
    return f"{m['found']}/{len(m['kept'])}"


def table(results: list[dict]) -> str:
    lines = ["| " + " | ".join(COLUMNS) + " |", "|---" * len(COLUMNS) + "|"]
    for r in results:
        cells = [r["name"], r["agent"]["positives"], _cell(r["agent"]), _cell(r["draft"]), _cell(r["union"]),
                 r["stats"].get("tokens", 0), r["stats"].get("seconds", 0)]
        lines.append("| " + " | ".join(map(str, cells)) + " |")
    total = {k: sum(r[k]["found"] for r in results) for k in ("agent", "draft", "union")}
    pos = sum(r["agent"]["positives"] for r in results)
    lines.append(f"| total found | {pos} | {total['agent']} | {total['draft']} | {total['union']} | "
                 f"{sum(r['stats'].get('tokens', 0) for r in results)} | "
                 f"{round(sum(r['stats'].get('seconds', 0) for r in results), 1)} |")
    return "\n".join(lines)


def report(paths: list[Path], mode: str) -> str:
    results = []
    for i, p in enumerate(paths, 1):
        log.info("set %d/%d %s", i, len(paths), p.stem)
        if r := eval_one(p, mode):
            results.append(r)
    if not results:
        return "no sets with a need field"
    drafts = [f"\n{r['name']}: " + " | ".join(r["llm_draft"].queries) for r in results]
    return table(results) + "\n" + "\n".join(drafts)
