"""`repo-scout config`: fill in the optional settings file (~/.config/repo-scout/.env) interactively.

Everything here is optional: search, triage and ranking work without any key.
"""
import argparse
import getpass
import os
from collections.abc import Callable
from pathlib import Path

from repo_scout import llm

# (variable, prompt, default, secret)
FIELDS = (
    (llm.KEY_VAR, "API key of an OpenAI-compatible endpoint", "", True),
    (llm.URL_VAR, "Endpoint base URL", llm.DEFAULT_URL, False),
    (llm.MODEL_VAR, "Model", llm.DEFAULT_MODEL, False),
    (llm.GUI_VAR, "Show the Draft button in the GUI (1 = yes, 0 = no)", "0", False),
)
CLEAR = "-"
INTRO = """Optional: LLM draft turns a need written in any language into a task description and queries.
repo-scout works fully without it. Press Enter to keep the value in [brackets], type - to clear it."""


def update_env(path: Path, values: dict[str, str]) -> None:
    """Set KEY=VALUE lines in place, keep other lines and comments; an empty value removes the key."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    todo = dict(values)
    out = []
    for line in lines:
        key = line.strip().removeprefix("export ").partition("=")[0].strip()
        if key in todo:
            value = todo.pop(key)
            if value:
                out.append(f"{key}={value}")
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in todo.items() if v]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)  # holds an API key


def _shown(value: str, secret: bool) -> str:
    return f"…{value[-4:]}" if secret and value else value


def ask_values(current: dict[str, str], ask: Callable[[str], str], ask_secret: Callable[[str], str]) -> dict[str, str]:
    """Prompt each field; stop after an empty key, since the rest only matters with a key."""
    out = {}
    for var, prompt, default, secret in FIELDS:
        now = current.get(var) or default
        answer = (ask_secret if secret else ask)(f"{prompt} [{_shown(now, secret)}]: ").strip()
        value = "" if answer == CLEAR else answer or now
        out[var] = "" if value == default and not secret else value  # defaults need no line in the file
        if var == llm.KEY_VAR and not value:
            break
    return out


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="repo-scout config", description=INTRO)
    ap.parse_args(argv)
    path = llm.user_env_path()
    print(f"{INTRO}\nSettings file: {path}\n")
    values = ask_values(llm.parse_env(path), input, getpass.getpass)
    update_env(path, values)
    state = "on" if values.get(llm.KEY_VAR) else "off"
    print(f"\nSaved. LLM draft is {state}. Check everything with: repo-scout doctor")
