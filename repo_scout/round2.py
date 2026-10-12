"""Round two: `topic:<slug>` queries from frequent topics among top candidates of the first pass."""
import re
from collections import Counter

ROUND2_K = 10  # number of top rows examined from first pass
MAX_TOPICS = 5  # limit of round two queries
MIN_OCCURRENCES = 2  # threshold: >=2 in top-K
GENERIC = frozenset({"python", "javascript", "typescript", "ai", "llm", "machine-learning", "open-source", "hacktoberfest"})
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,49}").fullmatch  # GitHub topic format; prevents query injection
USED = re.compile(r"-?topic:([\w.-]+)", re.IGNORECASE)


def pick_topics(top: list[dict], queries: list[str]) -> list[str]:
    """Up to MAX_TOPICS topics occurring in at least MIN_OCCURRENCES rows of top, excluding generic and already used topics."""
    used = {m.lower() for q in queries for m in USED.findall(q)}
    counts = Counter(t.lower() for r in top for t in set(r["topics"]))
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [t for t, n in ranked if n >= MIN_OCCURRENCES and SLUG(t) and t not in GENERIC and t not in used][:MAX_TOPICS]
