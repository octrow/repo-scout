**English** | [Русский](CONTEXT.ru.md)

# repo-scout — Glossary

Triage guide: [`docs/repo-triage.md`](docs/repo-triage.md).

- **Candidate** — a GitHub repository found by search that has not yet passed Triage.
- **Triage** (Step 1) — mechanical screening of a candidate using metadata: stop rules, flags, scores. No code inspection.
- **Stop rule** — a condition that immediately drops a candidate with no scoring (dead, toy, no code, off-topic).
- **Flag** — an informative tag that does not drop a candidate (fork, stars ≫ commits, archived, new, template, cosmetic only, star burst).
- **New** — created within the last 60 days. A flag, not a score.
- **Inspect** (Step 2) — reviewing GitHub web pages without cloning; yields a verdict and a goal for Study.
- **Study** (Step 3) — cloning into `external_examples/` and inspecting code with a specific goal.
- **Without LLM** — Search, Triage, Closeness, and ranking operate without generative or external models: deterministic rules, GitHub API, and local embedding models (CPU, offline). Holds in both modes: external models may add to the output, never drop or reorder it.
- **Basic mode** — the default: no external models and no API keys. Everything except LLM draft and Fit works.
- **Advanced mode** — Basic mode plus external models the user turns on with their own keys: an OpenAI-compatible model for LLM draft (before search) and a System One model for Fit (after Triage). Each part is optional on its own; without a key it is off.
- **Fit** — a System One model's probability (0–1) that a candidate can serve as the base for the task. Advanced mode only, for the top kept candidates of a run. Not a score and not a stop rule: a column next to Closeness that never drops or reorders rows.
- **Task description** — 1–3 English sentences describing what the user needs. Used to compute semantic Closeness.
- **Need** — what the user wants to find, in their own words in any language, without naming specific solutions. Used to generate the task description and queries (by human, agent, or LLM draft).
- **LLM draft** — task description, queries, and hard conditions suggested by an LLM based on the user's need. Merely fills out the form; the user reviews and launches the search.
- **Query** — a search string using GitHub search syntax (keywords, `language:`, `topic:`). Several queries are derived from one task description.
- **Pool** — deduplicated candidates from a single run: live results across all queries plus nearest matches from the Index.
- **Run** — a single search execution: task description, queries, hard conditions, timestamp, and final candidate table (including dropped candidates). Saved in full and acts as a draft for future searches.
- **Index** — local cumulative storage of candidates that passed stop rules and have fetched READMEs (metadata + embedding vector). Populated only from actual searches; no mass scraping. Metrics of indexed repos are updated before Triage.
- **Round two** — additional queries built automatically from top candidates' `topics`. Exactly one round, with a limit on query count.
- **Closeness** — semantic similarity between a candidate and the task description. Not a score: serves as a threshold (below is dropped as off-topic) and as primary sort key. Guide scores (freshness, popularity) serve as secondary keys.
- **Hard condition** — a requirement from the task description checked deterministically: language, required word regexes (in README and topics), excluded words. Violations trigger stop rules; if README is missing, required words flag rather than drop.
- **Golden set** — task description, queries, and hard conditions from a past search, plus repos with known verdicts. Stored with frozen GitHub response snapshots and timestamps for reproducible evaluation.
- **Substantive commit** — a commit on default branch not authored by service bots (dependabot, renovate, github-actions, etc.) and not cosmetic by message/size (docs/deps/ci/bump/typo, tiny text edits). AI-agent commits (Claude, Copilot, Codex, Devin…) are regular commits judged by substance. Freshness and dead checks use the last substantive commit date.
- **Cosmetic only** — a flag indicating none of the last 20 commits are substantive.
- **Verdict** — outcome of Inspect or Study for a specific project task: `→ Inspect`, `→ Study (goal)`, `drop (reason)`, `doubt (clarify)`. Bound to task rather than repo: one repo can have different verdicts in different tasks. Stored in Index and shown in future searches without hiding the repo.
- **Noise** — candidates that are not reusable solution bases: awesome lists, tutorials, demos, homework, spam/promotions. Dropped only upon ≥2 independent signals (name, description, topics). Templates are flagged, not treated as noise.
