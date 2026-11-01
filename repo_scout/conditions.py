"""Hard conditions: language, forbidden and required words. Violations return a stop reason."""

import re

MATCH_SHOWN = 40


# GitHub search takes linguist aliases (`language:cpp`) but reports the display name ("C++").
# ponytail: common aliases only; another alias still drops every row. Upgrade: linguist's languages.yml.
LANG_ALIASES = {
    "cpp": "c++",
    "golang": "go",
    "csharp": "c#",
    "cake": "c#",
    "js": "javascript",
    "node": "javascript",
    "ts": "typescript",
    "python3": "python",
    "rb": "ruby",
    "rs": "rust",
    "sh": "shell",
    "bash": "shell",
    "zsh": "shell",
    "objc": "objective-c",
    "obj-c": "objective-c",
    "objectivec": "objective-c",
    "fsharp": "f#",
    "elisp": "emacs lisp",
    "vim": "vim script",
    "viml": "vim script",
    "vimscript": "vim script",
    "pwsh": "powershell",
    "posh": "powershell",
}


def _canonical_lang(name: str) -> str:
    return LANG_ALIASES.get(name.lower(), name.lower())


def lang_stop(row: dict, lang: str | None) -> str | None:
    if lang and row["lang"] and _canonical_lang(row["lang"]) != _canonical_lang(lang):
        return f"wrong language ({row['lang']})"
    return None


def meta_text(row: dict) -> str:
    return " ".join([row["repo"], row["desc"], *row["topics"]])


def compile_all(flag: str, patterns: list[str]) -> list[re.Pattern]:
    """Compile regexes (case-insensitive) before network calls; errors raise ValueError."""
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
            return f"forbidden: {m.group(0)[:MATCH_SHOWN]}"
    return None


def must_stop(text: str, groups: list[re.Pattern]) -> str | None:
    """All groups must be present in the text."""
    for g in groups:
        if not g.search(text):
            return f"missing required: {g.pattern}"
    return None
