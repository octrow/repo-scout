"""Eval page logic without UI: eval/*.toml datasets and subprocess argv."""
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .search_form import EVAL_DIR

NO_DATE = "—"


@dataclass(frozen=True)
class EvalSet:
    name: str
    path: Path
    task: str
    n_expected: int
    snapshot: str  # snapshot date: dataset analysis_date or snapshot directory mtime


@dataclass
class EvalOptions:
    sets: list[Path] = field(default_factory=list)
    record: bool = False  # defaults to --replay: offline
    detail: bool = False
    sweep: bool = False
    top: int = 0
    no_round2: bool = False
    calls: bool = False
    index_check: bool = False
    fake_stars: bool = False
    all_grid: bool = False


def list_sets(eval_dir: Path = EVAL_DIR) -> list[EvalSet]:
    out = []
    for p in sorted(eval_dir.glob("*.toml")) if eval_dir.is_dir() else []:
        try:
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        snap = eval_dir / "snapshots" / str(data.get("name", p.stem))
        date = data.get("analysis_date") or (
            datetime.fromtimestamp(snap.stat().st_mtime).date().isoformat() if snap.is_dir() else NO_DATE)
        out.append(EvalSet(data.get("name", p.stem), p, data.get("task", ""), len(data.get("expected", [])), date))
    return out


def eval_argv(o: EvalOptions, out: Path) -> list[str]:
    """argv for `repo-scout eval …`: datasets, mode, flags, and `--out`."""
    argv = [sys.executable, "-m", "repo_scout", "eval"]
    if not o.fake_stars:
        argv += [str(p) for p in o.sets]
    argv.append("--record" if o.record else "--replay")
    for flag, on in (("--detail", o.detail), ("--sweep", o.sweep), ("--no-round2", o.no_round2),
                     ("--calls", o.calls), ("--index-check", o.index_check), ("--fake-stars", o.fake_stars),
                     ("--all-grid", o.fake_stars and o.all_grid)):
        if on:
            argv.append(flag)
    if o.top > 0:
        argv += ["--top", str(o.top)]
    return [*argv, "--out", str(out)]


def export_argv(project: str | None, out: Path) -> list[str]:
    argv = [sys.executable, "-m", "repo_scout", "eval", "--export-verdicts"]
    if project:
        argv += ["--project", project]
    return [*argv, "--out", str(out)]


def eval_errors(o: EvalOptions) -> list[str]:
    if not o.fake_stars and not o.sets:
        return ["Select at least one set"]
    return []
