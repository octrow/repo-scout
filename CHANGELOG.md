**English** | **[Русский](CHANGELOG.ru.md)**

# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Fixed
- Search no longer crashes when GitHub returns an empty (null) commit in a repo's history.
- `eval --fake-stars` closes the labels file it reads.

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

[Unreleased]: https://github.com/octrow/repo-scout/compare/v0.1.7...HEAD
[0.1.7]: https://github.com/octrow/repo-scout/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/octrow/repo-scout/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/octrow/repo-scout/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/octrow/repo-scout/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/octrow/repo-scout/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/octrow/repo-scout/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/octrow/repo-scout/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/octrow/repo-scout/releases/tag/v0.1.0
