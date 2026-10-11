"""Жёсткие условия: язык, запрещённые и обязательные слова. Нарушение возвращает причину стопа."""
import re

MATCH_SHOWN = 40


def lang_stop(row: dict, lang: str | None) -> str | None:
    if lang and row["lang"] and row["lang"].lower() != lang.lower():
        return f"не тот язык ({row['lang']})"
    return None


def meta_text(row: dict) -> str:
    return " ".join([row["repo"], row["desc"], *row["topics"]])


def compile_all(flag: str, patterns: list[str]) -> list[re.Pattern]:
    """Скомпилировать регэкспы (без учёта регистра) до сетевых вызовов; ошибка -> ValueError."""
    out = []
    for p in patterns:
        try:
            out.append(re.compile(p, re.IGNORECASE))
        except re.error as e:
            raise ValueError(f"{flag} {p!r}: {e}") from e
    return out


def exclude_stop(text: str, patterns: list[re.Pattern]) -> str | None:
    for p in patterns:
        if m := p.search(text):
            return f"запрещено: {m.group(0)[:MATCH_SHOWN]}"
    return None


def must_stop(text: str, groups: list[re.Pattern]) -> str | None:
    """Все группы должны найтись в тексте."""
    for g in groups:
        if not g.search(text):
            return f"нет обязательного: {g.pattern}"
    return None
