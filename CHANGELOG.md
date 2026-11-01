**English** | **[Русский](CHANGELOG.ru.md)**

# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.12] - 2026-11-01

### Fixed
- `--lang "Jupyter Notebook"` and other multi-word languages are quoted in the query.
- Negative `--months`, `--new-days`, `--limit`, `--from-index`, `--round2-k` and `--stars-k` are rejected; before, `--stars-k -1` checked every row but the last. The GUI number fields stop at 0.

## [0.1.11] - 2026-11-01

### Fixed
- Round two picks topics from rows above `--min-closeness`, also a lowered one; before, the floor never went under 0.64. Eval keeps 0.64.
- `--record` into a folder that already holds snapshots uses the folder's recording date, so `--replay` of it gives the same freshness.
- All queries are checked against GitHub's limits before the first request, so a bad last query no longer spends quota on the ones before it.
- GUI: runs saved in Russian show their round two rows under `round two` (not a separate `round 2`), and the Index verdict filter also finds verdicts saved in Russian.
- A GitHub rate limit while fetching READMEs and commits stops the run with `GitHub: …` (exit 1) after the usual retries. Before, every repo was skipped one by one and kept unscreened as `no details`, and the run was saved.
- Without `gh` on PATH, repo-scout says where to get the GitHub CLI instead of printing a Python traceback.

## [0.1.10] - 2026-11-01

### Fixed
- `--exclude` and `--must` match the repo name without the owner login: `--exclude bot` no longer drops `botpress/agent-kit`.
- `--must` checks repos without a README against name, description and topics, as its help says; before, they skipped the check and stayed. `README.markdown`, `README.txt` and `README.org` count as a README.
- Repos pulled from the Index follow `--months` and `--lang` like search results: older ones are dropped as `pushed before <date>`, and with `--lang` a repo with no language is dropped as `no language`.
- Repos dropped as dead, toy, no code or noise leave the Index (their verdicts stay), so they no longer take `--from-index` slots in every run. `--from-index N` now adds N repos that are not already in the search results.
- `--lang cpp`, `--lang golang` and other common GitHub aliases no longer drop every result: GitHub reports `C++` and `Go`, and the language check now maps the alias first.
- `--months` above 6 and `--months 0` work: the `dead` rule allows the same age (30 × months), and `0` turns it off. Before, nothing older than 6 months survived whatever `--months` said.
- `--must` and `--exclude` see the whole README: it was cut to 6000 chars, so a required word further down dropped the repo. The cap is now 100 000 chars.
- The GUI keeps `--no-fit`: a pasted command or a re-run of a saved run no longer loses it, and the Search form has a "Skip the fit column" checkbox.

## [0.1.9] - 2026-11-01

### Security
- The GUI answers only `127.0.0.1` and `localhost` Host names, so a web page that rebinds its DNS name to 127.0.0.1 can no longer drive it.
- The Fit column's request to TypeSafe no longer follows redirects, so the API key cannot be resent to another host.

### Changed
- CI and pre-commit also check ruff formatting, a complexity limit (10) and types with ty; long functions are split into small helpers, with tests pinning the behaviour first.

## [0.1.8] - 2026-10-30

### Added
- `docs/logic-map.md`: how a search run flows through the code, step by step, kept in sync by a test.
- Russian code of conduct (official Contributor Covenant 2.1 translation).

### Fixed
- Search no longer crashes when GitHub returns an empty (null) commit in a repo's history.
- `eval --fake-stars` closes the labels file it reads.
- Search no longer crashes when GitHub fails to refresh a repo pulled from the Index; the repo stays in the Index.
- A repo GitHub fails to return because of an error (not because it is gone) is no longer deleted from the Index.
- A GitHub reply with empty data is retried instead of crashing the search.
- A never-pushed repo (`pushedAt` null) no longer crashes triage; its age counts from creation.
- `eval --fake-stars` survives a deleted repo or an empty fork entry, and a label file with only one class.
- GUI: opening a draft whose run file was deleted shows a notice and an empty form instead of an error.
- LLM draft reads a JSON reply followed by prose with braces, and reports a non-text reply as an error instead of crashing.
- Saving settings no longer leaves an older duplicate key in `.env` that overrode the new value; the file is created readable by the owner only.
- `eval` names the missing keys of a broken set file instead of failing with a traceback.

### Security
- Dependencies with known vulnerabilities updated: certifi 2026.10.19, filelock 4.2.1, fastembed 0.9.1, pillow 13.0.0.

## [0.1.7] - 2026-10-14

### Added
- Demo GIF of a real search and a comparison with similar tools in the README.
- GUI tables fit the window; columns hide by priority only on narrow windows, one value per column.
- Kit strings in the GUI follow the language switch.

### Fixed
- The agent skill's frontmatter loads in agents.

### Security
- Actions pinned to commit SHAs, read-only tokens by default, gitleaks and zizmor in CI, OpenSSF Scorecard,
  Dependabot cooldown, pre-commit hooks.

## [0.1.6] - 2026-10-12
### Changed
- README images are kept out of the sdist (2.6 MB → 0.8 MB); the Eval screenshot is gone from the README.

## [0.1.5] - 2026-10-12
### Added
- Denser, readable GUI tables and repo panels; cropped screenshots in the README.
- Contributor Covenant 2.1 code of conduct.

## [0.1.4] - 2026-10-12
### Added
- GUI in English or Russian, switched in the header.
- Community files, issue and PR templates, Dependabot, ruff in CI.

## [0.1.3] - 2026-10-12
### Changed
- Plain-language pass over the README, GUI, CLI, `doctor`, `config` and the installers.

## [0.1.2] - 2026-10-12
### Added
- Advanced mode with an OpenAI-compatible LLM and a System One fit column.
### Changed
- Eval snapshots are kept out of the sdist (22 MB → 0.8 MB).

## [0.1.1] - 2026-10-12
### Added
- Standalone release builds, `repo-scout config`, an optional LLM settings file.
### Fixed
- Log pruning keeps the logs of parallel processes that may still be running.

## [0.1.0] - 2026-10-12
First public release.

[Unreleased]: https://github.com/octrow/repo-scout/compare/v0.1.12...HEAD
[0.1.12]: https://github.com/octrow/repo-scout/compare/v0.1.11...v0.1.12
[0.1.11]: https://github.com/octrow/repo-scout/compare/v0.1.10...v0.1.11
[0.1.10]: https://github.com/octrow/repo-scout/compare/v0.1.9...v0.1.10
[0.1.9]: https://github.com/octrow/repo-scout/compare/v0.1.8...v0.1.9
[0.1.8]: https://github.com/octrow/repo-scout/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/octrow/repo-scout/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/octrow/repo-scout/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/octrow/repo-scout/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/octrow/repo-scout/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/octrow/repo-scout/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/octrow/repo-scout/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/octrow/repo-scout/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/octrow/repo-scout/releases/tag/v0.1.0
