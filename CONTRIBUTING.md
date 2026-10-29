**English** | [Русский](CONTRIBUTING.ru.md)

# Contributing

Bug reports, ideas and pull requests are welcome. By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). For a large change, open an issue first so we can agree on the approach.

## Set up

You need Python 3.11+, [uv](https://docs.astral.sh/uv/) and the [GitHub CLI](https://cli.github.com/) logged in with `gh auth login`.

```bash
git clone https://github.com/octrow/repo-scout && cd repo-scout
uv sync
uv run repo-scout doctor --fix   # checks gh and downloads the embedding model
uv run repo-scout                # opens the GUI
```

## Before a pull request

```bash
uv run ruff check .
uv run pytest -q
```

- Add a test for new behavior. Tests never call GitHub or external models: they use snapshots and monkeypatch.
- Keep README.md and README.ru.md in sync when you change behavior or options.
- Changed a search step (what it drops, flags, skips or how it fails)? Update [docs/logic-map.md](docs/logic-map.md) in the same commit.
- Use the words from [CONTEXT.md](CONTEXT.md) (Candidate, Triage, Closeness, Fit...). A larger design decision gets an ADR in [docs/adr/](docs/adr/).
- Ranking stays deterministic. External models may add information, never drop or reorder rows ([ADR 0002](docs/adr/0002-advanced-mode-external-models.md)).
- Commit messages: `<type>: <description>`, where type is feat, fix, refactor, docs, test, chore, perf or ci.

## Releases

Bump `version` in pyproject.toml, merge to main, then push a tag `vX.Y.Z`. The release workflow runs the tests, builds the packages for Linux, macOS and Windows and publishes the release.
