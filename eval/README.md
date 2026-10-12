**English** | **[Русский](README.ru.md)**

# Golden Sets (eval)

Format of `eval/<set>.toml`: `name`, `source` (provenance of Verdicts), `analysis_date`, `task` (Task description in English), `queries` (3-6 Queries), `lang`/`must`/`exclude` (Hard conditions), followed by `[[expected]]` blocks containing `repo`, `verdict`, and `note`.

Verdicts: `→ Inspect`, `→ Deep dive (goal)`, `discard (reason)`, `unclear (what to clarify)`. Task descriptions and Queries were reconstructed by the agent as drafts.

| Set | Expected | of which "→ Deep dive" | Source | User Verification Needed |
|---|---|---|---|---|
| linux-coding | 20 | 8 | docs/research/opensource-analogs.md | task; queries are synthetic (originals not recorded) |
| buy-smarter | 10 | 9 | PLAN.md "Sources", INIT_DATA.md | task; 5 clones without detailed review; olx-parser as discard |
| buy-smarter-vision | 11 | 5 | docs/llm-vision/...research.md | separate set (not clones); "Keep/Core" mapped to Deep dive, "Future/Optional" to unclear |
| persona-crm | 6 | 6 | INIT_DATA.md, CLAUDE.md | monica/nametag/friends/whatsapp-crm: clones without deep dive |
| tiktok-lazy-follower | 5 | 5 | INIT_DATA.md | all clones without deep dive; project final outcome relies on yt-dlp |
| get_cool_event | 5 | 3 | CLAUDE.md, docs/PRODJECT.md | gallery-dl and insta-dl: "unclear" per Alternatives section |
| finance-insights | 5 | 5 | clones | all clones without deep dive |
| repo-scout | 6 | 4 | docs/analogs/README.md | task |

The `must` condition fields are currently only specified in `buy-smarter` and `tiktok-lazy-follower` (rough filtering by platform name); verify.
