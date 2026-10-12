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
    ("LLM draft: any OpenAI-compatible endpoint turns a need in any language into a task description and queries",
     f"Free option: OmniRoute ({OMNIROUTE_URL}) runs locally; the defaults below point at it.\n"
     "Ollama works too: base URL http://localhost:11434/v1, any key (e.g. ollama), model e.g. qwen3.",
     ((llm.KEY_VAR, "API key", "", True),
      (llm.URL_VAR, "Base URL", llm.DEFAULT_URL, False),
      (llm.MODEL_VAR, "Model", llm.DEFAULT_MODEL, False),
      (llm.GUI_VAR, "Show the Draft button in the GUI (1 = yes, 0 = no)", "0", False))),
    ("Fit: a System One model (Jev by TypeSafe) rates how well each top result fits your task",
     f"Get an API key at {systemone.KEYS_URL}",
     ((systemone.KEY_VAR, "TypeSafe API key", "", True),)),
)
CLEAR = "-"
INTRO = """Advanced mode adds external models on top of the basic search, which works fully without them.
Press Enter to keep the value in [brackets], type - to clear it, leave a key empty to skip that part."""


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
    os.chmod(path, 0o600)  # holds API keys


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
    print("\nSaved. See what is on with: repo-scout doctor")
