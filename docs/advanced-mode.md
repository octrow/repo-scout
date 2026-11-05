# Advanced mode

Basic mode is the default and needs no API keys. Search, triage, closeness and ranking run on GitHub data and a local CPU model.

Advanced mode adds two optional extras. Each one turns on with its own key. They add information and never drop or reorder results ([ADR 0002](adr/0002-advanced-mode-external-models.md)).

| Extra | What it does | Key | Free option |
|---|---|---|---|
| LLM draft | turns a need written in any language into a task description, queries and hard conditions; you review and run the search yourself | `LLM_API_KEY` | [OmniRoute](https://github.com/diegosouzapw/OmniRoute) (local gateway, the default URL) or [Ollama](https://ollama.com/) (`LLM_BASE_URL=http://localhost:11434/v1`, any key) |
| Fit | Jev, a TypeSafe System One model, rates from 0 to 1 how well each of the top 20 results can serve as the base for your task; shown as a `fit` column next to closeness | `TYPESAFE_API_KEY` | key at [console.typesafe.ai](https://console.typesafe.ai/keys) |

```bash
repo-scout config                                  # asks for the keys, saves ~/.config/repo-scout/.env
repo-scout doctor                                  # shows the mode and what is on
repo-scout draft "<what you need, any language>"   # LLM draft: prints a ready `repo-scout …` command
repo-scout --no-fit ...                            # one search without the fit column
```

| Variable | Default |
|---|---|
| `LLM_API_KEY` | none (LLM draft is off) |
| `LLM_BASE_URL` | `http://127.0.0.1:20128/v1` (any OpenAI-compatible `/chat/completions`) |
| `LLM_MODEL` | `free-stack` |
| `REPO_SCOUT_GUI_DRAFT` | `0`; `1` shows the Draft button in the GUI |
| `TYPESAFE_API_KEY` | none (fit is off) |
| `TYPESAFE_MODEL` | `jev-latest` |

The settings file is `~/.config/repo-scout/.env` (`$REPO_SCOUT_ENV`, readable only by you). Real environment variables take precedence over it. In a clone, a git-ignored `.env` in the repo root works too and overrides the user file. The older `OMNIROUTE_API_KEY`, `OMNIROUTE_MODEL` and `OMNIROUTE_BASE_URL` still work. Replayed runs and evals never call Fit.
