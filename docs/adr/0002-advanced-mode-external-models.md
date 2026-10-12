**English** | **[Русский](0002-advanced-mode-external-models.ru.md)**

# 0002. Advanced mode: external models are opt-in extras that never reorder results

Date: 2026-10-12 · Status: accepted

## Context
repo-scout ranks without generative models (CONTEXT.md, "Without LLM"). Users still want two things only external models give: queries written from a need in any language (LLM draft), and a judgment of whether a result can actually serve as a base for the task. A System One model (Jev by TypeSafe) answers typed yes/no questions with calibrated probabilities, which fits the second need better than a chat model.

## Decision
Two modes. **Basic** (default) needs no keys. **Advanced** turns on parts by key: `LLM_API_KEY` for LLM draft (any OpenAI-compatible endpoint; OmniRoute and Ollama are the free suggestions), `TYPESAFE_API_KEY` for **Fit**. Fit is one request per run, one `noul` question per top kept candidate (20), shown as a column. It never drops or reorders rows, and replay/eval runs never call it, so recall measurements stay deterministic. Keys live in `~/.config/repo-scout/.env`, filled by `repo-scout config`; `OMNIROUTE_*` stay readable as aliases.

## Rejected Alternatives
- **Sort by Fit (or Fit × Closeness) in advanced mode.** Unmeasured: it could push down repos the golden sets mark `→ Study`. Revisit only after eval shows Fit improves recall at the top.
- **Fit through the OpenAI-compatible LLM.** Free-text answers need parsing and are not calibrated; one more prompt to maintain.
- **One mode switch (`REPO_SCOUT_MODE=advanced`).** Redundant: a key already says the user wants that part, and the two parts are independent.

## When to Revisit
- Eval on the golden sets shows Fit-based ordering finds more `→ Study` repos in the top 10 → make Fit a sort key in advanced mode.
- Fit cost or latency matters (larger k, many runs) → batch per page in the GUI or cache Fit per (task, repo) in the Index.
