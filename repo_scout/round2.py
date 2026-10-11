"""Второй круг: Запросы `topic:<slug>` из частых topics топ-кандидатов первого прохода."""
import re
from collections import Counter

ROUND2_K = 10  # сколько лучших строк первого прохода смотрим
MAX_TOPICS = 5  # лимит Запросов второго круга
MIN_OCCURRENCES = 2  # ponytail: порог «≥2 из топ-K» взят без калибровки; менять только по данным eval
GENERIC = frozenset({"python", "javascript", "typescript", "ai", "llm", "machine-learning", "open-source", "hacktoberfest"})
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,49}").fullmatch  # формат topic на GitHub; защита от инъекции в Запрос
USED = re.compile(r"-?topic:([\w.-]+)", re.IGNORECASE)


def pick_topics(top: list[dict], queries: list[str]) -> list[str]:
    """До MAX_TOPICS topics, что встречаются минимум в MIN_OCCURRENCES строках top, без общих и уже заданных в Запросах."""
    used = {m.lower() for q in queries for m in USED.findall(q)}
    counts = Counter(t.lower() for r in top for t in set(r["topics"]))
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [t for t, n in ranked if n >= MIN_OCCURRENCES and SLUG(t) and t not in GENERIC and t not in used][:MAX_TOPICS]
