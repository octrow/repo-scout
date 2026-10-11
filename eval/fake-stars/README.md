# eval/fake-stars

`labels.csv` (repo,label,source): label 1 = накрутка, 0 = нет. Собран `build_labels.py` (seed 0): живые репо с ≥50★ на 2026-10-11.

- Позитивы (100): `data/250101/fake_stars_low_activity_repos.csv` и `fake_stars_clustered_repos.csv` с `p_stars_* ≥ 0.5` и `n_stars ≥ 50`.
- Негативы (100): все «→ Разбор» из `eval/*.toml` (органика, источник `eval/<набор>.toml`) плюс случайные из `data/250101/sample_repo_ids.csv` (`starscout-sample`; в выборке могут быть и накрученные, это занижает точность).
- `snapshots/`: история звёзд (`stars/`) и форки (GraphQL) на дату `meta.json`. Перезапись: `repo-scout eval --fake-stars --record` (сеть, `gh`).

Ограничение: метки StarScout получены по аккаунтам звездочётов на январь 2025; сейчас на GitHub часть звёзд могла быть снята.

## Attribution

Метки взяты из данных проекта StarScout (https://github.com/hehao98/StarScout, Apache-2.0): He et al., "4.5 Million (Suspected) Fake Stars in GitHub". Файлы данных не копируются в репозиторий, в `labels.csv` только имена репо и метки, выбранные по ним.
