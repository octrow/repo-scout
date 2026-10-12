"""`repo-scout doctor [--fix]`: is this machine ready to search? One line per check with a fix hint."""
import argparse
import shutil
import subprocess
import sys

from repo_scout import llm, semantic

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
    """Extras that never fail the check: everything works without them."""
    if not llm.available():
        return ["○ LLM draft (optional): off — to turn it on run: repo-scout config"]
    gui = "with" if llm.gui_enabled() else "without"
    return [f"✓ LLM draft (optional): on, model {llm.model()}, {gui} the GUI button"]


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
