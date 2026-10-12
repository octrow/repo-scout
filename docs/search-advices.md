**English** | [Русский](search-advices.ru.md)

# GitHub Search Insights

## Sources and References
- https://sourcegraph.com/search
- https://medium.com/@mohamedaziz.mhadhbi/github-search-tips-how-to-search-issues-repos-and-more-effectively-on-github-240ddd896f2e
- https://github.com/github/docs/blob/main/content/search-github/getting-started-with-searching-on-github/about-searching-on-github.md
- https://www.freecodecamp.org/news/how-to-use-github-search-like-a-pro/
- https://docs.github.com/en/get-started/exploring-projects-on-github/discovering-projects-on-github
- https://github.com/search?type=code
- https://docs.github.com/en/search-github/getting-started-with-searching-on-github/about-searching-on-github
- https://github.com/Dimillian/HyperGit
- https://tzx.notion.site/What-I-Learned-Building-a-Free-Semantic-Search-Tool-for-GitHub-and-Why-I-Failed-1a09b742c7918033b318f3a5d7dc9751
- https://github.com/manticoresoftware/manticore-github-issue-search

## Takeaways (2026-10-11)

- **SemHub** (article by tzx, https://semhub.dev/) — semantic search over **issues**, not repos. OpenAI embeddings 1536→256 (Matryoshka), pgvector on Supabase ($200/mo), Cloudflare Workers. Failure was due to distribution/demand, not tech. Key lessons: exact linear scan instead of ANN on small corpora, truncate text to model limits, stay embedded inside existing workflows (CLI + agent skill).
- **Search syntax** (docs.github.com): without `in:`, README is not indexed → `in:name,description,topics,readme`. Limits: 1000 results per query, ~4000 viewable hits, 256 text characters (excluding qualifiers), ≤5 AND/OR/NOT, `NOT` only for text terms (`-qualifier:` for qualifiers). `pushed:` checks pushes to any branch. Useful flags: `mirror:false`, `template:`, `archived:`, `license:`, `topics:>n`, `fork:true|only` (forks are excluded by default!), `sort:stars-desc` inside GraphQL query strings. Search API rate limit: 30 req/min.
- **Sourcegraph**: `/.api/search/stream` without token, `type:repo <words>` returns repos with stars and topics; code search with `select:repo` on sourcegraph.com yielded 0 — unreliable as an external search channel. Backlog candidate.
- **HyperGit** — searches user's own repos; **manticore-github-issue-search** — searches issues. Not suited for broad repository scouting.
- **keyhacks / keyhunter / gist win3zz** — leaked API keys verification, out of scope for repo-scout.
