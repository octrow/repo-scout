# Usage details

## Search options

Each positional argument is a GitHub search query (`language:`, `topic:`, `in:readme`). Write 3-6 variants with synonyms. Leave out `stars:`: a project with few stars can still be the one you need.

- Round two builds up to 5 `topic:<slug>` queries from the most common topics in the top 10 (`--round2-k`, `--no-round2`).
- The Index adds its closest matches to the pool (`--from-index N`, default 50). It lives at `~/.local/share/repo-scout/index.db` (`$REPO_SCOUT_INDEX`).
- Rows below the closeness threshold (`--min-closeness`, 0.64) are dropped as off-topic. `--all` shows dropped rows as well.
- The top 10 with 50+ stars get a star-history check (`--stars-k`, `--no-stars-check`). The flag shows what share of the first ~1000 stars came on burst days. Bought stars and a viral launch look the same, so read the flag as a number and decide yourself.

Hard conditions: `--lang python`, `--must REGEX` (a required word group, repeatable), `--exclude REGEX` (forbidden words). Other options: `--months 6`, `--new-days 60`, `--limit 50`, `--json`. Run `repo-scout --help` for the full list.

## Runs and verdicts

Every search is saved as a run in `~/.local/share/repo-scout/runs/<date>-<slug>.json` (`$REPO_SCOUT_RUNS`). Use `--out FILE` to pick the path or `--no-save` to skip saving. Pass `--project P` to tie the run to a project.

```bash
repo-scout verdict owner/repo "→ Study (how the window hides from screen share)" --project P --task "..."
repo-scout gui [--port 8790]   # Search, Runs, Index, Eval
```

A verdict is stored in the Index and shown on later searches. It never hides a repo.

Progress goes to stderr and to `~/.local/state/repo-scout/run.log` (`$REPO_SCOUT_LOG`), so you can `tail -f` it from another terminal. Use `-q` to send it only to the log file.

## Evaluation

Golden sets in `eval/*.toml` hold a past search plus repos with known verdicts. They replay offline from GitHub snapshots and measure recall ([`eval/README.md`](../eval/README.md), [`eval/BASELINE.md`](../eval/BASELINE.md)).

```bash
repo-scout eval eval/*.toml [--no-round2] [--calls]      # offline, from snapshots
repo-scout eval eval/*.toml --llm-draft [--record]       # agent queries vs LLM draft vs union
repo-scout eval --fake-stars [--all-grid]                # precision/recall/FPR of the star-burst flag
```

## Publishing

This repo was prepared for publishing with [repo-publish](https://github.com/octrow/octrow-skills), a skill that checks history and secrets, then sets up installers, CI and releases. Its install and release templates are filled in here as the worked example.

## GUI language

The GUI is in English by default. Switch to Russian with EN | RU in the header; the choice is saved as `REPO_SCOUT_LANG` in `~/.config/repo-scout/.env`.
