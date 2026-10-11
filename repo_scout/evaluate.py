"""`repo-scout eval`: прогон золотых наборов eval/*.toml и метрики полноты."""
import argparse
import sys
import tomllib
from pathlib import Path

from repo_scout import github
from repo_scout.cli import apply_closeness, run
from repo_scout.conditions import compile_all
from repo_scout.github import GitHubError
from repo_scout.semantic import MIN_CLOSENESS

SWEEP = [round(0.50 + 0.01 * i, 2) for i in range(41)]

COLUMNS = ["набор", "позитивов", "найдено", "прошло", "позиции", "ложный отсев", "не найдено", "«отсев» прошли", "мин. близость позитивов"]


def metrics(spec: dict, rows: list[dict]) -> dict:
    """Метрики набора по строкам триажа. Имена репо сравниваются без учёта регистра."""
    kept = [r["repo"].lower() for r in rows if not r["stop"]]
    stops = {r["repo"].lower(): r["stop"] for r in rows if r["stop"]}
    close = {r["repo"].lower(): r.get("closeness") for r in rows}
    exp = spec["expected"]
    pos = [e["repo"] for e in exp if e["verdict"].startswith("→")]
    neg = [e["repo"] for e in exp if e["verdict"].startswith("отсев")]
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
    out += [f"- прошёл, место {i}: {p}" for p, i in m["kept"]]
    out += [f"- ложный отсев: {p} ({why})" for p, why in m["false_drops"]]
    out += [f"- не найден: {p}" for p in m["not_found"]]
    out += [f"- «отсев» прошёл: {p}" for p in m["negatives_passed"]]
    return "\n".join(out)


def sweep(sets: list[tuple[dict, list[dict]]]) -> str:
    """Порог 0.50..0.90: сколько позитивов (→ Разбор / все →) и сколько строк выдачи отсеклось бы."""
    lines = ["| порог | потеряно → Разбор | потеряно всех → | осталось строк |", "|---|---|---|---|"]
    for t in SWEEP:
        razbor = pos = kept = 0
        for spec, rows in sets:
            alive = {r["repo"].lower(): r for r in rows if not r["stop"]}
            kept += sum(r["closeness"] >= t for r in alive.values() if r.get("closeness") is not None)
            for e in spec["expected"]:
                r = alive.get(e["repo"].lower())
                if e["verdict"].startswith("→") and r and r["closeness"] < t:
                    pos += 1
                    razbor += e["verdict"].startswith("→ Разбор")
        lines.append(f"| {t:.2f} | {razbor} | {pos} | {kept} |")
    return "\n".join(lines)


def eval_set(path: Path, mode: str, task: str | None = None) -> tuple[dict, list[dict]]:
    spec = tomllib.loads(path.read_text())
    exclude = compile_all("--exclude", spec.get("exclude", []))
    must = compile_all("--must", spec.get("must", []))
    github.configure(mode, path.parent / "snapshots" / spec["name"])
    now = github.recorded_at()  # дата снимка и при дозаписи: сравнимость с baseline
    rows = run(spec["queries"], months=6, new_days=60, limit=50, lang=spec.get("lang") or None, now=now,
               exclude=exclude, must=must, task=task or spec["task"], min_closeness=0)
    return spec, rows


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="repo-scout eval")
    ap.add_argument("sets", nargs="+", type=Path)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--record", action="store_true", help="писать снапшоты (сеть)")
    mode.add_argument("--replay", action="store_true", help="читать снапшоты (по умолчанию)")
    ap.add_argument("--detail", action="store_true", help="список репо по каждому набору")
    ap.add_argument("--sweep", action="store_true", help="таблица порогов Близости 0.50..0.90")
    ap.add_argument("--top", type=int, metavar="N", help="вывести топ-N выдачи каждого набора")
    ap.add_argument("--task", metavar="TEXT", help="подменить Описание задачи (проверка устойчивости формулировок)")
    a = ap.parse_args(argv)
    try:
        sets = [eval_set(p, "record" if a.record else "replay", a.task) for p in a.sets]
    except (ValueError, GitHubError) as e:
        sys.exit(f"eval: {e}")
    ms, tops = [], []
    for spec, rows in sets:
        capped = [dict(r) for r in rows]
        apply_closeness(capped, MIN_CLOSENESS)
        ms.append(metrics(spec, capped))
        tops.append([r["repo"] for r in capped if not r["stop"]][:a.top or 0])
    print(summary_table(ms))
    if a.sweep:
        print("\n" + sweep(sets))
    for m, top in zip(ms, tops):
        if top:
            print(f"\n{m['name']} top-{a.top}: " + ", ".join(top))
    if a.detail:
        print("\n".join(detail(m) for m in ms))
