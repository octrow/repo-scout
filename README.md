<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="repo-scout: find the repo you can build on before you write your own. In one real run, 282 candidates became 119 kept and ranked by closeness, 76 dropped as off-topic, and 87 dropped as dead, noise or toy.">
</p>

<p align="center">
  <a href="https://github.com/octrow/repo-scout/actions/workflows/test.yml"><img src="https://github.com/octrow/repo-scout/actions/workflows/test.yml/badge.svg" alt="test"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+">
</p>

<p align="center">
  <b>English</b> | <a href="README.ru.md">Русский</a>
</p>

Search GitHub for something you can reuse before you write it yourself. Small new projects count too: they rank by how close they are to your task, not by stars.

<p align="center">
  <img src="./assets/readme/triage.svg" width="100%" alt="Rows from a real run looking for README-audit tools. A 22-star repo ranks first at closeness 0.84. Flags mark a new repo, a 100% early star burst and cosmetic-only commits without dropping them. Stop rules drop github-readme-stats (79,824 stars, 309 days idle), awesome-go (an awesome list), a 2-commit toy, and an off-topic repo at closeness 0.63.">
</p>

repo-scout runs several GitHub searches, merges the results, and does the mechanical first pass of [`docs/repo-triage.md`](docs/repo-triage.md). That pass covers stop rules (dead, toy, noise, no code, off-topic), flags (fork, stars ≫ commits, archived, new, template, cosmetic-only commits, star burst), and freshness and popularity scores. Results are sorted by semantic closeness to your task description, computed by a local CPU embedding model. Ranking never calls an LLM.

## Install

One command. It installs [uv](https://docs.astral.sh/uv/) (which brings its own Python) and the [GitHub CLI](https://cli.github.com/) if they are missing, installs the latest [release](https://github.com/octrow/repo-scout/releases), walks you through `gh auth login` once, downloads the local embedding model, and offers to open the GUI.

```bash
# macOS / Linux
curl -LsSf https://raw.githubusercontent.com/octrow/repo-scout/main/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/octrow/repo-scout/main/install.ps1 | iex"
```

Run the same command again to update. Options: `sh -s -- --version 0.1.0`, `--main` (current main branch instead of a release), `--no-launch`, `--uninstall` (keeps your runs and index). On Windows set `$env:REPO_SCOUT_VERSION`, `$env:REPO_SCOUT_MAIN=1`, `$env:REPO_SCOUT_NO_LAUNCH=1` or `$env:REPO_SCOUT_UNINSTALL=1` first.

Something not working? `repo-scout doctor` checks gh, the GitHub login and the model, and says how to fix each one.

### Or download a ready build

Each [release](https://github.com/octrow/repo-scout/releases/latest) has standalone builds that need no Python and no uv. Unpack the archive and run `repo-scout` inside it (on Windows, double-click `repo-scout.exe`). With no arguments it opens the GUI in your browser.

| System | File |
|---|---|
| Windows x64 | `repo-scout-<version>-windows-x86_64.zip` |
| macOS Apple Silicon | `repo-scout-<version>-macos-arm64.tar.gz` |
| Linux x64 (glibc 2.35+, e.g. Ubuntu 22.04+) | `repo-scout-<version>-linux-x86_64.tar.gz` |
| Linux arm64 | `repo-scout-<version>-linux-arm64.tar.gz` |

You still need the [GitHub CLI](https://cli.github.com/) with `gh auth login` done once; `repo-scout doctor --fix` checks it and downloads the model. The builds are not code-signed: Windows SmartScreen asks you to confirm ("More info" → "Run anyway"), and on macOS a browser-downloaded build needs `xattr -dr com.apple.quarantine repo-scout` once. An Intel Mac can use the one-command install.

## Quick start

From a clone, with Python 3.11+, uv and an authenticated `gh`:

```bash
uv sync && uv tool install --editable .   # puts `repo-scout` on PATH
repo-scout --task "Live speech transcription with an overlay, runs on Linux" \
  "whisper live transcription" "speech to text overlay language:python" "topic:asr linux"
repo-scout                                # no arguments: opens the GUI in your browser
```

## How a search works

1. **Queries**: each positional argument is a GitHub search query (`language:`, `topic:`, `in:readme`). Write 3–6 variants with synonyms. Don't add `stars:`, since few stars is no reason to drop a project.
2. **Round two** runs on its own. It builds up to 5 `topic:<slug>` queries from the most common topics in the top 10 (`--round2-k`, `--no-round2`).
3. **Index**: the local store of past candidates and their READMEs adds its closest matches to the pool (`--from-index N`, default 50). It lives at `~/.local/share/repo-scout/index.db` (`$REPO_SCOUT_INDEX`).
4. **Triage** applies stop rules and flags. Rows below the closeness threshold (`--min-closeness`, 0.64) are dropped as off-topic. `--all` shows dropped rows as well.
5. **Star burst**: the top 10 with ≥50★ get a star-history check (`--stars-k`, `--no-stars-check`). The flag shows what share of the first ~1000★ came on burst days. Bought stars and a viral launch look the same, so treat the flag as a measurement and not a verdict.

Hard conditions: `--lang python`, `--must REGEX` (a required word group, repeatable), `--exclude REGEX` (forbidden words). Other options: `--months 6`, `--new-days 60`, `--limit 50`, `--json`. Run `repo-scout --help` for the full list.

## Runs, verdicts and the GUI

Every search is saved as a run in `~/.local/share/repo-scout/runs/<date>-<slug>.json` (`$REPO_SCOUT_RUNS`). Use `--out FILE` to pick the path or `--no-save` to skip saving. Pass `--project P` to tie the run to a project.

```bash
repo-scout verdict owner/repo "→ Study (how the window hides from screen share)" --project P --task "..."
repo-scout gui [--port 8790]   # Search, Runs, Index, Eval
```

A verdict is stored in the Index and shown on later searches. It never hides a repo. The GUI opens saved runs as a filterable table with READMEs from the Index and two-click verdicts. It runs searches and evals as subprocesses with a live log and a cancel button. The GUI is built on a vendored copy of nicegui-kit ([`repo_scout/gui/kit/VENDORED.md`](repo_scout/gui/kit/VENDORED.md)).

Progress goes to stderr and to `~/.local/state/repo-scout/run.log` (`$REPO_SCOUT_LOG`), so you can `tail -f` it from another terminal. Use `-q` to send it only to the log file.

## Optional LLM draft

Everything above works without any API key. The LLM draft is an extra: with `OMNIROUTE_API_KEY` set, a model can turn a need written in any language into a task description, queries and hard conditions. It only fills in the form. You still review it and run the search yourself.

```bash
repo-scout draft "<what you need, any language>"   # prints a ready `repo-scout …` command
```

| Variable | Default |
|---|---|
| `OMNIROUTE_API_KEY` | none (the feature is off without it) |
| `OMNIROUTE_MODEL` | `free-stack` |
| `OMNIROUTE_BASE_URL` | `http://127.0.0.1:20128/v1` (OpenAI-compatible `/chat/completions`) |

`repo-scout config` asks for these and saves them to `~/.config/repo-scout/.env` (`$REPO_SCOUT_ENV`, readable only by you). Press Enter to keep a value, type `-` to clear it. `repo-scout doctor` shows whether the draft is on. Real environment variables take precedence over the file. In a clone, a git-ignored `.env` in the repo root works too and overrides the user file. `REPO_SCOUT_GUI_DRAFT=1` shows the Draft button in the GUI.

## Evaluation

Golden sets in `eval/*.toml` hold a past search plus repos with known verdicts. Replayed offline from GitHub snapshots, they measure recall ([`eval/README.md`](eval/README.md), [`eval/BASELINE.md`](eval/BASELINE.md)).

```bash
repo-scout eval eval/*.toml [--no-round2] [--calls]      # offline, from snapshots
repo-scout eval eval/*.toml --llm-draft [--record]       # agent queries vs LLM draft vs union
repo-scout eval --fake-stars [--all-grid]                # precision/recall/FPR of the star-burst flag
```

## Agent skill

[`skill/SKILL.md`](skill/SKILL.md) teaches a coding agent the full workflow: search, inspection and verdicts. Install it with `ln -s "$PWD/skill" ~/.agents/skills/repo-scout`.

## Development

```bash
uv sync && uv run pytest -q
```

The domain glossary is in [`CONTEXT.md`](CONTEXT.md), and design decisions are in [`docs/adr/`](docs/adr/).

## License

[MIT](LICENSE). Third-party code, data and fonts are listed in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
