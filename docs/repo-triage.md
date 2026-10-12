**English** | [Русский](repo-triage.ru.md)

# Triage Guide for External Git Repositories

How to quickly decide whether an external repo (analog, competitor, code donor) is worth your time without in-depth code reading.
Goal: a verdict on where to invest attention and what to borrow. License is not considered: this is internal research.

**These are guidelines, not rigid rules.** When in doubt, clarify with the user.

Project-specific scoring axes (platform, stack, features) live in the project directory: `<project>/docs/repo-triage.md`.

## Steps

| Step | What to Check | Output |
|---|---|---|
| **1. Triage** | Closeness to Task description, Hard conditions, Noise, description + stars / forks / commits / last update. README — if decision requires it. | Closeness + score → pass to Step 2 if ≥ threshold |
| **2. Inspect** | GitHub web pages without cloning: README, sidebar languages, Releases, Contributors/Insights, last 10–20 commits, open issues and replies. | Verdict + **Study goal** |
| **3. Study** | Clone into `<project>/external_examples/` (in `.gitignore`). | What to borrow / suitability as a base |

## Step 1 — Triage

### Closeness

Semantic similarity of candidate (name, description, topics, README) to Task description (English, 1–3 sentences; `--task`). Not a score: threshold and **primary sort key**; score is secondary, days since push is tertiary. Default threshold is 0.64 (`--min-closeness`): below is dropped as `off-topic (0.xx)`. Calibrated on eval benchmarks as the maximum threshold retaining all `→ Study` positives, minus a 0.02 safety margin.

### Stop Rules (any triggers immediate drop, skipping scores)

- **Off-topic:** Closeness below threshold.
- **Hard conditions** (`--lang`, `--must`, `--exclude`): wrong language, forbidden word in name/description/topics/README, missing required word regexes (missing README flags instead of dropping).
- **Noise:** awesome list, tutorial, demo, homework, spam/promo — only upon ≥2 independent signals (name, description, topics). Template is flagged, not dropped.
- **Dead:** no updates > 4 months with < 500 commits; no updates > 6 months with any commit count.
  Freshness and dead checks rely on the last **substantive** commit (not a service bot, not cosmetic docs/deps/ci/bump/typo; AI-agent commits are judged by content).
  Rationale: modern projects evolve rapidly with AI assistance, making older unmaintained code significantly less viable.
- **Toy:** < ~50 commits and 0 stars (unless individual commits are massive).
- **Closed / locked:** dropped if no copyable source code exists. If historical code is accessible, evaluate normally.

What does **not** drop:
- Low star counts (few stars is no reason to discard).
- Narrow product positioning ("note taker", "meeting summary"): evaluate internal mechanisms — audio capture, ASR, etc.
- Fork: valuable if specialized (e.g. customized for Linux). If not differentiated, evaluate upstream.
- High commit volume: normal variation.

### Flags (informative, do not drop)

- **stars≫commits** — imbalance (thousands of stars for dozens of commits): hype/purchased stars without engineering substance.
- **burst★ N% early** — measurement: share of the first ~1000★ arriving during spike days (via star history: 28-day window, day above median + 3·1.4826·MAD, ≥5★/day). Computed for top-K candidates after closeness with ≥50★. **Meaning:** stars arrived in bursts. Could be star-farming **or** organic viral launch (Hacker News, Trending, post); cannot be distinguished from history alone. Treat as an indicator to inspect the star chart during Inspect, not a verdict. Eval performance (test): recall ≈0.44, false positive rate (FPR) on organic repos ≈0.14 (~1.4 false flags per top 10 organic repos).
- **fork** — notes upstream repository.
- **cosmetic only** — none of the last 20 commits are substantive.
- **template**, **no README**, **new**.

### Common Scoring Axes

| Axis | Points |
|---|---|
| **Freshness** (last update) | ≤ 7 days **+4**; ≤ 14 days **+3**; ≤ 1 month **+2**; ≤ 3 months **+1** |
| **Popularity** (stars) | ≥ 100 **+1**; ≥ 1k **+2**; ≥ 10k **+3**; ≥ 50k **+4**; ≥ 100k **+5** |

Plus project-specific axes. **Unknown = 0.**

## Step 2 — Inspect

**Token budget:** skip images/screenshots; read first ~15 KB of README (≈300 lines), then only table of contents and target sections.
For README screening, grep for keywords (platforms, stack, features) rather than full reading.

**Platform support beyond README:** If README omits your target platform, search issues/PRs (`gh search issues --repo X linux`): look for open PRs, maintainer discussions, or build logs.

**Stop:**
- None of our pipeline components can be borrowed.
- Last commits are purely cosmetic (README edits, version bumps) with no real progress.
- No releases or clear setup instructions, and evident runtime failure.

**Positives (reasons to proceed to Study):**
- Specific module of interest is present.
- Issues/PRs addressing our platform or exact challenges with solutions.
- Multiple active contributors responsive to issues.

**Output:** verdict + Study goal ("how the window hides from screen share"). Confirm goal with user before starting Study.

## Step 3 — Study

`git clone --depth 1 <url> <project>/external_examples/<repo>` — inspect code under the specific goal from Step 2.
Output: what to copy/adapt, or suitability as architectural foundation.

## Result Format

Detailed findings from Steps 2–3 (metrics, facts, file paths, comparison, pitfalls) should be preserved in `<project>/docs/analogs/<repo>.md`.
Summary row in analog list:

```
triage: step 1 · close 0.81 · score 10 (platform 3, stack 1, features 2, fresh 4, pop 0) · flags: new · verdict: → Inspect
```

Verdicts: `→ Inspect`, `→ Study (<goal>)`, `drop (<reason>)`, `doubt (<what to clarify>)`.
