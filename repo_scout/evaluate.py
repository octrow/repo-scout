"""`repo-scout eval`: прогон золотых наборов eval/*.toml и метрики полноты."""
import argparse
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


def eval_set(path: Path, mode: str, task: str | None = None, queries: list[str] | None = None,
             index: Index | None = None, from_index: int = FROM_INDEX,
             round2: bool = True) -> tuple[dict, list[dict]]:
    """Прогон набора. Индекс по умолчанию свежий временный: числа сравнимы, пользовательский Индекс не трогаем."""
    spec = tomllib.loads(path.read_text())
    exclude = compile_all("--exclude", spec.get("exclude", []))
    must = compile_all("--must", spec.get("must", []))
    github.configure(mode, path.parent / "snapshots" / spec["name"])
    github.calls.clear()
    now = github.recorded_at()  # дата снимка и при дозаписи: сравнимость с baseline
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
    """Критерий Фазы 5: другая формулировка и меньше Запросов поднимают из Индекса репо, которых нет в живой выдаче."""
    with tempfile.TemporaryDirectory() as tmp:
        idx = Index(Path(tmp) / "index.db")
        spec, first = eval_set(path, mode, index=idx, round2=False)
        if not spec.get("alt_task"):
            return ""
        _, rows = eval_set(path, mode, spec["alt_task"], spec["queries"][:2], idx, from_index, round2=False)
        idx.db.close()
    pos = {e["repo"].lower() for e in spec["expected"] if e["verdict"].startswith("→")}
    live = [r for r in rows if r["source"] == "запрос"]
    from_idx = [r for r in rows if r["source"] == "индекс"]
    hit = lambda rs: sorted(r["repo"] for r in rs if r["repo"].lower() in pos and not r["stop"])
    return (f"{spec['name']}: Индекс после первого прогона {sum(not r['stop'] for r in first)} строк; второй прогон "
            f"(2 Запроса, другая формулировка): живая выдача {len(live)}, из Индекса {len(from_idx)} "
            f"(прошли стоп-правила {sum(not r['stop'] for r in from_idx)}); позитивы в живой {hit(live) or '—'}, "
            f"позитивы из Индекса {hit(from_idx) or '—'} из {len(pos)}")


def _one_line(text: str) -> str:
    return " ".join(text.split())


def export_verdicts(index: Index, project: str | None) -> str:
    """Вердикты Индекса как блоки [[expected]] для Золотых наборов, по проектам."""
    out, current = [], None
    for proj, name, verdict, task, date in index.verdicts(project):
        if proj != current:
            out.append(f"\n# проект: {_one_line(proj)}")
            current = proj
        out += ["[[expected]]", f"repo = {json.dumps(name, ensure_ascii=False)}",
                f"verdict = {json.dumps(verdict, ensure_ascii=False)}", f"# {date}: {_one_line(task)}"]
    return "\n".join(out).strip()


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="repo-scout eval")
    ap.add_argument("sets", nargs="*", type=Path)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--record", action="store_true", help="писать снапшоты (сеть)")
    mode.add_argument("--replay", action="store_true", help="читать снапшоты (по умолчанию)")
    ap.add_argument("--detail", action="store_true", help="список репо по каждому набору")
    ap.add_argument("--sweep", action="store_true", help="таблица порогов Близости 0.50..0.90")
    ap.add_argument("--top", type=int, metavar="N", help="вывести топ-N выдачи каждого набора")
    ap.add_argument("--task", metavar="TEXT", help="подменить Описание задачи (проверка устойчивости формулировок)")
    ap.add_argument("--no-round2", action="store_true", help="без второго круга (сравнение)")
    ap.add_argument("--calls", action="store_true", help="число вызовов API (поиск, детали) по наборам")
    ap.add_argument("--index-check", action="store_true", help="критерий Фазы 5: перефразировка + Индекс")
    ap.add_argument("--export-verdicts", action="store_true", help="Вердикты Индекса как [[expected]] (TOML)")
    ap.add_argument("--from-index", type=int, default=FROM_INDEX, metavar="N", help="с --index-check")
    ap.add_argument("--project", help="с --export-verdicts: только этот проект")
    a = ap.parse_args(argv)
    if a.export_verdicts:
        return print(export_verdicts(Index(default_path()), a.project))
    if not a.sets:
        ap.error("нужны наборы eval/*.toml")
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
        print("\n" + "\n".join(f"{s['name']}: поиск {s['calls'].get('search', 0)}, детали {s['calls'].get('details', 0)}"
                              for s, _ in sets))
    if a.sweep:
        print("\n" + sweep(sets))
    for m, top in zip(ms, tops):
        if top:
            print(f"\n{m['name']} top-{a.top}: " + ", ".join(top))
    if a.detail:
        print("\n".join(detail(m) for m in ms))
