# How repo-scout differs from GitHub search and similar tools

| Tool | What it does well | Where repo-scout differs |
|---|---|---|
| GitHub search | One query, sorted by best match or stars | Runs several queries and merges them, drops dead, toy and off-topic repos, and ranks by closeness to your task rather than by stars |
| Asking a chat model | Fast suggestions in plain language | Every candidate comes from a live GitHub search, so new repos are included and every name exists |
| [DeepGit](https://github.com/zamalali/DeepGit) | An LLM writes the search plan and ranks the shortlist | Ranking needs no LLM and no API key; stop rules and flags are deterministic, so the same candidates always get the same marks |
| [repohunt](https://github.com/danielrltan/repohunt) | MCP server that searches and ranks hits for a coding agent | Adds a local embedding model for closeness, stop rules, a star-burst check and a local Index with your verdicts |
| [github-hidden-gems](https://github.com/JoanAbad82/github-hidden-gems) | Scores how good a little-known repo is (0–100) | Scores how close a repo is to *your* task, then lets you record a verdict per project |

The notes on these tools are in [`analogs/`](analogs/README.md); some of their ideas are borrowed here.
