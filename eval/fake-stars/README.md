**English** | **[Русский](README.ru.md)**

# eval/fake-stars

`labels.csv` (repo,label,source): label 1 = fake stars, 0 = organic. Generated via `build_labels.py` (seed 0): active repos with ≥50★ as of 2026-10-11.

- Positives (100): `data/250101/fake_stars_low_activity_repos.csv` and `fake_stars_clustered_repos.csv` with `p_stars_* ≥ 0.5` and `n_stars ≥ 50`.
- Controls / Negatives (100): all "→ Deep dive" from `eval/*.toml` (organic, source `eval/<set>.toml`) plus random samples from `data/250101/sample_repo_ids.csv` (`starscout-sample`; sample may contain undetected manipulated repos, understating precision).
- `snapshots/`: star history (`stars/`) and forks (GraphQL) as of date in `meta.json`. Re-recording: `repo-scout eval --fake-stars --record` (network, `gh`).

Limitation: StarScout labels reflect stargazer accounts as of January 2025; some stars may have since been pruned on GitHub.

## Attribution

Labels sourced from the StarScout project (https://github.com/hehao98/StarScout, Apache-2.0): He et al., "4.5 Million (Suspected) Fake Stars in GitHub". Raw data files are not mirrored in this repository; `labels.csv` stores only repository names and corresponding label indicators.
