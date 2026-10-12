#!/bin/sh
# repo-scout installer for macOS / Linux.
#   curl -LsSf https://raw.githubusercontent.com/octrow/repo-scout/main/install.sh | sh
#   ... | sh -s -- --version 0.1.0   # a specific release instead of the latest one
#   ... | sh -s -- --main            # current main branch instead of a release
#   ... | sh -s -- --no-launch       # install only, do not offer to start the GUI
#   ... | sh -s -- --uninstall       # remove the app, keep your runs and index
# Re-running it updates. REPO_SCOUT_SOURCE=<path or uv spec> installs from there instead (CI, local testing).
set -eu

REPO="octrow/repo-scout"
PYTHON="3.12"  # ponytail: pinned so onnxruntime/fastembed wheels exist; bump when they ship for newer Pythons
VERSION=""
MAIN=0
LAUNCH=1
UNINSTALL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --version) [ $# -ge 2 ] || { echo "--version needs a value, e.g. --version 0.1.0" >&2; exit 2; }
               VERSION="${2#v}"; shift ;;
    --main) MAIN=1 ;;
    --no-launch) LAUNCH=0 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) echo "options: --version X.Y.Z | --main | --no-launch | --uninstall"; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
# curl | sh takes stdin from the pipe, so interactive steps read the terminal directly
has_tty() { (: </dev/tty) 2>/dev/null; }
tty_run() { if has_tty; then "$@" </dev/tty; else "$@"; fi; }

export PATH="$HOME/.local/bin:$PATH"

if [ "$UNINSTALL" = 1 ]; then
  if have uv; then uv tool uninstall repo-scout || true; fi
  say "repo-scout removed. Your runs and index stay in ~/.local/share/repo-scout."
  exit 0
fi

# 1. uv: installs Python and the app into an isolated environment, no system Python needed
if ! have uv; then
  say "Installing uv, the Python package manager repo-scout runs on"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  have uv || die "uv was installed but is not on PATH. Open a new terminal and re-run this command."
fi

# 2. gh: every GitHub search goes through the official GitHub CLI
install_gh() {
  if have brew; then brew install gh
  elif have apt-get; then sudo apt-get update && sudo apt-get install -y gh
  elif have dnf; then sudo dnf install -y gh
  elif have pacman; then sudo pacman -S --noconfirm github-cli
  elif have zypper; then sudo zypper install -y gh
  else return 1
  fi
}
if ! have gh; then
  say "Installing the GitHub CLI (gh)"
  note "repo-scout searches GitHub through gh, which keeps your login in your system keychain."
  have brew || note "It comes from your system package manager, so you may be asked for your password (sudo)."
  if ! tty_run install_gh || ! have gh; then
    warn "Could not install gh automatically."
    note "Install it from https://cli.github.com/ (a single package for your system),"
    note "then re-run this command. Everything else is installed already."
  fi
fi

# 3. the app: a release wheel built and tested by CI, or the main branch
if [ -n "${REPO_SCOUT_SOURCE:-}" ]; then
  SPEC="$REPO_SCOUT_SOURCE"
elif [ "$MAIN" = 1 ]; then
  SPEC="repo-scout @ https://github.com/$REPO/archive/refs/heads/main.tar.gz"
else
  if [ -z "$VERSION" ]; then
    # /releases/latest redirects to /releases/tag/vX.Y.Z; with no release yet it lands on /releases
    URL="$(curl -fsSLo /dev/null -w '%{url_effective}' "https://github.com/$REPO/releases/latest")" \
      || die "Could not reach GitHub. Check your internet connection and re-run."
    case "$URL" in */tag/v*) VERSION="${URL##*/tag/v}" ;; *) die "No release published yet. Re-run with --main." ;; esac
  fi
  SPEC="repo-scout @ https://github.com/$REPO/releases/download/v$VERSION/repo_scout-$VERSION-py3-none-any.whl"
fi
say "Installing repo-scout${VERSION:+ $VERSION}"
uv tool install --reinstall --python "$PYTHON" "$SPEC"
uv tool update-shell >/dev/null 2>&1 || true
BIN="$(uv tool dir --bin)/repo-scout"

# 4. GitHub login, once
if have gh && ! gh auth status >/dev/null 2>&1; then
  if has_tty; then
    say "Log in to GitHub: a browser page opens, read-only access is enough"
    tty_run gh auth login --web --git-protocol https || warn "Login skipped. Run 'gh auth login' before your first search."
  else
    warn "Not logged in to GitHub. Run 'gh auth login' before your first search."
  fi
fi

# 5. download the embedding model now so the first search does not stall, then show what is ready
say "Checking the setup"
"$BIN" doctor --fix || warn "Fix the ✗ items above, then check again with: repo-scout doctor"

# 6. optional settings: asked once, skipped when a key is already saved
ENV_FILE="${REPO_SCOUT_ENV:-$HOME/.config/repo-scout/.env}"
if has_tty && ! grep -qs '^OMNIROUTE_API_KEY=' "$ENV_FILE"; then
  note "Optional: an LLM can turn a need written in any language into search queries."
  note "repo-scout works fully without it. You can set it up later with: repo-scout config"
  printf 'Set up the optional LLM draft now? (needs an OpenAI-compatible API key) [y/N] '
  read -r answer </dev/tty || answer=n
  case "$answer" in [yY]*) tty_run "$BIN" config || warn "Settings not saved. Run 'repo-scout config' later." ;; esac
fi

say "Installed. Start repo-scout any time with: repo-scout"
note "(open a new terminal if the command is not found; full path: $BIN)"
if [ "$LAUNCH" = 1 ] && has_tty; then
  printf 'Start repo-scout now? [Y/n] '
  read -r answer </dev/tty || answer=n
  case "$answer" in
    [nN]*) ;;
    *) say "Starting the GUI in your browser, press Ctrl+C here to stop it"; exec "$BIN" gui --open ;;
  esac
fi
