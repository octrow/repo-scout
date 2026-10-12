"""`repo-scout doctor [--fix]`: is this machine ready to search? One line per check with a fix hint."""
import argparse
import shutil
import subprocess
import sys

from repo_scout import config, llm, semantic, systemone

GH_URL = "https://cli.github.com/"
LOGIN_HINT = "run: gh auth login --web"


def _load_model(local_only: bool) -> None:
    from fastembed import TextEmbedding  # lazy import: model loading is heavy
    from loguru import logger
    logger.disable("fastembed")  # a cache miss is logged as ERROR; the check reports it instead
    TextEmbedding(semantic.MODEL, cache_dir=semantic.cache_dir(), local_files_only=local_only)


def _model_check(fix: bool) -> tuple[bool, str, str]:
    label = f"embedding model {semantic.MODEL}"
    try:
        _load_model(local_only=True)
        return True, label, ""
    except Exception:  # noqa: BLE001 — any load failure means "not usable offline"
        if not fix:
            return False, label, "run: repo-scout doctor --fix (downloads ~65 MB once)"
    print(f"Downloading {label} (~65 MB, one time)…", flush=True)
    try:
        _load_model(local_only=False)
        return True, label, ""
    except Exception as e:  # noqa: BLE001 — network/disk errors become a hint, the first search retries
        return False, label, f"download failed ({e}); the first search will retry"


def checks(fix: bool = False) -> list[tuple[bool, str, str]]:
    gh = shutil.which("gh") is not None
    out = [(gh, "GitHub CLI (gh) installed", f"install it from {GH_URL}")]
    authed = gh and subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0
    out.append((authed, "gh logged in to GitHub", LOGIN_HINT))
    return [*out, _model_check(fix)]


def optional() -> list[str]:
    """Advanced mode: extras that never fail the check, since basic mode works without them."""
    draft, fit = llm.available(), systemone.available()
    on = [name for name, ok in (("LLM draft", draft), ("fit", fit)) if ok]
    lines = [f"Mode: advanced ({', '.join(on)})" if on else "Mode: basic (no external models)"]
    if draft:
        gui = "with" if llm.gui_enabled() else "without"
        lines.append(f"✓ LLM draft: model {llm.model()} at {llm.setting(llm.URL_VAR, llm.DEFAULT_URL)}, {gui} the GUI button")
    else:
        lines.append(f"○ LLM draft (optional): off — free with OmniRoute ({config.OMNIROUTE_URL}) or Ollama")
    if fit:
        lines.append(f"✓ fit: model {systemone.model()}")
    else:
        lines.append(f"○ fit (optional): off — Jev by TypeSafe, key at {systemone.KEYS_URL}")
    if not (draft and fit):
        lines.append("  turn these on with: repo-scout config")
    return lines


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="repo-scout doctor", description="Check that repo-scout is ready to search")
    ap.add_argument("--fix", action="store_true", help="download the embedding model if it is missing")
    a = ap.parse_args(argv)
    results = checks(a.fix)
    for ok, label, hint in results:
        print(f"✓ {label}" if ok else f"✗ {label} — {hint}")
    print(*optional(), sep="\n")
    if not all(ok for ok, _, _ in results):
        sys.exit(1)
