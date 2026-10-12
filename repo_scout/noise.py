"""Noise (awesome / tutorial / demo / homework / spam) and 'template' flag. Words from github-hidden-gems filtering/rules.py."""
import re

from repo_scout.triage import topics_of

MIN_SIGNALS = 2

# kind -> (words in name, phrases in description, topics)
KINDS: dict[str, tuple[set, tuple, set]] = {
    "awesome": ({"awesome"}, ("awesome list", "curated list", "a curated", "curated collection"),
                {"awesome", "awesome-list", "curated-list"}),
    "tutorial": ({"tutorial", "workshop", "bootcamp", "101"},
                 ("tutorial", "step by step", "learn how to", "online course", "bootcamp", "for beginners"),
                 {"tutorial", "tutorials", "course", "workshop", "bootcamp"}),
    "demo": ({"demo", "sample", "example", "playground", "poc", "showcase"},
             ("demo", "sample app", "example app", "proof of concept", "poc", "playground", "showcase"),
             {"demo", "sample", "example", "examples", "playground"}),
    "homework": ({"homework", "assignment", "coursework", "hw", "lab", "exercise", "lesson", "exam"},
                 ("homework", "assignment", "coursework", "course project", "class project", "school project",
                  "my solutions", "lab work"),
                 {"homework", "assignment", "coursework", "student-project", "school-project",
                  "university-project", "exercises", "classroom"}),
    "spam": ({"keygen", "crack", "cracked"},
             ("revolutionary", "world's best", "best ever", "guaranteed", "10x", "passive income", "get rich",
              "buy now", "join now", "money machine", "free followers", "free robux", "free money"),
             {"keygen", "crack", "cheat", "free-money"}),
}
TEMPLATE = ({"template", "boilerplate", "starter", "scaffold", "cookiecutter"},
            ("template", "boilerplate", "starter kit", "scaffold", "cookiecutter"),
            {"template", "boilerplate", "starter", "scaffold", "cookiecutter"})


def _signals(node: dict, words: set, phrases: tuple, topics: set) -> list[str]:
    tokens = re.split(r"[^a-z0-9]+", node["nameWithOwner"].split("/")[-1].lower())
    desc = (node.get("description") or "").lower()
    found = []
    if any(t in words or t.rstrip("s") in words for t in tokens):
        found.append("name")
    if any(re.search(rf"\b{re.escape(p)}s?\b", desc) for p in phrases):
        found.append("description")
    if topics & {t.lower() for t in topics_of(node)}:
        found.append("topics")
    return found


def is_template(node: dict) -> bool:
    return bool(node.get("isTemplate")) or bool(_signals(node, *TEMPLATE))


def noise_stop(node: dict) -> str | None:
    """'noise (kind: sources)' when >=2 independent signals match. Template is only a flag and doesn't prevent noise."""
    best = max(((kind, _signals(node, *spec)) for kind, spec in KINDS.items()), key=lambda x: len(x[1]))
    kind, found = best
    return f"noise ({kind}: {', '.join(found)})" if len(found) >= MIN_SIGNALS else None
