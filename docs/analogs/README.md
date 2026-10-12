**English** | [Русский](README.ru.md)

# repo-scout Analogs — Research Analysis 2026-10-11

Study Goal: identify candidate channels, signals, and ranking heuristics that operate without LLMs to adopt in scout.
Cloned repositories: `external_examples/` (in `.gitignore`). Paths below are relative to that folder.
None of the analogs used embeddings/BM25/vectors — semantic Closeness was designed specifically for repo-scout.

## Summary
- repohunt — triage: → Study (multi-query ranking) · TS, ~600 lines, without LLM · borrowed: ranking, README cleaning, `in:name,description,readme`
- github-hidden-gems — triage: → Study (noise filter) · Python, ~12k lines · borrowed: two-signal noise filter, activity excluding bot commits, file tree heuristics
- github-discovery — triage: drop (dead, 107d / 59 commits), but valuable constants · Python, ~29k lines, heavy stack · borrowed formulas, not code modules
- git-crawler — triage: → Study (scoring) · C#/Angular · borrowed: rateLimit within same GraphQL query, contributors via Link rel=last, star bell curve
- SimRepo — drop (no code for similar_repos, GPL-3.0) · nothing to borrow

## Borrowed Concepts (Ranked by Value)
1. Noise filtering (tutorial/template/demo/spam/awesome): reject only on ≥2 independent signals — `github-hidden-gems/src/hidden_gems/filtering/rules.py:200-576`. S
2. Multi-query ranking: count of matching queries → best-match position → pushed_at; stars as tie-breaker — `repohunt/src/rank.ts`. S
3. `in:name,description,readme`, without `sort` (best-match position provides free relevance signal) — `repohunt/src/github.ts:220-244`. S
4. `rateLimit{cost remaining resetAt}` inside the same GraphQL query — `git-crawler/Features/Crawling/DiscoverRepositories/GitHubDiscoveryClient.cs:100-162`. S
5. README cleaning: strip badges/images/layout HTML, preserve code blocks, truncate at ~2000 characters on paragraph boundary — `repohunt/src/readme.ts:1-83`. S
6. Freshness excluding bot/typo/bump commits — `github-hidden-gems/src/hidden_gems/light_analysis/activity.py:26-177`. S–M
7. Repository health from file tree (tests, CI, src/, manifest, README length) — `github-hidden-gems/src/hidden_gems/light_analysis/classification.py:139-204`. M
8. Maintenance: bus factor across authors of last 30 commits, cadence, closed/open issues — `github-discovery/src/github_discovery/screening/maintenance.py:25-190`. M
9. Discovery channels: `topic:awesome-{word}` + README links (`github-discovery/.../curated_channel.py:37,408-520`); one-hop owner & README links (`github-hidden-gems/.../relationships/explorer.py:26-175`). M
10. Rate limits: 403 treated as rate limit only when remaining==0 or Retry-After present; bounded concurrency with partial results — `repohunt/src/github.ts:150-160,273-296`. S

## DeepGit (zamalali/DeepGit) — Research Analysis 2026-10-11
triage: step 1 · score 2 (fresh 1, pop 1) · flags: — · verdict: → Study (vector layer) · Python, MIT

Architecture: LLM-1 (intent → queries/topics/must-haves) → GraphQL search → upsert into LanceDB → +15 vector matches from index → prescore without LLM → top-8 → LLM-2 (ranking).
- Vector layer `src/deepgit/retrieval/semantic.py:57-250` (269 lines): fastembed `BAAI/bge-small-en-v1.5` (384, ONNX CPU), document format `name\ndesc\ntopics[:12]\nREADME[:1400]` (without badge stripping), query via `query_embed()`. LanceDB `merge_insert` by name_with_owner. Downsides: cosine distance discarded, no threshold, no fetched_at/TTL — index metrics never refresh.
- GraphQL search with README (7 aliases for `object(expression:"HEAD:README.md")`) and root file tree in one query — `src/deepgit/github/graphql.py:20-81,94-155`. Expensive per page → first 15–25 results.
- Retries: 403/429 → min(2^n·5, 60)s; "200 without JSON" = secondary rate limit — `graphql.py:177-209`. No semaphore or remaining quota check.
- prescore `signals.py:86-99`: 0.4·relevance(intent term share) + 0.2·maintenance(1−log1p(days)/log1p(1095)) + 0.1·health(tests .40, .github .25, license .20, manifest .15) + 0.3·popularity(log1p★/log1p 10k). No stop rules.
- Queries: `topic:<slug> sort:stars-desc` (`pipeline.py:77-91`), deterministic fallback from intent terms and adjacent word pairs + `language:` (`pipeline.py:61-74,234-244`).
- Replacing LLM-1 without LLM: agent in skill + round two topics; language dictionary. Replacing LLM-2: semantic Closeness as primary key + threshold + deterministic stop rules.
