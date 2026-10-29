"""`repo-scout config`: turn on advanced mode by filling the settings file (~/.config/repo-scout/.env) interactively.

Basic mode needs none of this: search, triage and ranking work without any key or external model.
"""
import argparse
import getpass
import os
from collections.abc import Callable
from pathlib import Path

from repo_scout import llm, systemone

OMNIROUTE_URL = "https://github.com/diegosouzapw/OmniRoute"
# (title, hint, fields); field = (variable, prompt, default, secret); the first field is the section's key
SECTIONS = (
    ("LLM draft: a model writes search queries from your request in any language.",
     "Any OpenAI-compatible endpoint works.\n"
     f"Free: OmniRoute ({OMNIROUTE_URL}) runs on your computer. The defaults below point at it.\n"
     "Ollama: base URL http://localhost:11434/v1, any key (for example ollama), a model such as qwen3.",
     ((llm.KEY_VAR, "API key", "", True),
      (llm.URL_VAR, "Base URL", llm.DEFAULT_URL, False),
      (llm.MODEL_VAR, "Model", llm.DEFAULT_MODEL, False),
      (llm.GUI_VAR, "Show the Draft button in the GUI? 1 = yes, 0 = no", "0", False))),
    ("Fit: Jev by TypeSafe rates how well each top result fits your task.",
     f"Get a key: {systemone.KEYS_URL}",
     ((systemone.KEY_VAR, "TypeSafe API key", "", True),)),
)
CLEAR = "-"
INTRO = """Advanced mode adds external models. Basic search works without them.
Press Enter to keep the value in [brackets]. Type - to clear it.
Leave a key empty to skip that part."""


def update_env(path: Path, values: dict[str, str]) -> None:
    """Set KEY=VALUE lines in place, keep other lines and comments; an empty value removes the key."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    todo = dict(values)
    seen = set()
    out = []
    for line in lines:
        key = line.strip().removeprefix("export ").partition("=")[0].strip()
        if key not in values:
            out.append(line)
        elif key not in seen:  # first occurrence gets the value, later duplicates are dropped
            seen.add(key)
            if todo.pop(key):
                out.append(f"{key}={values[key]}")
    out += [f"{k}={v}" for k, v in todo.items() if v]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # holds API keys: never world-readable
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.chmod(path, 0o600)  # tighten a pre-existing file


def _shown(value: str, secret: bool) -> str:
    return f"…{value[-4:]}" if secret and value else value


def ask_values(current: dict[str, str], ask: Callable[[str], str], ask_secret: Callable[[str], str],
               say: Callable[[str], None] = lambda _: None) -> dict[str, str]:
    """Prompt each section; an empty key skips the rest of its section."""
    out = {}
    for title, hint, fields in SECTIONS:
        say(f"\n{title}\n{hint}")
        for var, prompt, default, secret in fields:
            now = current.get(var) or current.get(llm.ALIASES.get(var, "")) or default
            answer = (ask_secret if secret else ask)(f"{prompt} [{_shown(now, secret)}]: ").strip()
            value = "" if answer == CLEAR else answer or now
            out[var] = "" if value == default and not secret else value  # defaults need no line in the file
            if var in llm.ALIASES:
                out[llm.ALIASES[var]] = ""  # the new name replaces the older alias line
            if secret and not value:
                break
    return out


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="repo-scout config", description=INTRO)
    ap.parse_args(argv)
    path = llm.user_env_path()
    print(f"{INTRO}\nSettings file: {path}")
    update_env(path, ask_values(llm.parse_env(path), input, getpass.getpass, print))
    print("\nSaved. To see what is on, run: repo-scout doctor")
