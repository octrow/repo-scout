# Install options

The one-command install is in the [README](../README.md#install). This page holds the rest.

## Installer options

Run the same command again to update. Options: `sh -s -- --version 0.1.0`, `--main` (current main branch instead of a release), `--no-launch`, `--uninstall` (keeps your runs and index). On Windows set `$env:REPO_SCOUT_VERSION`, `$env:REPO_SCOUT_MAIN=1`, `$env:REPO_SCOUT_NO_LAUNCH=1` or `$env:REPO_SCOUT_UNINSTALL=1` first.

repo-scout is not on PyPI. The `repo-scout` package there is an unrelated project, so `pip install repo-scout` installs someone else's code.

If something does not work, run `repo-scout doctor`. It checks gh, the GitHub login and the model, and tells you how to fix each problem.

## Download a ready build

Each [release](https://github.com/octrow/repo-scout/releases/latest) has standalone builds that need no Python and no uv. Unpack the archive and run `repo-scout` inside it (on Windows, double-click `repo-scout.exe`). With no arguments it opens the GUI in your browser.

| System | File |
|---|---|
| Windows x64 | `repo-scout-<version>-windows-x86_64.zip` |
| macOS Apple Silicon | `repo-scout-<version>-macos-arm64.tar.gz` |
| Linux x64 (glibc 2.35+, e.g. Ubuntu 22.04+) | `repo-scout-<version>-linux-x86_64.tar.gz` |
| Linux arm64 | `repo-scout-<version>-linux-arm64.tar.gz` |

You still need the [GitHub CLI](https://cli.github.com/), and you need to run `gh auth login` once. `repo-scout doctor --fix` checks this and downloads the model.

The builds are not code-signed. Windows SmartScreen asks you to confirm ("More info" → "Run anyway"). On macOS, a build downloaded in a browser needs `xattr -dr com.apple.quarantine repo-scout` once. On an Intel Mac, use the one-command install.

## From a clone

With Python 3.11+, uv and an authenticated `gh`:

```bash
uv sync && uv tool install --editable .   # puts `repo-scout` on PATH
```
