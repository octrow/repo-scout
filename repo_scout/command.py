"""Команда `repo-scout …` <-> параметры поиска: разбор строки, argv по параметрам."""
import argparse
import shlex

NON_SEARCH = {"out", "no_save", "json", "all", "record", "replay", "quiet"}  # не параметры поиска


def search_params(a: argparse.Namespace) -> dict:
    """Параметры поиска из Namespace (JSON-безопасный dict, без вывода и снапшотов)."""
    return {k: v for k, v in vars(a).items() if k not in NON_SEARCH}


def parse_command(text: str) -> argparse.Namespace:
    """Строка `repo-scout …` (можно с ведущим `$`) -> Namespace; любая ошибка — ValueError."""
    from repo_scout.cli import _parser, validate_query  # поздний импорт: cli реэкспортирует этот модуль

    tokens = shlex.split(text)
    while tokens and tokens[0].lstrip("$") in ("", "repo-scout", "repo_scout"):
        tokens.pop(0)
    ap = _parser()
    ap.raise_errors = True
    try:
        a = ap.parse_args(tokens)
    except SystemExit as e:  # -h
        raise ValueError("справка недоступна в команде") from e
    for q in a.queries:
        validate_query(q)
    return a


def to_argv(params: dict, extra: list[str] | None = None) -> list[str]:
    """Аргументы после имени программы по параметрам поиска; значения по умолчанию опускаются.

    `extra` (например `["--out", path]`) ставится до `--`, иначе станет запросом.
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
