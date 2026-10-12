"""Every user-visible kit string, in one dict. Russian by default.

The kit reads `TEXTS` at call time, so an app switches language by updating it:
`texts.TEXTS.update(texts.EN)` at startup, or again from its own language switch.
Override single keys the same way. `"lines"` is a function: plural forms differ.
"""

from collections.abc import Callable


def _lines_ru(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "строка"
    return "строки" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "строк"


RU: dict[str, str | Callable[[int], str]] = {
    # layout
    "copied": "Скопировано — вставьте в чат",
    "copy_for_chat": "Скопировать для чата",
    "required": "Заполните поле «{label}»",
    "loading": "Загружается",
    "retry": "Повторить",
    # table
    "empty": "ничего не найдено.",
    "rows_per_page": "Строк на странице:",
    "of": "из",
    "columns": "Колонки",
    "fit_width": "По ширине окна",
    # theme toggle
    "theme_system": "Тема: как в системе",
    "theme_light": "Тема: светлая",
    "theme_dark": "Тема: тёмная",
    # run_pool (written into the log, not shown as a widget)
    "overlong_line": "[nicegui-kit: строка длиннее STREAM_LINE_LIMIT обрезана]",
    "spawn_failed": "не удалось запустить: {error}",
    # run_monitor
    "run": "прогон",
    "status_queued": "в очереди · №{position}",
    "status_running": "идёт",
    "status_done": "готово",
    "status_cancelled": "остановлено пользователем",
    "status_failed": "ошибка · код {code}",
    "stop_confirm": "Остановить этот прогон?",
    "cancel": "Отмена",
    "stop": "Остановить",
    "dequeue": "Убрать из очереди",
    "output": "Вывод: {n} {lines}",
    "no_output": "Вывода пока нет",
    "idle": "Сейчас ничего не выполняется",
    "lines": _lines_ru,
}

EN: dict[str, str | Callable[[int], str]] = {
    "copied": "Copied — paste into chat",
    "copy_for_chat": "Copy for chat",
    "required": "Please fill in '{label}'",
    "loading": "Loading",
    "retry": "Retry",
    "empty": "nothing found.",
    "rows_per_page": "Rows per page:",
    "of": "of",
    "columns": "Columns",
    "fit_width": "Fit to window",
    "theme_system": "Theme: system",
    "theme_light": "Theme: light",
    "theme_dark": "Theme: dark",
    "overlong_line": "[nicegui-kit: line longer than STREAM_LINE_LIMIT truncated]",
    "spawn_failed": "failed to start: {error}",
    "run": "run",
    "status_queued": "queued · #{position}",
    "status_running": "running",
    "status_done": "done",
    "status_cancelled": "cancelled by user",
    "status_failed": "error · code {code}",
    "stop_confirm": "Stop this run?",
    "cancel": "Cancel",
    "stop": "Stop",
    "dequeue": "Remove from queue",
    "output": "Output: {n} {lines}",
    "no_output": "No output yet",
    "idle": "Nothing is currently running",
    "lines": lambda n: "line" if n == 1 else "lines",
}

# ponytail: process-global, one language per server; per-client dicts if a multi-user
# app ever needs two languages at once
TEXTS: dict[str, str | Callable[[int], str]] = dict(RU)


def tr(key: str, **fmt: object) -> str:
    """The current text for `key`, formatted with `fmt`."""
    text = TEXTS[key]
    assert isinstance(text, str), key
    return text.format(**fmt) if fmt else text


def lines_word(n: int) -> str:
    word = TEXTS["lines"]
    assert callable(word)
    return word(n)
