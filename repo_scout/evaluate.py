"""`repo-scout eval`: прогон золотых наборов eval/*.toml и метрики полноты."""
import argparse
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from repo_scout import github
from repo_scout.cli import run
from repo_scout.github import GitHubError

COLUMNS = ["набор", "позитивов", "найдено", "прошло", "позиции", "ложный отсев", "не найдено", "«отсев» прошли"]


def metrics(spec: dict, rows: list[dict]) -> dict:
    """Метрики набора по строкам триажа. Имена репо сравниваются без учёта регистра."""
    kept = [r["repo"].lower() for r in rows if not r["stop"]]
    stops = {r["repo"].lower(): r["stop"] for r in rows if r["stop"]}
    exp = spec["expected"]
    pos = [e["repo"] for e in exp if e["verdict"].startswith("→")]
    neg = [e["repo"] for e in exp if e["verdict"].startswith("отсев")]
    return {
        "name": spec["name"],
        "positives": len(pos),
        "found": sum(p.lower() in kept or p.lower() in stops for p in pos),
        "kept": [(p, kept.index(p.lower()) + 1) for p in pos if p.lower() in kept],
        "false_drops": [(p, stops[p.lower()]) for p in pos if p.lower() in stops],
        "not_found": [p for p in pos if p.lower() not in kept and p.lower() not in stops],
        "negatives_passed": [n for n in neg if n.lower() in kept],
    }


def summary_table(ms: list[dict]) -> str:
    lines = ["| " + " | ".join(COLUMNS) + " |", "|---" * len(COLUMNS) + "|"]
    for m in ms:
        pos = ", ".join(str(i) for _, i in m["kept"]) or "—"
        cells = [m["name"], m["positives"], m["found"], len(m["kept"]), pos,
                 len(m["false_drops"]), len(m["not_found"]), len(m["negatives_passed"])]
        lines.append("| " + " | ".join(map(str, cells)) + " |")
    return "\n".join(lines)


def detail(m: dict) -> str:
    out = [f"\n### {m['name']}"]
    out += [f"- прошёл, место {i}: {p}" for p, i in m["kept"]]
    out += [f"- ложный отсев: {p} ({why})" for p, why in m["false_drops"]]
    out += [f"- не найден: {p}" for p in m["not_found"]]
    out += [f"- «отсев» прошёл: {p}" for p in m["negatives_passed"]]
    return "\n".join(out)


def eval_set(path: Path, mode: str) -> dict:
    spec = tomllib.loads(path.read_text())
    if spec.get("must") or spec.get("exclude"):
        print(f"{spec['name']}: must/exclude пока не применяются (Фаза 3)", file=sys.stderr)
    github.configure(mode, path.parent / "snapshots" / spec["name"])
    now = github.recorded_at() if mode == "replay" else datetime.now(UTC)
    rows = run(spec["queries"], months=6, new_days=60, limit=50, lang=spec.get("lang") or None, now=now)
    return metrics(spec, rows)


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="repo-scout eval")
    ap.add_argument("sets", nargs="+", type=Path)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--record", action="store_true", help="писать снапшоты (сеть)")
    mode.add_argument("--replay", action="store_true", help="читать снапшоты (по умолчанию)")
    ap.add_argument("--detail", action="store_true", help="список репо по каждому набору")
    a = ap.parse_args(argv)
    try:
        ms = [eval_set(p, "record" if a.record else "replay") for p in a.sets]
    except (ValueError, GitHubError) as e:
        sys.exit(f"eval: {e}")
    print(summary_table(ms))
    if a.detail:
        print("\n".join(detail(m) for m in ms))
