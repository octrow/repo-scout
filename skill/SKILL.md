**English** | **[Русский](SKILL.ru.md)**

---
name: repo-scout
description: Search for existing GitHub solutions before building your own: recent low-star projects count too. Use whenever the user wants to implement something and needs to check if there is an existing or close repository to build upon; on "find on github", "is there something ready-made", "search for analogs", "repo-scout".
---

# repo-scout

Methodology: `docs/repo-triage.md` (stop rules, flags, scores, Steps 1–3, output format). Read it before starting.
The `repo-scout` CLI command performs Step 1 mechanically: search, stop rules, flags, and aggregate scores (freshness + popularity).

## Workflow

1. **Task description** in English (1–3 sentences stating what is needed) goes into `--task`: it is used to compute Closeness. If `<project>/docs/repo-triage.md` exists with project axes and thresholds, use them.
2. **Queries.** (Write queries yourself; do not use `repo-scout draft` or the LLM Draft in the GUI: those are for humans without an agent.) 3–6 query variants: synonyms, English terms, `language:`, `topic:`, `in:readme`. Avoid `stars:` filters: low stars are not a reason to exclude a repo.
   ```bash
   repo-scout --task "Find open-source live speech transcription with an overlay, runs on Linux" "whisper live transcription" "speech to text overlay language:python" "topic:asr linux"
   ```
   Hard conditions: `--lang python`, `--must REGEX` (required words, repeatable), `--exclude REGEX` (excluded words). Below the Closeness threshold (`--min-closeness`, 0.64), rows are filtered out as "off topic"; if results are too narrow or broad, reformulate the task description rather than the threshold. Progress is logged to stderr and `~/.local/state/repo-scout/run.log` (overwritten; the user can run `tail -f`), `-q` sends only warnings to stderr. Additional flags: `--months 6`, `--new-days 60`, `--all` (include filtered out), `--json`. Pass `--project <name>`: searches are saved as Runs (path shown in log), and the user can open them in the GUI (`repo-scout gui`, "Runs" page) to record Verdicts with clicks.
3. **Round two and the Index trigger automatically.** From the top-10 `topics`, up to 5 `topic:<slug>` queries are built (`--round2-k`, `--no-round2`; used topics are logged to stderr), and closest entries from the local Index are added (`--from-index N`, 50).
   The `spike★ N% early` flag (share of the first ~1000★ in burst days; REST stars history for top-10 with ≥50★; `--stars-k`, `--no-stars-check`) is a measurement: purchased stars and viral launches look identical; check the star history chart during Inspection, do not treat as an automatic discard.
4. **Project axes.** For candidates passing stop rules, add scores along project axes (platform, stack, features). Only read READMEs if required to decide: `gh api repos/OWNER/REPO/readme -H 'Accept: application/vnd.github.raw' | head -c 15000`, preferably grep for keywords.
5. **Inspection** of top 3–7 per methodology: without cloning, within token budget. Clarify Deep dive objective with the user.
6. **Result.** Summary lines following methodology format (`triage: step 1 · close 0.81 · scores … · flags: … · verdict: …`). Steps 2–3 details go into `<project>/docs/analogs/<repo>.md`.
7. **Verdicts.** After Inspection or Deep dive, save verdict to the Index (`~/.local/share/repo-scout/index.db`, `$REPO_SCOUT_INDEX`):
   ```bash
   repo-scout verdict owner/repo "→ Deep dive (how the window is hidden from screen share)" --project linux-coding --task "interview assistant"
   ```
   Formats: `→ Inspect`, `→ Deep dive (<goal>)`, `discard (<reason>)`, `unclear (<what to clarify>)`. A verdict never hides a repo, it is simply displayed in subsequent searches.
