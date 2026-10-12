**English** | **[Русский](continue-phase-9.1.ru.md)**

# Prompts for continuation: Phase 9.1 (LLM Draft eval and gate checks)

## 1. For `/compact`

```
/compact Continuing repo-scout (~/dev/repo-scout, master = origin, HEAD 1038fc0): implement PLAN.md "9.1 Complete eval and determine gate decisions". Preserve: Phase 8 (GUI on nicegui-kit vendored copy in repo_scout/gui/kit, Runs in runs/, port selection) and Phase 9 (repo_scout/llm.py — Draft via OmniRoute, OMNIROUTE_API_KEY/OMNIROUTE_MODEL=free-stack key in .env (in .gitignore, never print API keys); repo_scout/eval_llm.py — agent/Draft/union variants; need field in eval/*.toml) committed and pushed, 275 tests passing. Eval --llm-draft recorded only for buy-smarter (9 positives: agent 4/2, Draft 4/2, union 4/2; ~1.1k tokens and ~14s per Draft), buy-smarter-vision partially; recording takes ~13 min/set due to detail refetching (~200 repos per variant) and retries on HTTP 502. 502 skips are recorded in snapshots (github._record_skipped). Next steps in 9.1: shared details cache eval/snapshots-llm/_shared/details, stars_k=0 in --llm-draft, 1 retry for failed repo in eval, progress indicator "set i/N" in log; sequentially record 7 remaining sets in background; evaluate gates across 8 sets (Draft "found" >= agent -> keep button; otherwise hide by default), document in eval/BASELINE.md "Phase 9". Do not commit .agents/, .claude/, skills-lock.json. Jev/TypeSafe re-ranking deferred until after 9.1.
```

## 2. Full prompt (new session)

```
Project: ~/dev/repo-scout (Python >=3.11, uv; private GitHub octrow/repo-scout, master branch). The tool searches GitHub for open-source foundation projects using the methodology in docs/repo-triage.md: search -> stop rules/flags/scores -> Closeness (local fastembed BAAI/bge-small-en-v1.5 embeddings) -> Index (sqlite) and Verdicts. Glossary — CONTEXT.md (Run, Need, LLM Draft, Non-LLM, Golden set ...), plan — PLAN.md.

Status (2026-10-12, HEAD 1038fc0, 275 tests passing, `uv run pytest -q`):
- Phase 8 — GUI: `repo-scout` without arguments (or `repo-scout gui [--port 8790]`) — NiceGUI on vendored nicegui-kit (repo_scout/gui/kit, VENDORED.md). Views: Search / Runs / Index / Eval; search and eval run in background subprocesses via run_pool. Each search persisted as a Run (~/.local/share/repo-scout/runs/*.json; --out, --no-save, --project).
- Phase 9 — LLM Draft (optional): repo_scout/llm.py, `repo-scout draft "<need>"`, "Draft with LLM" button in GUI. OmniRoute http://127.0.0.1:20128/v1, env variables OMNIROUTE_API_KEY, OMNIROUTE_MODEL (free-stack), OMNIROUTE_BASE_URL (loaded from environment or repo .env; .env in .gitignore — never log or print keys). Untrusted model output validation: validate_query, compile_all, ReDoS checks, language validation, single retry. LLM snapshots stored in <snapshot dir>/llm/.
- Eval for Draft: `repo-scout eval eval/*.toml --llm-draft [--record] [--out FILE]`, snapshots in eval/snapshots-llm/<set>/. Each eval/*.toml includes a need field (Russian user need without names from expected; validated in tests/test_eval_need.py). Variants: agent (set queries), Draft (draft(need)), union (both query sets).
- Interim results (eval/BASELINE.md, "Phase 9"): recorded buy-smarter — 9 positives, agent 4/2, Draft 4/2, union 4/2 (found/kept); ~1.1k tokens and ~14s per Draft. Recording takes ~13 min/set due to detail queries and HTTP 502 retries.

Task: Implement PLAN.md "### 9.1 Complete eval and determine gate decisions":
1. Accelerate recording: shared details cache eval/snapshots-llm/_shared/details/<sha16(lower name)> across all sets and variants; stars_k=0 in --llm-draft; 1 retry instead of 3 for single failed repo in eval; progress logging "set i/N, variant, details k/M" in log. Ensure existing buy-smarter snapshots remain valid.
2. Record remaining 7 sets sequentially via background `repo-scout eval eval/<set>.toml --llm-draft --record`.
3. Evaluate gates across all 8 sets (replay, --out eval/LLM-REPORT.md): Draft "found" >= agent -> keep button visible; otherwise hide by default. Record findings in eval/BASELINE.md "Phase 9"; update PLAN.md.

Constraints:
- Do not commit .agents/, .claude/, skills-lock.json.
- Type annotations, clean functions <50 lines, files <400 lines.
```
