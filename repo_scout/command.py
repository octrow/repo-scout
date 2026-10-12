"""Command `repo-scout …` <-> search parameters: string parsing and argv serialization."""
import argparse
import shlex
import sys

NON_SEARCH = {"out", "no_save", "json", "all", "record", "replay", "quiet"}  # not search parameters


def search_params(a: argparse.Namespace) -> dict:
    """Search parameters from Namespace (JSON-serializable dict, excluding output and snapshot options)."""
    return {k: v for k, v in vars(a).items() if k not in NON_SEARCH}


def parse_command(text: str) -> argparse.Namespace:
    """Parse `repo-scout …` string (optional leading `$`) into Namespace; raises ValueError on error."""
    from repo_scout.cli import _parser, validate_query  # lazy import: cli re-exports this module

    tokens = shlex.split(text)
    while tokens and tokens[0].lstrip("$") in ("", "repo-scout", "repo_scout"):
        tokens.pop(0)
    ap = _parser()
    ap.raise_errors = True
    try:
        a = ap.parse_args(tokens)
    except SystemExit as e:  # -h
        raise ValueError("help is not available in command") from e
    for q in a.queries:
        validate_query(q)
    return a


def to_argv(params: dict, extra: list[str] | None = None) -> list[str]:
    """Arguments after program name from search parameters; default values are omitted.

    `extra` (such as `["--out", path]`) is placed before `--`, otherwise it becomes a positional query.
    """
    from repo_scout.cli import _parser

    out: list[str] = []
    for act in _parser()._actions:
        if act.dest not in params or act.dest in ("queries", "help"):
            continue
        val, flag = params[act.dest], act.option_strings[-1]
        if val == act.default:
            continue
        if act.nargs == 0:  # store_true
            out.append(flag)
        elif isinstance(val, list):
            out += [f"{flag}={v}" for v in val]
        else:
            out.append(f"{flag}={val}")
    return [*out, *(extra or []), "--", *params["queries"]]


def self_argv() -> list[str]:
    """argv prefix that re-runs repo-scout: the frozen release binary itself, or this interpreter with -m."""
    return [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "repo_scout"]
