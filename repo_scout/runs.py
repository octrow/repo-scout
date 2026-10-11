"""Прогоны: один запуск поиска целиком (параметры, второй круг, все строки), JSON-файл на Прогон."""
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
    error: str | None = None  # у битого файла — причина, остальные поля пустые


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
    """Пишет Прогон (все строки, включая отсеянные). `path` задан — пишет туда, иначе в каталог Прогонов."""
    if path is None:
        name = f"{now.strftime('%Y%m%d-%H%M%S')}-{slug(params.get('task') or '')}.json"
        path = free_path(runs_dir() / name)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": VERSION, "created_at": now.isoformat(), "params": params,
            "round2_topics": round2_topics, "rows": rows}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: битый JSON: {e}") from e
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise ValueError(f"{path}: неподдерживаемая версия Прогона")
    if missing := [k for k in REQUIRED if k not in data]:
        raise ValueError(f"{path}: нет ключей {', '.join(missing)}")
    topics = data["round2_topics"]
    if not (isinstance(data["params"], dict) and isinstance(data["rows"], list)
            and all(isinstance(r, dict) for r in data["rows"])
            and isinstance(topics, list) and all(isinstance(t, str) for t in topics)):
        raise ValueError(f"{path}: неверная структура Прогона")
    return data


def list_runs() -> list[Summary]:
    """Сводки Прогонов, новые первыми; битый файл — запись с `error`, без исключения."""
    if not runs_dir().is_dir():
        return []
    out = []
    for p in sorted(runs_dir().glob("*.json"), reverse=True):
        try:
            d = load(p)
        except (ValueError, OSError) as e:  # ValueError включает JSONDecodeError
            out.append(Summary(p, error=str(e)))
            continue
        params = d["params"]
        out.append(Summary(p, d["created_at"], params.get("task"), params.get("project"),
                           len(d["rows"]), sum(1 for r in d["rows"] if not r.get("stop"))))
    return out


def delete(path: Path) -> None:
    Path(path).unlink()
