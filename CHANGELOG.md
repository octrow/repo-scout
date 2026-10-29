**English** | **[Русский](CHANGELOG.ru.md)**

# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/octrow/repo-scout/compare/v0.1.8...HEAD
[0.1.8]: https://github.com/octrow/repo-scout/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/octrow/repo-scout/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/octrow/repo-scout/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/octrow/repo-scout/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/octrow/repo-scout/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/octrow/repo-scout/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/octrow/repo-scout/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/octrow/repo-scout/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/octrow/repo-scout/releases/tag/v0.1.0
