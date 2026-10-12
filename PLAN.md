**English** | **[Русский](PLAN.ru.md)**

# repo-scout v1 — Implementation Plan

Goal: before writing custom code, quickly find ready-made or close open-source solutions on GitHub that can serve as a foundation, including fresh low-star repositories. The core pipeline runs without generative LLMs; generative tasks (Task description, Queries, Inspection) remain with the AI agent via the skill.

Foundations:
- Concepts: `CONTEXT.md`. Methodology: `docs/repo-triage.md` (after Phase 1).
- Decisions: `docs/adr/`. Analog reviews: `docs/analogs/README.md` (DeepGit, repohunt, hidden-gems, github-discovery, git-crawler). Search syntax and limits: `docs/search-advices.md`.
- Analog clones: `external_examples/` (in `.gitignore`).

## Pipeline v1

```
skill: task → Task description (EN) + 3–6 Queries + Hard conditions
  → search (GraphQL) ─┐
  → Index (Closeness) ┴→ Pool → stop rules → Noise → --lang/--exclude
  → README batch + 20 commits → substantive commits → freshness/"dead" → --must
  → Closeness (threshold, primary key) + methodology score (secondary key)
  → round two by topics (single round) → table / --json + save to Index
```

## Phase 1 — Packaging and Migration

- [x] `pyproject.toml` (uv, Python ≥3.11), package `repo_scout/`: `github.py` (GraphQL, rate limit), `triage.py` (stop rules, flags, scoring), `cli.py`; entry point `repo-scout`.
- [x] Migrate `scout.py` to modules without behavioral changes; `test_scout.py` → `tests/test_triage.py` (pytest).
- [x] `uv tool install --editable .`; skill invokes `repo-scout` instead of `scout.py`.
- [x] Relocate `~/dev/docs/repo-triage.md` → `docs/repo-triage.md`, symlink at the original path.
- [x] Search optimizations from `docs/search-advices.md`: `in:name,description,topics,readme`, `mirror:false`, `--lang` → `language:` in Query; validate limits (256 chars, ≤5 AND/OR/NOT) before execution with clean error messages.
- [x] Track `rateLimit{cost remaining resetAt}` in every GraphQL request; retries for 403/429/"200 without JSON" with exponential backoff (DeepGit `graphql.py:177-209`), distinguish rate limits from other 403 errors; fixed backoff 5/10/20 s (ponytail: resetAt handling via `gh api -i` when hitting hourly cap) (repohunt `github.ts:150-160`).

Done: `repo-scout "q1" "q2"` produces the same output table as legacy `scout.py`, additionally discovering repos matching solely in README; all tests pass.

## Phase 2 — Golden Sets and Eval

- [x] Format `eval/<set>.toml`: Task description, Queries, Hard conditions, expected repos with Verdicts, date.
- [x] Eval sets (agent extracts Task description from repo README/CLAUDE.md, verified by user):
  linux-coding (`docs/research/opensource-analogs.md` + `analogs/`), buy-smarter, persona-crm, tiktok-lazy-follower, get_cool_event, finance-insights (clone without review = "→ Deep dive"), repo-scout (`docs/analogs/README.md`).
- [x] GitHub response recording: `--record` writes GraphQL responses to `eval/snapshots/<set>/`, `--replay` reads offline without network.
- [x] `repo-scout eval eval/<set>.toml`: recall on "→ Inspect/Deep dive" (count in output, ranks), false discards (reasons: stop rule / Noise / condition / threshold), how many "discard" verdicts survived. Consolidated multi-set summary table.
- [x] Lock baseline metrics for the pipeline in `eval/BASELINE.md`.

Note: Task descriptions in `eval/*.toml` await user verification.

Done: Offline evaluation across all sets functional, baseline recorded. Subsequent phases benchmark against baseline; loss of "→ Deep dive" constitutes a regression.

## Phase 3 — Noise, Hard Conditions, Substantive Commits

- [x] Noise detection: awesome / tutorial / demo / homework / spam based on repo name, description, and topics; discard only on ≥2 independent signals with reason in output. Source inspiration: `external_examples/github-hidden-gems/src/hidden_gems/filtering/rules.py:200-576`. Boilerplates flag "template" rather than Noise.
- [x] Hard conditions: `--lang` (primaryLanguage), `--exclude` (regex → discard), `--must` (regex groups against README+topics; missing README → flag, not discard). Repos filtered out by `--must` listed on separate output row.
- [x] Batch GraphQL fetching for surviving candidates (aliases `r1: repository(...)`, 20–50 per batch): README (aliases README.md/readme.md/README.rst…), `history(first:20){committedDate message additions deletions author{user{login}}}`.
- [x] Substantive commit analysis: filter out automation bots (dependabot, renovate, github-actions, pre-commit-ci, allcontributors, imgbot, semantic-release-bot) and trivial cosmetic edits (commit messages matching `docs:|chore(deps)|ci:|style:|bump|release|typo|readme|merge` or tiny text diffs). AI-agent commits treated as normal development. Inspired by `github-hidden-gems/.../light_analysis/activity.py:26-177`.
- [x] Freshness and "dead" metrics calculated from the latest substantive commit; if none exist among the 20 commits → oldest commit date used + "only cosmetics" flag.

Done: Unit tests for Noise rules, conditions, and commit heuristics; eval verification shows noise (e.g. awesome lists) eliminated while retaining all "→ Deep dive" targets.

## Phase 4 — Closeness (Semantic Relevance)

- [x] `semantic.py`: fastembed `BAAI/bge-small-en-v1.5`, query embedding via `query_embed()`; candidate document `name + description + topics + README`, with sanitized README (stripped badges, images, layout HTML; adapted from `external_examples/repohunt/src/readme.ts:1-83`) truncated to ~512 tokens.
- [x] `--task "<Task description>"` is required; Closeness is primary sort key, methodology score is secondary; candidates below threshold trigger "off topic" stop rule.
- [x] Calibrate threshold on eval: highest threshold where zero "→ Deep dive" targets are lost. Document value and rationale in `eval/BASELINE.md`.
- [x] Update `docs/repo-triage.md`: Closeness (threshold + sorting), Hard conditions, Noise, substantive commits, updated summary format.

Done: Eval confirms recall matches or exceeds baseline with improved top rankings for "→ Deep dive"; alternative phrasings of the same task yield consistent top results.

## Phase 5 — Local Index and Verdicts

- [x] stdlib `sqlite3` (`~/.local/share/repo-scout/index.db`): metadata, README, `fetched_at`, BLOB float32 vector, embedding model name. Exact cosine scan via numpy (ADR-0001; `ponytail:` threshold comment for transitioning to sqlite-vec).
- [x] Writing: every candidate passing stop rules with an acquired README is upserted by `owner/name`.
- [x] Reading: top-N by Closeness from Index is injected into the candidate Pool; metrics refreshed via batch GraphQL prior to filtering.
- [x] Model updates trigger vector recomputation from stored READMEs without external network requests.
- [x] Verdicts: `repo-scout verdict owner/repo "<verdict>" --project <name> --task "<summary>"`; output displays "previously seen" column (project, date, verdict). Does not hide candidates. Skill records verdicts following Inspection/Deep dive.
- [x] `repo-scout eval --export-verdicts` exports Index verdicts as candidates for Golden sets.

Done: Subsequent searches with related queries pull in previously discovered repos absent from live GraphQL results; Verdicts display across sessions.

## Phase 6 — Round Two (Topic Exploration)

- [x] Collect frequent `topics` from the top-K (default 10) post-closeness, excluding previously used queries; formulate up to 5 `topic:<slug>` queries (+ `language:` when `--lang` specified), executed in a single expansion round.
- [x] New candidates pass through identical pipeline; output includes "source" column (query / round two / index).
- [x] Update skill documentation: workflow order, `--task`, conditions, verdicts.

Done: Eval demonstrates recall improvement or parity with bounded increase in API requests (metrics recorded in `eval/BASELINE.md`, "Phase 6"). Positive count: 21 → 26, passed: 18 → 23; API calls: 48 / 134 → 82 / 259 across 8 sets.

## Phase 7 — Star Spikes Flag

Context (2026-10-11): As of July 2026, GitHub restricts stargazer lists to repo owners and collaborators (GraphQL `stargazers` empty, REST returns 404). Account-level signals (StarScout low-activity, DevTrust createdAt clustering) are unavailable for third-party repos. Only aggregated star history `GET /repos/{o}/{r}/stargazers/history` (REST API version 2026-03-10) is accessible: weekly breakdown by day, descending chronologically, 30 weeks per page. Star manipulation is flagged via **Flag** without modifying scores: repos below 1000★ receive ≤1 point from stars anyway, while large repos have negligible bought proportions.

- [x] `repo_scout/stars.py`: star history retrieval (REST via `gh api`, retries and caching identical to GraphQL, keyed by repo name). Executed only for top-K candidates post-closeness (`--stars-k`, default 10) with ≥50★ (StarScout MIN_STARS). Pages scanned until creation week or earliest ~1000★ (where purchases typically cluster), bounded by `MAX_PAGES`.
- [x] MAD spike detection (real-stars constants `src/shared/constants.ts:13-19`, `mad.ts:72-179`, MIT; StarGuard Apache-2.0 equivalent): 28-day sliding window, flagged if `count > median + 3·1.4826·MAD` and count meets star threshold; repos under 30★ remain unclassified.
- [x] Distinguish virality from manipulation (real-stars heuristic): inspect forks during spike windows (GraphQL `forks(orderBy:CREATED_AT)` with `createdAt`); star surges lacking fork activity warrant suspicion.
- [x] `spike★ N% early` flag (renamed from "fake stars?"): measures share of initial ~1000★ occurring in spike periods; causes (purchase vs viral surge) are indistinguishable from telemetry alone.
- [x] Eval suite: `eval/fake-stars/` derived from StarScout datasets (Apache-2.0, attributed): positive set from `data/250101/fake_stars_{low_activity,clustered}_repos.csv` with `p_stars_*` ≥0.5 and `n_stars` ≥50; control set from `sample_repo_ids.csv` plus golden set "→ Deep dive" organic repos. Precision and recall benchmarked; false positives analyzed.
- [x] Gate verification: if precision < ~0.7, flag remains disabled by default (`--stars-check` flag retained). Documented in `eval/BASELINE.md`.
- [x] Update documentation: `docs/repo-triage.md`, `CONTEXT.md`, and skill.

Done: Precision and recall evaluated against StarScout benchmarks; flag surfaced in output table; API request overhead recorded.

## Phase 8 — GUI (Full CLI Parity)

Decisions (2026-10-11): GUI replicates all CLI capabilities: Search, Runs, Index, Eval. Search and eval execute as background processes via `run_pool` with live streaming logs and cancellation; Index interacts directly via `Index`. Humans compose Task descriptions and Queries directly. Drafts are populated from historical Runs and eval sets, while agent prompts yield ready-to-run CLI commands. Every CLI execution persists a Run JSON file. `nicegui-kit` is vendored directly into the repository to guarantee standalone builds independent of local system environments. Visual styling follows `DESIGN.md` and kit patterns.

### 8.1 CLI: Runs and GUI Input (TDD)
- [x] `repo_scout/runs.py`: `save(params, rows, round2_topics, now) -> Path`, `list_runs() -> list[Summary]`, `load(path)`, `delete(path)`. Directory `$REPO_SCOUT_RUNS` or `~/.local/share/repo-scout/runs/`, filename pattern `<YYYYmmdd-HHMMSS>-<task-slug>.json`. Payload `{"version": 1, "created_at", "params", "round2_topics", "rows"}`; includes **all** candidates, enabling GUI toggles for filtered rows without re-running searches.
- [x] `cli`: Runs persisted by default, except under `--replay`/`--record` or `--no-save`. `--out PATH` specifies target output. CLI logs target path. New parameter `--project` recorded in `params`. Round two slugs returned and logged.
- [x] `cli.parse_command(text) -> Namespace`: `shlex.split` wrapper around `_parser()`, tolerating leading `repo-scout` or `$` prefixes. Argparse errors converted to `ValueError` with descriptive message without exiting. Enables "Paste command" action.
- [x] `cli.to_argv(params) -> list[str]`: inverse of `parse_command`, powering command preview and `run_pool.submit`. Verified: roundtrip `parse_command(shlex.join(to_argv(p))) == p`.
- [x] `evaluate --out PATH`: outputs report to file, preventing `run_pool` stdout/stderr interleaving.
- [x] `repo_scout/__main__.py`: GUI invokes subcommands via `[sys.executable, "-m", "repo_scout", …]`, preserving environment and virtualenv integrity.

### 8.2 Vendoring nicegui-kit and Skeleton
- [x] Copied from `~/dev/pylibs/nicegui-kit/src/nicegui_kit/` into `repo_scout/gui/kit/`: `theme`, `layout`, `table`, `run_pool`, `run_monitor`, and `assets/fonts` (Inter OFL font with `LICENSE.txt`). Imports localized to relative paths. AA contrast tests adapted into `tests/test_theme_layout.py`.
- [x] `repo_scout/gui/kit/VENDORED.md`: records vendored commit (`adf21c1`), timestamp, and list of modifications (prefixed with `# repo-scout:`). Added Inter font to `THIRD_PARTY_NOTICES.md`.
- [x] Dependencies: added `nicegui>=3.15,<4`. Dev dependencies: `pytest-asyncio`, `conftest.py` configured with `pytest_plugins = ["nicegui.testing.user_plugin"]` and `asyncio_mode = "auto"`.
- [x] `repo_scout/gui/app.py`: header navigation "Search · Runs · Index · Eval" and `theme_toggle`. `apply_theme()` called once. Graceful shutdown handler cleans up background processes. Command `repo-scout gui [--port 8790]` dispatches seamlessly.

### 8.3 "Search" View (`/`)
- [x] Form inputs:
  - "Draft": select menu from historical Runs and `eval/*.toml` sets;
  - "Task (EN)";
  - "Queries": multi-line input, validated via `validate_query`;
  - "Project": autocomplete hints from existing verdicts;
  - "Language", "Required words", "Excluded words": validated via `compile_all`;
  - Expandable "Advanced" drawer: `months`, `new_days`, `limit`, `min_closeness`, `from_index`, `round2`, `stars_k`.
- [x] Dynamic command string `$ repo-scout …` reflecting form state with copy button. Action buttons: "Run" (primary), "Prompt for agent" (copies structured prompt), "Paste command" (modal importing CLI string into form).
- [x] Execution via `run_pool.submit(argv + ["--out", path])` and `attach_run_monitor()`. Completion notifications provide direct links to `/runs/{id}`.

### 8.4 "Runs" Views (`/runs`, `/runs/{id}`)
- [x] Listing page (`empty_aware_table`): date, task, project, candidate counts (passed / total). Deletion guarded by confirmation modal.
- [x] Detail view: parameter header with "Reuse as draft" button. Filter bar: text search, source chips, flags, show/hide filtered candidates. Candidate table matching CLI markdown columns, sorted by default relevance.
- [x] Detail drawer: GitHub link, metrics, flags, rejection reasons, historical verdicts (`Index.seen`), and embedded README viewer (`markdown_reader`).
- [x] Verdict modal: verdict selection (`→ Inspect` / `→ Deep dive (…)` / `discard (…)` / `unclear (…)`) with notes. Validated and persisted via `Index.add_verdict`.

### 8.5 "Index" View (`/index`)
- [x] Table listing indexed repositories with filtering by project, verdict, and query. Actions for editing verdicts, renaming `owner/repo`, and deleting entries with confirmation.

### 8.6 "Eval" View (`/eval`)
- [x] Evaluation cards for `eval/*.toml` sets with dataset stats. Controls for replay/record flags, sweep parameters, and dataset selection. Runs execute via `run_pool` with rendered markdown reports.

### 8.7 Tests, Documentation, and Review
- [x] End-to-end NiceGUI user tests for all pages using mock runs and isolated test databases.
- [x] Documentation updated across README, skill, and CONTEXT.md.
- [x] Code review completed for UI consistency, accessibility, and error handling.

Done: Complete browser-based GUI operational alongside CLI and agent skills.

## Phase 9 — LLM Query Drafting (Optional)

Decisions (2026-10-12): Eval data reveals that query construction accounts for the largest share of misses (19 out of 45 positives missed due to queries). LLMs are integrated strictly at the drafting stage: converting a raw Need into structured drafts (Task description, Queries, Hard conditions). The model is not called during execution, nor does it re-rank results. Without an API key, the feature remains inactive and the system functions as before.

- [x] `repo_scout/llm.py` implemented via standard library `urllib` without external SDKs.
  - Environment variables (or `.env` in the repo root): `OMNIROUTE_API_KEY`, `OMNIROUTE_BASE_URL` (default `http://127.0.0.1:20128/v1`), `OMNIROUTE_MODEL` (`free-stack`).
  - `draft(need) -> Draft(task, queries, lang, must, exclude)` returning structured queries conforming to methodology rules.
  - Defensive validation: JSON extraction, schema checks, regex compilation, and fallback retry on malformed output. API keys sanitized from logs.
  - Snapshot caching: `--record`/`--replay` caches LLM responses by sha(model+prompt).
- [x] CLI: `repo-scout draft "<need>"` outputs an executable `repo-scout …` command line.
- [x] GUI: "Search" view provides "What are you looking for" input and "Draft with LLM" button — after the gate only with the key and `REPO_SCOUT_GUI_DRAFT=1`.
- [x] Eval (gate failed: Draft found 24 vs Agent 28 — see 9.1):
  - Add `need` descriptions to each `eval/*.toml` benchmark set.
  - Benchmark `repo-scout eval --llm-draft`: compare recall between Agent queries, LLM draft queries, and their union. Cache snapshots in `eval/snapshots-llm/<set>/`.
  - Gate check: if LLM draft recall is lower than Agent queries, retain drafting as opt-in CLI/UI utility only. Document cost and latency metrics in `eval/BASELINE.md`.
- [x] Documentation: README and CONTEXT updated with configuration parameters.

### 9.1 Eval Finalization and Gate Decisions

- [x] Shared details cache across sets and variants to minimize redundant network requests.
- [x] Disable star history scans during `--llm-draft` runs (`stars_k=0`) to isolate recall benchmarks.
- [x] Bounded retries (1 instead of 3) for a single failing repo during `--llm-draft` recordings; skip markers in the shared cache are rechecked once per run.
- [x] Progress logging (set i/N, variant, details k/M); detail batches fetched 3 at a time; GraphQL points spent logged per run; per-run log files (`logs/`, 1 GiB cap).
- [x] Record remaining benchmark datasets sequentially (5–7 min and 58–85 GraphQL points per set).
- [x] Evaluate overall gates across all 8 sets and record findings in `eval/LLM-REPORT.md` and `eval/BASELINE.md`: Draft 24 / Agent 28 / union 27 of 45 positives → GUI button opt-in (`REPO_SCOUT_GUI_DRAFT=1`), `repo-scout draft` stays; no "my queries + Draft" mode (union does not beat Agent).

Status (2026-10-12): Phase 9 done; gate failed, Draft is an opt-in helper. Known limit: shared details are not tied to each set's snapshot date (all sets recorded 2026-10-11/12).

## Backlog (Deferred until supported by eval data)

1. Channel: 1-hop neighbor expansion — repos by the same author and GitHub links in READMEs.
2. Channel: Curated awesome lists — `topic:awesome-*` links.
3. Channel: Sourcegraph repo discovery without tokens.
4. Channel: Package registry discovery (PyPI / npm / crates).
5. Granular commit file path analysis (code vs docs) for edge cases.
6. Codebase health metrics (tests, CI, bus factor, issues) as tertiary ranking signals.
7. Index transition to sqlite-vec / LanceDB per ADR-0001 criteria.
