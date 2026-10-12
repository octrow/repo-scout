**English** | **[Русский](BASELINE.ru.md)**

# Baseline eval (Phase 2)

Snapshot recording date: 2026-10-11. Pipeline: Phase 1 (`in:name,description,topics,readme`, `mirror:false`, `pushed:>=6 months`, limit 50 per query, stop rules and triage scores). Hard conditions (`must`/`exclude`) not yet applied. Task descriptions in `eval/*.toml` await user verification, so figures are preliminary.

Command: `repo-scout eval eval/*.toml --record` (offline replay: `--replay`, outputs identical results).

Ranks are calculated among candidates passing stop rules, ordered by triage methodology score (Closeness not yet introduced). Positive = Verdict "→ …".

| Set | Positives | Found | Passed | Ranks | False discards | Missed | Passed Discard |
|---|---|---|---|---|---|---|---|
| buy-smarter | 9 | 3 | 1 | 74 | 2 | 6 | 1 |
| buy-smarter-vision | 5 | 2 | 1 | 95 | 1 | 3 | 0 |
| finance-insights | 5 | 4 | 4 | 11, 63, 13, 31 | 0 | 1 | 0 |
| get_cool_event | 3 | 2 | 2 | 13, 103 | 0 | 1 | 0 |
| linux-coding | 8 | 3 | 3 | 17, 105, 96 | 0 | 5 | 3 |
| persona-crm | 6 | 2 | 2 | 46, 67 | 0 | 4 | 0 |
| repo-scout | 4 | 1 | 1 | 230 | 0 | 3 | 0 |
| tiktok-lazy-follower | 5 | 4 | 4 | 90, 21, 152, 41 | 0 | 1 | 0 |

Observations:
- Recall is low: out of 45 positives, 21 entered the pool, 18 passed stop rules, 24 missed. All "missed" repos are alive (verified via `gh api` for monica, screenpipe, open_clip, transformers, repohunt, github-hidden-gems, git-crawler: commits within past 3 months), indicating misses stem from query formulations and the 50 results-per-query cap in best-match order rather than filters.
- Positions of target repos range from 11 to 230: without Closeness and Noise filtering, target repos sink down (repo-scout: DeepGit at #230, others unretrieved). This is the primary target metric for Phases 3–4.
- False discards: 3 (all flagged by "dead" rule: ozon-mcp-server 126d, ai-super-agent 167d, FashionMV 165d), all in sets with 2026 clones.
- Repos passing despite "discard" verdict: 4 (olx-parser, Aura-AI, xexamai, interview-copilot): stop rules do not flag them, requiring Noise and Hard conditions.
- Initial candidate pool is broad (hundreds per set), and sorting by freshness + stars buries small fresh projects such as repohunt (1★) and github-hidden-gems (0★).

## Phase 3

Date: 2026-10-11. Pipeline: Phase 2 + Noise (≥2 signals across name/description/topics), "template" flag, `lang`/`exclude`/`must` from sets (case-insensitive regex), batch README and 20 recent commits for survivors, freshness and "dead" based on last Substantive Commit (commits past snapshot date ignored).

Command: `repo-scout eval eval/*.toml --record` (subsequently `--replay`, both runs match recordings identically). Snapshot date (`meta.json`) unchanged at 2026-10-11. Snapshots stored as `*.json.gz`, with repo details separated under `details/<repo_name_hash>.json.gz`, allowing incremental `--record` without invalidating existing files. README truncated to 6000 chars, commits store `messageHeadline`; complete `eval/snapshots` size is 4.6 MB.

| Set | Positives | Found | Passed | Ranks | False discards | Missed | Passed Discard |
|---|---|---|---|---|---|---|---|
| buy-smarter | 9 | 3 | 1 | 60 | 2 | 6 | 1 |
| buy-smarter-vision | 5 | 2 | 1 | 58 | 1 | 3 | 0 |
| finance-insights | 5 | 4 | 4 | 9, 44, 11, 21 | 0 | 1 | 0 |
| get_cool_event | 3 | 2 | 2 | 8, 71 | 0 | 1 | 0 |
| linux-coding | 8 | 3 | 3 | 5, 59, 75 | 0 | 5 | 3 |
| persona-crm | 6 | 2 | 2 | 31, 39 | 0 | 4 | 0 |
| repo-scout | 4 | 1 | 1 | 191 | 0 | 3 | 0 |
| tiktok-lazy-follower | 5 | 4 | 4 | 35, 5, 72, 13 | 0 | 1 | 0 |

Diff against Phase 2 baseline:
- No regressions: positives in pool 21, passed 18, false discards 3 (same "dead": ozon-mcp-server, ai-super-agent, FashionMV), missed 24, passed discards 4. Recall is identical since Phase 3 filters noise rather than expanding search.
- Ranks of surviving positives improved due to noise elimination: linux-coding 17/105/96 → 5/59/75, buy-smarter 74 → 60, buy-smarter-vision 95 → 58, tiktok 90/21/152/41 → 35/5/72/13, repo-scout DeepGit 230 → 191.
- Noise filtering stats: awesome 267, tutorial 4, demo 3, homework & spam 0. Flags: "template" on 34 rows, "only cosmetics" on 47, "no README" on 10. `--must` filtered 52 rows (buy-smarter & tiktok) with zero positive losses.
- Refined heuristics: common words removed from noise regexes (`generator`, `free`, `hack`, `learning`, `course`, `list`, `resources`, `collection of`), retaining qualified combinations (`online course`, `free followers`, `curated list`). Cosmetic commits `bump|release <v>|typo|readme` now bound by word boundaries and diff size ≤100 lines; prefixes `docs:|chore(deps):|ci:|style:` and `Merge` remain unconditional.
- 4 discards still pass (olx-parser, Aura-AI, xexamai, interview-copilot) awaiting semantic Closeness in Phase 4.

## Phase 4

Date: 2026-10-11. Pipeline: Phase 3 + Closeness (fastembed `BAAI/bge-small-en-v1.5`, README cleaned across full text, input capped at 20,000 characters, candidate doc `name + description + topics + cleaned README` truncated to 2000 chars ≈ 512 tokens). Sort order: Closeness, then methodology score, then push recency. Task description taken from set `task` field. Completely offline via snapshots (`repo-scout eval eval/*.toml --sweep`, 2 min on CPU).

| Set | Positives | Found | Passed | Ranks | False discards | Missed | Passed Discard | Min. Closeness (Positives) |
|---|---|---|---|---|---|---|---|---|
| buy-smarter | 9 | 3 | 1 | 31 | 2 | 6 | 1 | 0.69 |
| buy-smarter-vision | 5 | 2 | 1 | 51 | 1 | 3 | 0 | 0.68 |
| finance-insights | 5 | 4 | 4 | 10, 7, 6, 58 | 0 | 1 | 0 | 0.71 |
| get_cool_event | 3 | 2 | 2 | 13, 3 | 0 | 1 | 0 | 0.71 |
| linux-coding | 8 | 3 | 3 | 21, 17, 41 | 0 | 5 | 3 | 0.68 |
| persona-crm | 6 | 2 | 2 | 16, 2 | 0 | 4 | 0 | 0.66 |
| repo-scout | 4 | 1 | 1 | 2 | 0 | 3 | 0 | 0.80 |
| tiktok-lazy-follower | 5 | 4 | 4 | 48, 5, 8, 18 | 0 | 1 | 0 | 0.69 |

Ranks compared to Phase 3:
- linux-coding 5/59/75 → 21/17/41;
- repo-scout 191 → 2;
- finance 9/44/11/21 → 10/7/6/58;
- tiktok 35/5/72/13 → 48/5/8/18;
- persona 31/39 → 16/2; get_cool_event 8/71 → 13/3;
- buy-smarter 60 → 31; buy-smarter-vision 58 → 51.
Recall unchanged: 18/18 surviving positives retained (zero lost to threshold), false discards 3, missed 24. Ranks improved for 11 of 18 positives (median rank: 14.5).

### Query Prefix

`query_embed` in fastembed does not prepend the bge-small-en model card prefix, so `embed_task` adds `"Represent this sentence for searching relevant passages: "` manually. Eval comparison (identical README cleaning): without prefix, sum of ranks is 338, median 16, 632 rows remain at 0.64; with prefix, sum of ranks is 357, median 14.5, 575 rows remain. Max threshold without loss is 0.66 in both cases. Chosen variant: with prefix for cleaner output and improved median rank.

### Threshold Sweep

Sweep from 0.50 to 0.90 (step 0.01) across all sets. Out of 18 passing positives:

| Threshold | Lost "→ Deep dive" | Rows Remaining |
|---|---|---|
| 0.50–0.66 | 0 | 1150 … 461 |
| 0.67 | 1 | 399 |
| 0.70 | 5 | 232 |
| 0.75 | 10 | 51 |
| 0.80 | 18 | 2 |

Maximum threshold without losing positives is 0.66. Configured standard threshold: **0.64** (maximum minus 0.02 safety margin). Threshold 0.64 eliminates 587 out of 1162 rows (51%) as "off topic" without losing a single positive target.

### Phrasing Robustness

Task descriptions rephrased two ways (`repo-scout eval ... --task "..." --top 10`), measuring top-10 overlap with original `task`:

| Set | Rephrasing 1 | Rephrasing 2 |
|---|---|---|
| linux-coding | 6 of 10 | 5 of 10 |
| repo-scout | 10 of 10 | 10 of 10 |

## Phase 5

Date: 2026-10-11. Index (sqlite3 + BLOB vectors + numpy linear scan), Verdicts, `--from-index`, `source` and `previously seen` columns. Snapshots of Index updates recorded in `eval/snapshots/<set>/refresh/`.

Verification test (`repo-scout eval eval/linux-coding.toml eval/repo-scout.toml --index-check`): run 1 populates Index; run 2 executes against identical Index with rephrased `alt_task` and only the first 2 queries, evaluating `--from-index`:

| Set | In Index after run 1 | Run 2: Live search | From Index (passed stop rules) | Positives in live | Positives from Index |
|---|---|---|---|---|---|
| linux-coding | 137 | 85 | 10 (10) | 1 of 8 (natively) | 0 |
| repo-scout | 229 | 99 | 17 (17) | 1 of 4 (DeepGit) | 0 |

Injection size testing (`--index-check --from-index N`):

| N | linux-coding: from Index, positives | repo-scout: from Index, positives | GraphQL batch updates (10 repos/batch) |
|---|---|---|---|
| 20 | 10, 0 | 17, 0 | 1 + 2 |
| 30 | 14, 1 (Specter-AI) | 26, 0 | 2 + 3 |
| 50 | 23, 2 (Specter-AI, pluely) | 42, 0 | 3 + 5 |

N=50 recovers positives for linux-coding, establishing **`--from-index 50` as default**.

## Phase 6

Date: 2026-10-11. Round two: from top-10, topics appearing in ≥2 rows are extracted (filtering generic topics), spawning up to 5 `topic:<slug>` queries in an expansion round.

Found / passed / ranks of passing positives (threshold 0.64), without round two → with round two:

| Set | Positives | Found | Passed | Ranks |
|---|---|---|---|---|
| buy-smarter | 9 | 3 → 4 | 1 → 2 | 31 → 44, 27 |
| buy-smarter-vision | 5 | 2 → 3 | 1 → 2 | 51 → 76, 88 |
| finance-insights | 5 | 4 → 5 | 4 → 5 | 10, 7, 6, 58 → 11, 25, 8, 6, 76 |
| get_cool_event | 3 | 2 → 2 | 2 → 2 | 13, 3 → 19, 4 |
| linux-coding | 8 | 3 → 4 | 3 → 4 | 21, 17, 41 → 29, 6, 25, 61 |
| persona-crm | 6 | 2 → 3 | 2 → 3 | 16, 2 → 35, 6, 3 |
| repo-scout | 4 | 1 → 1 | 1 → 1 | 2 → 4 |
| tiktok-lazy-follower | 5 | 4 → 4 | 4 → 4 | 48, 5, 8, 18 → 65, 5, 9, 21 |
| **Total** | 45 | **21 → 26** | **18 → 23** | |

Round two successfully surfaced 5 new positives: a-ulianov/OzonAPI (buy-smarter), mlfoundations/open_clip (vision), beancount/beancount (finance), PavelLizunov/suflyor (linux-coding), monicahq/monica (persona-crm). Zero positive losses; false discards remained steady at 3.

API request volume per set (searches + details, details batched by 10):

| Set | Search | Details | Round 2 Topics |
|---|---|---|---|
| buy-smarter | 6 → 11 | 8 → 28 | ozon, ecommerce, marketplace, mcp, ai-agents |
| buy-smarter-vision | 6 → 10 | 16 → 34 | clip, computer-vision, multimodal, streamlit |
| finance-insights | 6 → 11 | 20 → 36 | beancount, personal-finance, plaintext-accounting, accounting, budgeting |
| get_cool_event | 6 → 10 | 16 → 30 | instagram, instagram-downloader, instagram-api, telegram |
| linux-coding | 6 → 11 | 15 → 34 | ai-assistant, cluely-alternative, electron, meeting-assistant, react |
| persona-crm | 6 → 8 | 16 → 26 | self-hosted, crm |
| repo-scout | 6 → 11 | 25 → 37 | github-api, github-search, github, github-growth, github-ranking |
| tiktok-lazy-follower | 6 → 10 | 18 → 34 | tiktok, api, tiktok-api, youtube |
| **Total** | 48 → 82 | 134 → 259 | |

## Phase 7

Date: 2026-10-11. Flag `spike★ N% early`: share of first min(1000, total)★ occurring during MAD spike days (REST `stargazers/history`). Dataset `eval/fake-stars`: 100 StarScout positives (active, ≥50★) and 100 controls (27 "→ Deep dive" golden set repos, 73 from `sample_repo_ids`). Recorded 200 histories, 1707 REST calls (~8.5 per repo).

Tune split: threshold 0.7 / min 5 stars/day selected (recall ≥ 0.5, minimum FPR).

**Test split (threshold 0.7, min 5): TP 22, FP 7, precision 0.76, recall 0.44, FPR 0.14.** Expectation on top-10 standard candidates: ~1.4 false flags per run, with at least one in ~78% of runs if all 10 are organic.

False flags on test: viral launches (dinov3, transformers, actual, monica, nametag, meetily, ThreeOverlay).

**Gate review** (Test FPR ≤ 0.15): passed with 0.01 margin on 50 controls. Flag enabled by default (`--stars-k 10`, `--no-stars-check` to disable) as an informative measurement rather than an absolute accusation. Cost: up to 85 REST calls per run.

Fork analysis: spikes without fork surges did not differentiate manipulated from viral repos (in fact, manipulated repos averaged higher fork ratios during spikes), so fork metrics are excluded from the flag.

## Phase 9 — LLM Draft (2026-10-12, gate failed)

`repo-scout eval eval/*.toml --llm-draft --out eval/LLM-REPORT.md` (replay), model `free-stack` via OmniRoute, snapshots in `eval/snapshots-llm/` (details shared in `_shared/details`). Variants: agent — the set's Queries; Draft — `draft(need)` from the Need alone (no answer names), with its own task, Queries and conditions; union — both Query lists with the set's task and conditions.

| set | positives | agent: found/kept | Draft: found/kept | union | tokens | Draft time, s |
|---|---|---|---|---|---|---|
| buy-smarter | 9 | 4/2 | 4/2 | 4/2 | 1125 | 13.6 |
| buy-smarter-vision | 5 | 3/2 | 1/0 | 2/1 | 1229 | 10.1 |
| finance-insights | 5 | 5/5 | 3/3 | 5/5 | 873 | 9.2 |
| get_cool_event | 3 | 2/2 | 2/2 | 2/2 | 910 | 5.4 |
| linux-coding | 8 | 6/6 | 6/5 | 5/5 | 967 | 8.9 |
| persona-crm | 6 | 3/3 | 3/3 | 4/4 | 1028 | 8.8 |
| repo-scout | 4 | 1/1 | 1/1 | 1/1 | 1081 | 7.7 |
| tiktok-lazy-follower | 5 | 4/4 | 4/4 | 4/4 | 998 | 7.7 |
| **total** | **45** | **28/25** | **24/20** | **27/24** | **8211** | **71** |

**Gate:** Draft found 24 < agent 28 → the GUI "Draft with LLM" button is hidden by default (shown with the key plus `REPO_SCOUT_GUI_DRAFT=1`); `repo-scout draft` stays. The union (27) does not beat the agent: +1 in persona-crm (`sneg55/pingcrm`), −1 in buy-smarter-vision (`mlfoundations/open_clip`) and linux-coding (`PavelLizunov/suflyor`) — a different Second round built from a different top's topics. No "my Queries + Draft" mode.

**What the Draft loses (manual review):**
- buy-smarter-vision: `facebookresearch/dinov3`, `mlfoundations/open_clip` — general embedding libraries; Draft Queries stay fashion-specific.
- finance-insights: `beancount/beancount`, `beancount/fava` — the plain-text accounting ecosystem, never named by the model.
- linux-coding: `Zackriya-Solutions/meetily` found but dropped by the Draft's Hard condition `must: interview` — the model sets overly strict conditions.
- persona-crm: `subzeroid/instagrapi` — a building block (social API), not a CRM; the Draft found another positive instead, net equal.

Conclusion: from a Need alone the model covers direct phrasings but misses adjacent ecosystems and building blocks, and sometimes drops positives with its own conditions. Useful as a hint for a human, not as a replacement for agent Queries.

**Cost:** LLM — ~1k tokens and ~9 s per Draft (free-stack is free; answers are non-deterministic, so snapshots are required). Eval recording after the speed-up (shared details cache, 3 batches in parallel, 1 retry) — 5–7 min and 58–85 GraphQL points per set instead of ~13 min; replay of all 8 sets — ~5 min, 1.5 GB (embeddings in batches of 32 plus an in-process vector cache; previously 10+ GB). One repo skipped on HTTP 502 (`tkarim45/Beginner-Data-Science-Projects`, not a positive).

Limitation: shared details are not tied to each set's snapshot date — when re-recording a set later, re-record its details too.
