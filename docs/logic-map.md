# Logic map

How one search run flows through the code: where it splits, what each step decides, what changes without
an optional part (network, Index, API keys), and how it fails. Describes the code as it is. Terms are from
[`CONTEXT.md`](../CONTEXT.md); the triage methodology is [`docs/repo-triage.md`](repo-triage.md).

Every `Module:` line names `path::function`; `tests/test_logic_map.py` fails when one no longer exists.
Change a step → update this file in the same commit.

## Entry points

| Command | Goes to | Defaults that matter |
|---|---|---|
| `repo-scout --task T q1 q2…` | `cli._main` → `cli.run` | `--months 6`, `--limit 50` (max 100), `--min-closeness 0.64`, `--from-index 50`, `--round2-k 10`, `--stars-k 10`, fit on when `TYPESAFE_API_KEY` is set |
| `repo-scout` (no args), `repo-scout gui` | `gui.app.main` | opens the browser; port 8790 or the next free one |
| `repo-scout draft "<need>"` | `cli.draft_main` → `llm.draft` | needs `OMNIROUTE_API_KEY`; prints a ready `repo-scout …` command |
| `repo-scout verdict owner/repo "<verdict>" --project P --task T` | `cli.verdict_main` → `Index.add_verdict` | |
| `repo-scout eval eval/<set>.toml` | `evaluate.main` | `--replay` by default: no network |
| `repo-scout config`, `repo-scout doctor` | `config.main`, `doctor.main` | |

`--record DIR` / `--replay DIR` switch off the Index, run saving and fit, so a recording is reproducible.

## Main flow: one search

### 1. Parse and validate

Module: repo_scout/cli.py::_main, repo_scout/conditions.py::compile_all

`--exclude` / `--must` are compiled as regexes. A bad regex → `ValueError` → message on stderr, exit 2.
In replay, `now` is the recording date (`github.recorded_at`), so freshness matches the snapshot.

### 2. Build queries and search

Module: repo_scout/cli.py::build_query, repo_scout/cli.py::validate_query, repo_scout/github.py::search

Each query gets `in:name,description,topics,readme` (unless it is all qualifiers or has its own `in:`),
`mirror:false`, `language:<--lang>` and `pushed:>=<now − months>` (unless `--months 0` or the query has
its own `pushed:`). Over 256 text chars or more than 5 AND/OR/NOT → `ValueError` before any request.
Results are merged into the Pool by `owner/name`.

### 3. Pull nearest repos from the Index

Module: repo_scout/cli.py::_from_index, repo_scout/index.py::Index.top, repo_scout/github.py::refresh

Splits on: no Index (record/replay), no task, or `--from-index 0` → step skipped.
Top-N by Closeness not already in live results are re-fetched in one batch (metadata + README + commits).
Gone on GitHub (`NOT_FOUND`) → removed from the Index. Renamed → renamed in the Index. Failed for any other
reason (`github.last_failed`) → kept in the Index, skipped this run.

### 4. Triage on metadata

Module: repo_scout/triage.py::triage

Stop rules: `dead` (no push for 180 days, or 120 with under 500 commits), `toy` (under 50 commits and 0★),
`no code`. Flags: fork, `stars≫commits`, archived, new. Score = freshness + popularity points.
A repo with `pushedAt` null ages from `createdAt`.

### 5. Noise and hard conditions on metadata

Module: repo_scout/cli.py::_screen_meta, repo_scout/noise.py::noise_stop, repo_scout/conditions.py::lang_stop

Only rows not yet dropped. Template → flag. Noise needs 2+ independent signals to drop.
`--lang` checks `primaryLanguage`; `--exclude` checks name, description and topics.

### 6. Details: README and the last 20 commits

Module: repo_scout/cli.py::_screen_details, repo_scout/github.py::details, repo_scout/commits.py::last_substantive

Batches of 10 aliases, 3 in parallel. A failing batch is split in half; a single failing repo is retried,
then skipped with the `no details` flag. Freshness and `dead` are recomputed from the last substantive
commit (bots and cosmetic commits ignored); if none of the 20 are substantive → `cosmetic only` flag.
`--exclude` runs on the README too. `--must` needs a README: without one the row gets `no README`
and is not dropped.

### 7. Closeness

Module: repo_scout/cli.py::add_closeness, repo_scout/semantic.py::closeness, repo_scout/semantic.py::candidate_text

Local fastembed `BAAI/bge-small-en-v1.5`, CPU, offline after the first model download.
Document = name + description + topics + cleaned README (~2000 chars). Rows with a README are upserted into
the Index here. Below `--min-closeness` → `off-topic` stop rule.

### 8. Round two

Module: repo_scout/cli.py::_round2, repo_scout/round2.py::pick_topics

Splits on: no task or `--no-round2` → skipped. Up to 5 `topic:` queries from topics seen in 2+ of the
top-K rows, not generic, not already used. New repos go through steps 4–7 with source `round two`.

### 9. Sort, mark seen, flags, fit

Module: repo_scout/cli.py::sort_key, repo_scout/index.py::Index.seen, repo_scout/cli.py::add_stars_flag, repo_scout/systemone.py::add_fit

Sort: Closeness, then score, then fewer days since push. `seen` = past verdicts from the Index.
Star burst: top `--stars-k` kept rows with 50+★ (REST star history); a GitHub error skips the flag
with a warning. Fit: top 20 kept rows, one TypeSafe request; without a key nothing is sent; any error
is a warning. Neither flag nor fit drops or reorders rows.

### 10. Output and save

Module: repo_scout/cli.py::to_markdown, repo_scout/runs.py::save

Markdown table (or `--json`) of kept rows; rows dropped by `--must` listed separately.
The run, dropped rows included, is saved to `~/.local/share/repo-scout/runs/` unless `--no-save`,
`--record` or `--replay`. A save error is a warning, not a failure.

## Side flows

### LLM draft (before search)

Module: repo_scout/llm.py::draft, repo_scout/llm.py::parse_draft

Need → Task description, queries, hard conditions through an OpenAI-compatible API. JSON is taken from a
fenced block or the first decodable object; one retry on a malformed reply. Without a key: off.
In the GUI the button shows only with the key and `REPO_SCOUT_GUI_DRAFT=1` (eval gate failed, see
`eval/LLM-REPORT.md`).

### GUI

Module: repo_scout/gui/app.py::main, repo_scout/gui/search_page.py::search, repo_scout/gui/runs_logic.py::sorted_rows

The Search page builds the same argv (`cli.to_argv`) and runs `python -m repo_scout … --out PATH` as a
subprocess with a live log. Runs pages read the saved run JSON; the Index page talks to `Index` directly.

### Eval

Module: repo_scout/evaluate.py::eval_set, repo_scout/evaluate.py::metrics

Each `eval/*.toml` set runs the main flow on recorded snapshots with a fresh temporary Index and
`min_closeness=0`; the threshold is applied afterwards so `--sweep` can vary it. Recall counts
`→ Inspect` / `→ Deep dive` repos found.

## Where the flow splits by mode

| Part | Basic (default) | `--replay` | `--record` | Advanced (keys set) |
|---|---|---|---|---|
| GitHub | live via `gh` | snapshots only, missing → error | live + writes snapshots | live |
| Index read/write | yes | no | no | yes |
| Run saved | yes | no | no | yes |
| Star burst | top 10 | from snapshots | live | top 10 |
| Fit | off | off | off | top 20 |
| LLM draft | off | cached replies | live + cache | on |

## How it fails

| Failure | Result |
|---|---|
| Bad regex, query over GitHub limits | exit 2 with the reason, no request sent |
| `gh` not logged in, plain 403 | `GitHub: …`, exit 1 |
| 429 / 502 / rate limit / empty reply | retries with backoff 5–60 s, then exit 1 |
| One repo keeps failing in a batch | skipped with a warning, `no details`; kept in the Index |
| Star history, fit, run save errors | warning; the table is still printed |

## Known gaps

- Hand-edited run JSON with wrong-typed fields (`score: null`, `flags: null`) breaks the GUI run page;
  files the app writes are always well-typed.
- Shared eval details are not tied to each set's snapshot date (see `PLAN.md`, Phase 9.1).
