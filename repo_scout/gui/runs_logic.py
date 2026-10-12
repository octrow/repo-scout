"""Runs and Index pages logic without UI: Run file lookup, row filters, verdict text."""
from pathlib import Path

from .. import runs
from ..cli import sort_key
from .i18n import t

ALL = "All"
FLAGS_ALL = "All flags"
SOURCES_ALL = "All sources"
# key -> label in form; Verdict is assembled according to index.VERDICT rules
VERDICT_KINDS = {"watch": "→ Inspect", "dig": "→ Study", "drop": "Drop", "doubt": "Doubt"}
VERDICT_PREFIX = {"watch": "→ Inspect", "dig": "→ Study", "drop": "drop", "doubt": "doubt"}
NOTE_LABELS = {"dig": "Study goal", "drop": "Drop reason", "doubt": "What to clarify"}
DESC_LIMIT = 120


def resolve_run(stem: str) -> Path | None:
    """Run file by stem, strictly inside runs directory; otherwise None."""
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
    """Rows matching filters; order is preserved. Text is searched in repo, desc, and lang."""
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
    return ", ".join([*r.get("flags", []), *([t("dropped: {stop}").format(stop=stop)] if stop else [])]) or "—"


def table_row(r: dict) -> dict:
    """Table row with CLI markdown output columns."""
    close = r.get("closeness")
    g = r.get
    return {"repo": g("repo", "?"), "url": g("url", ""), "close": "—" if close is None else f"{close:.2f}",
            "fit": "—" if g("fit") is None else f"{g('fit'):.2f}",
            "source": g("source", ""), "score": f"{g('score', 0)} (fresh {g('fresh', 0)}, pop {g('pop', 0)})",
            "stars": g("stars", 0), "forks": g("forks", 0), "commits": g("commits", 0),
            "pushed": g("pushed_days", ""), "created": g("created", ""), "lang": g("lang", ""),
            "flags": flags_text(r), "seen": g("seen") or "—", "desc": (g("desc") or "")[:DESC_LIMIT]}


def compose_verdict(kind: str, note: str) -> str:
    """Verdict string from kind and note; ValueError if note is required but empty."""
    prefix = VERDICT_PREFIX[kind]
    if kind == "watch":
        return prefix
    note = " ".join((note or "").split())
    if not note:
        raise ValueError(f"{t(NOTE_LABELS[kind])}: {t('explanation required')}")
    return f"{prefix} ({note})"


def verdict_filter_options() -> dict[str, str]:
    return {"": t(ALL), **{k: VERDICT_PREFIX[k] for k in VERDICT_KINDS}}
