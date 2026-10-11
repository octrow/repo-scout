"""`repo-scout eval --llm-draft`: полнота Запросов агента, Черновика LLM и их объединения (Фаза 9)."""
import sys
import tomllib
from pathlib import Path

from repo_scout import github, llm
from repo_scout.cli import apply_closeness
from repo_scout.evaluate import eval_set, metrics
from repo_scout.llm import LLMError  # noqa: F401  (реэкспорт для evaluate)
from repo_scout.semantic import MIN_CLOSENESS

COLUMNS = ["набор", "позитивов", "агент: найдено/прошло", "Черновик: найдено/прошло",
           "объединение: найдено/прошло", "токены", "время Черновика, с"]


def snapshot_dir(path: Path, name: str) -> Path:
    return path.parent / "snapshots-llm" / name


def _metrics(path: Path, mode: str, snap: Path, overrides: dict | None) -> dict:
    spec, rows = eval_set(path, mode, overrides=overrides, snap_dir=snap)
    capped = [dict(r) for r in rows]
    apply_closeness(capped, MIN_CLOSENESS)
    return metrics(spec, capped)


def variants(spec: dict, d: llm.Draft) -> dict[str, dict | None]:
    """Переопределения набора для трёх вариантов; объединение: Запросы обоих, условия набора."""
    union = list(dict.fromkeys([*spec["queries"], *d.queries]))
    return {"agent": None,
            "draft": {"task": d.task, "queries": list(d.queries), "lang": d.lang or "",
                      "must": list(d.must), "exclude": list(d.exclude)},
            "union": {"queries": union}}


def eval_one(path: Path, mode: str) -> dict | None:
    """Метрики трёх вариантов набора с `need`; без `need` — None."""
    spec = tomllib.loads(path.read_text(encoding="utf-8"))
    need = spec.get("need")
    if not need:
        print(f"eval: набор {spec['name']} без поля need, пропущен", file=sys.stderr)
        return None
    snap = snapshot_dir(path, spec["name"])
    github.configure(mode, snap)  # llm кладёт ответы в <snap>/llm/
    d = llm.draft(need)
    stats = dict(llm.last_stats)
    res = {name: _metrics(path, mode, snap, ov) for name, ov in variants(spec, d).items()}
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
    lines.append(f"| итого найдено | {pos} | {total['agent']} | {total['draft']} | {total['union']} | "
                 f"{sum(r['stats'].get('tokens', 0) for r in results)} | "
                 f"{round(sum(r['stats'].get('seconds', 0) for r in results), 1)} |")
    return "\n".join(lines)


def report(paths: list[Path], mode: str) -> str:
    results = [r for p in paths if (r := eval_one(p, mode))]
    if not results:
        return "нет наборов с полем need"
    drafts = [f"\n{r['name']}: " + " | ".join(r["llm_draft"].queries) for r in results]
    return table(results) + "\n" + "\n".join(drafts)
