"""Runs: a complete single search run (parameters, round two, all rows), saved as a JSON file."""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

VERSION = 1
REQUIRED = ("version", "created_at", "params", "round2_topics", "rows")
SLUG_MAX = 40


@dataclass(frozen=True)
class Summary:
    path: Path
    created_at: str | None = None
    task: str | None = None
    project: str | None = None
    n_total: int = 0
    n_kept: int = 0
    error: str | None = None  # corrupt file stores error reason, other fields remain empty


def runs_dir() -> Path:
    return Path(os.environ.get("REPO_SCOUT_RUNS") or Path.home() / ".local/share/repo-scout/runs")


def slug(task: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:SLUG_MAX].strip("-") or "run"


def free_path(base: Path) -> Path:
    n, path = 1, base
    while path.exists():
        n += 1
        path = base.with_name(f"{base.stem}-{n}{base.suffix}")
    return path


def save(params: dict, rows: list[dict], round2_topics: list[str], now: datetime, path: Path | None = None) -> Path:
    """Save a Run (all rows, including dropped). Writes to `path` if specified, else runs directory."""
    if path is None:
        name = f"{now.strftime('%Y%m%d-%H%M%S')}-{slug(params.get('task') or '')}.json"
        path = free_path(runs_dir() / name)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": VERSION,
        "created_at": now.isoformat(),
        "params": params,
        "round2_topics": round2_topics,
        "rows": rows,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: corrupt JSON: {e}") from e
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise ValueError(f"{path}: unsupported Run version")
    if missing := [k for k in REQUIRED if k not in data]:
        raise ValueError(f"{path}: missing keys {', '.join(missing)}")
    if not _valid_structure(data):
        raise ValueError(f"{path}: invalid Run structure")
    return data


def _list_of(value, kind: type) -> bool:
    return isinstance(value, list) and all(isinstance(v, kind) for v in value)


def _valid_structure(data: dict) -> bool:
    """params is a dict, rows a list of dicts with sane flags and score, round2_topics a list of strings."""
    return (
        isinstance(data["params"], dict)
        and _list_of(data["rows"], dict)
        and all(_valid_row(r) for r in data["rows"])
        and _list_of(data["round2_topics"], str)
    )


def _valid_row(row: dict) -> bool:
    """flags a list and score a number when present: the GUI sorts and filters on them."""
    score = row.get("score", 0)
    return isinstance(row.get("flags", []), list) and isinstance(score, int | float) and not isinstance(score, bool)


def list_runs() -> list[Summary]:
    """Run summaries, newest first; corrupt files recorded with `error` without raising."""
    if not runs_dir().is_dir():
        return []
    out = []
    for p in sorted(runs_dir().glob("*.json"), reverse=True):
        try:
            d = load(p)
        except (ValueError, OSError) as e:
            out.append(Summary(p, error=str(e)))
            continue
        params = d["params"]
        out.append(
            Summary(
                p,
                d["created_at"],
                params.get("task"),
                params.get("project"),
                len(d["rows"]),
                sum(1 for r in d["rows"] if not r.get("stop")),
            )
        )
    return out


def delete(path: Path) -> None:
    Path(path).unlink()
