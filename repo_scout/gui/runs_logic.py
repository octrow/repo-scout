"""Страницы «Прогоны» и «Индекс» без UI: поиск файла Прогона, фильтры строк, текст Вердикта."""
from pathlib import Path

from .. import runs
from ..cli import sort_key

ALL = "Все"
FLAGS_ALL = "Все флаги"
SOURCES_ALL = "Все источники"
# ключ -> подпись в форме; Вердикт собирается по правилам index.VERDICT
VERDICT_KINDS = {"watch": "→ Осмотр", "dig": "→ Разбор", "drop": "Отсев", "doubt": "Спорно"}
VERDICT_PREFIX = {"watch": "→ Осмотр", "dig": "→ Разбор", "drop": "отсев", "doubt": "спорно"}
NOTE_LABELS = {"dig": "Цель разбора", "drop": "Причина отсева", "doubt": "Что уточнить"}
DESC_LIMIT = 120


def resolve_run(stem: str) -> Path | None:
    """Файл Прогона по имени без расширения, строго внутри каталога Прогонов; иначе None."""
    if not stem or "/" in stem or "\\" in stem or ".." in stem or "\x00" in stem:
        return None
    path = runs.runs_dir() / f"{stem}.json"
    return path if path.is_file() else None


def sorted_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=sort_key)


def source_options(rows: list[dict]) -> list[str]:
    return [SOURCES_ALL, *dict.fromkeys(r.get("source", "") for r in rows)]


def flag_options(rows: list[dict]) -> list[str]:
    return [FLAGS_ALL, *sorted({f for r in rows for f in r.get("flags", [])})]


def filter_rows(rows: list[dict], *, text: str = "", source: str = SOURCES_ALL, flag: str = FLAGS_ALL,
                show_stopped: bool = False) -> list[dict]:
    """Строки под фильтры; порядок сохраняется. Текст ищется в repo, описании и языке."""
    needle = (text or "").strip().lower()
    out = []
    for r in rows:
        if r.get("stop") and not show_stopped:
            continue
        if source != SOURCES_ALL and r.get("source") != source:
            continue
        if flag != FLAGS_ALL and flag not in r.get("flags", []):
            continue
        if needle and needle not in f"{r.get('repo', '')} {r.get('desc', '')} {r.get('lang', '')}".lower():
            continue
        out.append(r)
    return out


def flags_text(r: dict) -> str:
    stop = r.get("stop")
    return ", ".join([*r.get("flags", []), *([f"отсев: {stop}"] if stop else [])]) or "—"


def table_row(r: dict) -> dict:
    """Строка таблицы с колонками markdown-вывода CLI."""
    close = r.get("closeness")
    g = r.get
    return {"repo": g("repo", "?"), "url": g("url", ""), "close": "—" if close is None else f"{close:.2f}",
            "source": g("source", ""), "score": f"{g('score', 0)} (свеж {g('fresh', 0)}, поп {g('pop', 0)})",
            "stars": g("stars", 0), "forks": g("forks", 0), "commits": g("commits", 0),
            "pushed": g("pushed_days", ""), "created": g("created", ""), "lang": g("lang", ""),
            "flags": flags_text(r), "seen": g("seen") or "—", "desc": (g("desc") or "")[:DESC_LIMIT]}


def compose_verdict(kind: str, note: str) -> str:
    """Строка Вердикта из вида и пояснения; ValueError, если пояснение обязательно, а его нет."""
    prefix = VERDICT_PREFIX[kind]
    if kind == "watch":
        return prefix
    note = " ".join((note or "").split())
    if not note:
        raise ValueError(f"{NOTE_LABELS[kind]}: заполните пояснение")
    return f"{prefix} ({note})"


def verdict_filter_options() -> dict[str, str]:
    return {"": ALL, **{k: VERDICT_PREFIX[k] for k in VERDICT_KINDS}}
