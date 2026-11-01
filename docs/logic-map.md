# Logic map

How one search run flows through the code: where it splits, what each step decides, what changes without
an optional part (network, Index, API keys), and how it fails. Describes the code as it is. Terms are from
[`CONTEXT.md`](../CONTEXT.md); the triage methodology is [`docs/repo-triage.md`](repo-triage.md).
Known logic gaps are numbered in `PLAN.md` → "Logic map findings" (`#N` below).

Every `Module:` line names `path::function`; `tests/test_logic_map.py` fails when one no longer exists.
Change a step → update this file in the same commit.

## The flow at a glance

```
task + queries + flags
  │
  ├─ 1  Parse ................ are the regexes valid, what is "now"
  ├─ 2  Search ............... which repos GitHub returns per query
  ├─ 3  From Index ........... which known repos join the Pool
  ├─ 4  Triage ............... dead / toy / no code on metadata
  ├─ 5  Noise, --lang ........ template, noise, wrong language, forbidden words
  ├─ 6  Details .............. README + 20 commits: real freshness, README conditions
  ├─ 7  Closeness ............ is it on topic; Index upsert
  ├─ 8  Round two ............ topic: queries from the top rows, steps 4–7 again
  ├─ 9  Sort, flags, fit ..... order, seen, star burst, fit (never drop rows)
  └─ 10 Output, save
  │
Markdown table / JSON + run JSON
```

## Entry points

| Command | Goes to | Defaults that matter |
|---|---|---|
| `repo-scout --task T q1 q2…` (also `python -m repo_scout`) | `cli._main` → `cli.run` | `--months 6`, `--new-days 60`, `--limit 50` (max 100), `--min-closeness 0.64`, `--from-index 50`, `--round2-k 10`, `--stars-k 10`; fit on when `TYPESAFE_API_KEY` is set |
| `repo-scout` (no args) | `gui.app.main` with `--open` | opens the browser |
| `repo-scout gui …` | `gui.app.main` | does not open the browser |
| `repo-scout draft "<need>"` | `cli.draft_main` → `llm.draft` | needs `LLM_API_KEY` (old name `OMNIROUTE_API_KEY`); URL `http://127.0.0.1:20128/v1`, model `free-stack`; prints a ready `repo-scout …` command |
| `repo-scout verdict owner/repo "<verdict>" --project P --task T` | `cli.verdict_main` → `Index.add_verdict` | `--project`, `--task` required |
| `repo-scout eval eval/<set>.toml` | `evaluate.main` | `--replay` by default; fixed `months=6`, `new_days=60`, `limit=50`, stars and fit off |
| `repo-scout config`, `repo-scout doctor` | `config.main`, `doctor.main` | `config` writes `~/.config/repo-scout/.env` (0600); `doctor --fix` downloads the model |

Keys and settings: real environment first, then the checkout's `.env`, then `~/.config/repo-scout/.env`.
GUI port: 8790; held by another program → asks (no TTY: moves on), held by our GUI → asks to restart
(no TTY: prints the link and exits); scans up to 50 ports.
`--record DIR` / `--replay DIR` switch off the Index, run saving and fit; the star burst still runs (step 9).
`--out` is ignored under them.

## Main flow: one search

### 1. Parse and validate

Module: repo_scout/cli.py::_main, repo_scout/conditions.py::compile_all

`--exclude` / `--must` are compiled as regexes. A bad regex → `ValueError` → message on stderr, exit 2.
Any later `ValueError` inside the run also exits 2, with no table and no save.
In replay, `now` is the recording date (`github.recorded_at`), so freshness matches the snapshot.

### 2. Build queries and search

Module: repo_scout/cli.py::build_query, repo_scout/cli.py::validate_query, repo_scout/github.py::search

Each query gets `in:name,description,topics,readme` (unless it is all qualifiers or has its own `in:`),
`mirror:false` and `language:<--lang>` (unless the query has its own), and `pushed:>=<now − months>`
(unless `--months 0` or the query has its own `pushed:`). `--lang` is appended unquoted.
Queries are validated one by one, just before each is sent: over 256 text chars or more than 5
AND/OR/NOT → exit 2 after the earlier queries already ran (#11). The GUI validates all of them up front.
Results are merged into the Pool by `owner/name`.

### 3. Pull nearest repos from the Index

Module: repo_scout/cli.py::_from_index, repo_scout/index.py::Index.top, repo_scout/github.py::refresh, repo_scout/cli.py::qualifier_stop

Splits on: no Index (record/replay), no task, or `--from-index 0` → step skipped.
Takes the N closest repos (no floor) that are not already in live results.
They are re-fetched in sequential chunks of 10 (metadata + README + commits); rows get source `index`.
Gone on GitHub (`NOT_FOUND`) → removed from the Index. Renamed → renamed in the Index. Failed for any other
reason (`github.last_failed`) → kept in the Index, left out of this run.
Index rows skip the search query, so after triage (step 4) they get its qualifiers as stop rules: pushed
before `now − months` → `pushed before <date>`, `--lang` with no language → `no language`. `mirror:false`
is not checked (no `isMirror` field).

### 4. Triage on metadata

Module: repo_scout/triage.py::triage

Stop rules, first match wins: `dead` (no push for 180 days, or 120 with under 500 commits), `toy` (under
50 commits and 0★), `no code` (0 commits, so only with stars). Above `--months 6` the `dead` limits grow to 30 × months
(and 2/3 of that); `--months 0` turns `dead` off.
Flags: fork, `stars≫commits` (1000★+ and over 20× commits), archived, new (`--new-days`).
Score = freshness + popularity points. A repo with `pushedAt` null ages from `createdAt`.

### 5. Noise and hard conditions on metadata

Module: repo_scout/cli.py::_screen_meta, repo_scout/noise.py::noise_stop, repo_scout/conditions.py::lang_stop

Only rows not yet dropped. Template → flag. Noise needs 2+ independent signals of one kind to drop.
`--lang` compares `primaryLanguage` case-insensitively after mapping common GitHub aliases (`cpp` → `C++`,
`golang` → `Go`); an empty language passes, an alias not in the list drops every row. `--exclude` checks the repo name (no owner login), description and topics.

### 6. Details: README and the last 20 commits

Module: repo_scout/cli.py::_screen_details, repo_scout/github.py::details, repo_scout/commits.py::last_substantive

Batches of 10 aliases, 3 in parallel. A failing batch is split in half without retries; a single failing
repo is retried, then skipped with the `no details` flag (#9). A README is one of 8 case-sensitive names at
HEAD (`README.md`, `readme.md`, `README.rst`, `README`, `Readme.md`, `README.markdown`, `README.txt`,
`README.org`), cut to 100 000 chars.
Freshness and `dead` are recomputed from the last substantive commit (bots, cosmetic and `Merge…` commits
ignored; commits dated after `now` ignored). None of the 20 substantive → `cosmetic only` flag and
freshness from the oldest of the 20, which can make the row `dead`.
`--exclude` runs on the README too. `--must` runs on README + name + description + topics; without a
README the row gets `no README` and `--must` checks the metadata only. `no details` rows skip both.

### 7. Closeness

Module: repo_scout/cli.py::add_closeness, repo_scout/semantic.py::closeness, repo_scout/semantic.py::candidate_text

Local fastembed `BAAI/bge-small-en-v1.5`, CPU, offline after the first model download.
Document = name + description + topics + cleaned README (~2000 chars).
Rows still alive with a non-empty README are upserted into the Index here, before the threshold, so
off-topic rows are stored too. Below `--min-closeness` → `off-topic` stop rule.

### 8. Round two

Module: repo_scout/cli.py::_round2, repo_scout/round2.py::pick_topics

Splits on: no task or `--no-round2` → skipped. Up to 5 `topic:` queries from topics seen in 2+ of the
top-K rows with Closeness ≥ max(`--min-closeness`, 0.64) (#13), not generic, not in the user's queries.
New repos go through steps 4–7 with source `round two`; no Index pull in this round.

### 9. Sort, mark seen, flags, fit

Module: repo_scout/cli.py::sort_key, repo_scout/index.py::Index.seen, repo_scout/cli.py::add_stars_flag, repo_scout/systemone.py::add_fit

Sort: Closeness, then score, then fewer days since push. `seen` = past verdicts from the Index.
Star burst: top `--stars-k` kept rows with 50+★ (REST star history, up to 20 pages per repo; needs a
complete history and 30+★); a GitHub error skips the flag with a warning.
Fit: top 20 kept rows, one TypeSafe request, text capped at 1000 chars per row; without a key nothing is
sent; any error is a warning. Neither flag nor fit drops or reorders rows.

### 10. Output and save

Module: repo_scout/cli.py::to_markdown, repo_scout/runs.py::save

Markdown table (or `--json`) of kept rows (`--all`: dropped rows too); rows dropped by `--must` are listed
separately and never in the table. After printing, the run, dropped rows included, is saved to
`--out`, `REPO_SCOUT_RUNS` or `~/.local/share/repo-scout/runs/` unless `--no-save`, `--record` or
`--replay`. An `OSError` on save is a warning.

## What a run writes

| Write | When | Skipped by |
|---|---|---|
| Log file, pruned to 1 GiB (`REPO_SCOUT_LOG`) | every search | — |
| Index DB created; re-embeds all rows if the stored model differs (`REPO_SCOUT_INDEX`) | opened on start | record/replay |
| Index rename / forget (step 3), upsert (step 7); forget of rows dropped as `dead`, `toy`, `no code`, noise (verdicts stay) | every run with an Index | record/replay; **not** `--no-save` |
| Run JSON (step 10) | every run | `--no-save`, record, replay |
| GitHub snapshots incl. `stars/`; existing ones are reused, `meta.json` keeps the first date (#14) | `--record` | — |
| fastembed model (`~/.cache/repo-scout/fastembed` or `FASTEMBED_CACHE_PATH`) | first run | — |
| LLM reply cache | only `eval --llm-draft` with a snapshot dir | — |

## Side flows

### LLM draft (before search)

Module: repo_scout/llm.py::draft, repo_scout/llm.py::parse_draft

Need (cut to 2000 chars) → Task description (≤600 chars), up to 10 queries, up to 10 regexes (nested
quantifiers rejected) through an OpenAI-compatible API. JSON is taken from a fenced block or the first
decodable object; one retry on a reply that fails validation; HTTP errors or a reply without `choices`
raise at once. Without a key: off. In the GUI the button shows only with the key and
`REPO_SCOUT_GUI_DRAFT=1` (eval gate failed, see `eval/LLM-REPORT.md`).

### GUI

Module: repo_scout/gui/app.py::main, repo_scout/gui/search_page.py::search, repo_scout/gui/runs_logic.py::sorted_rows

The Search page builds the same argv (`cli.to_argv`) and runs `python -m repo_scout … --out PATH` (or the
frozen binary) as a subprocess with a live log. The form has no `--json`, `--all`; they are
dropped from a pasted command. It opens the Index on load for project autocomplete and lists `~/dev`.
Runs pages read the saved run JSON. The Index page talks to `Index` directly (rename, forget).
The Eval page runs `repo-scout eval … --out <runs>/../eval-reports/*.md`; its Record toggle uses the network.
The server listens on 127.0.0.1 and `restrict_hosts` answers 400 to any other Host name (DNS rebinding).

### Eval

Module: repo_scout/evaluate.py::eval_set, repo_scout/evaluate.py::metrics

Each `eval/*.toml` set runs the main flow on recorded snapshots with a fresh temporary Index and
`min_closeness=0`; the threshold is applied afterwards so `--sweep` can vary it. Positives are verdicts
starting with `→` or `->` (e.g. `→ Разбор`); recall counts positives present in the rows, kept or dropped.
Other modes: `--record`, `--fake-stars`, `--llm-draft`, `--index-check` (two runs on one temp Index),
`--export-verdicts` (opens the real Index).

## Where the flow splits by mode

| Part | Basic (default) | `--replay` | `--record` | Advanced (keys set) |
|---|---|---|---|---|
| GitHub | live via `gh` | snapshots only, missing → error | snapshot if present, else live + write | live |
| Index read/write | yes | no | no | yes |
| Run saved | yes | no | no | yes |
| Star burst | top 10 | snapshots; missing → warning | snapshot or live + write | top 10 |
| Fit | off | off | off | top 20 |
| LLM draft | off | (eval only) cached replies | (eval only) live + cache | on |

## How it fails

| Failure | Result |
|---|---|
| Bad regex | exit 2 with the reason, no request sent |
| Query over GitHub limits | exit 2; earlier queries were already sent (#11) |
| `gh` not installed | Python traceback (#10) |
| `gh` not logged in, plain 403 | `GitHub: …`, exit 1 |
| 429 / 502 / rate limit / empty reply on search | retries after 5, 10, 20 s, then exit 1 |
| Same on details / refresh batches | split down to single repos, skipped with a warning; no exit (#9) |
| One repo keeps failing | step 6: kept with `no details`; step 3: left out of the run, kept in the Index |
| Star history, fit, run save errors | warning; the table is still printed |

## Known gaps

Open HIGH and MEDIUM findings; details in `PLAN.md` → "Logic map findings".
- A rate limit during details keeps every row unscreened as `no details` (#9).
- No `gh` on PATH → traceback (#10).
- Hand-edited run JSON with wrong-typed fields (`score: null`, `flags: null`) breaks the GUI run page.
- Shared eval details are not tied to each set's snapshot date (`PLAN.md`, Phase 9.1).
