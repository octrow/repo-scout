# repo-scout

Ищет на GitHub готовые решения перед тем, как писать своё, и делает Шаг 1 триажа из `docs/repo-triage.md`: стоп-правила (мёртвый / игрушка), флаги (форк, stars≫commits, archived, новый, всплеск★), баллы свежести и популярности.

```bash
repo-scout --task "English task description" "query" "another query language:python" [--lang python] [--exclude RE] [--must RE] [--months 6] [--new-days 60] [--limit 50] [--no-round2] [--round2-k 10] [--from-index 50] [--stars-k 10] [--no-stars-check] [--all] [--json]
repo-scout verdict owner/repo "→ Осмотр" --project P --task "..."
repo-scout eval eval/*.toml [--no-round2] [--calls]   # Золотые наборы, офлайн по снапшотам
repo-scout eval --fake-stars [--all-grid]   # precision/recall/FPR флага «всплеск★» (tune/test) на eval/fake-stars (офлайн; --record — сеть)
uv sync && uv run pytest -q
uv tool install --editable .   # команда repo-scout в PATH
```

Зависимости: Python 3.11+ (uv) и авторизованный `gh`. Второй круг (один раз `topic:<slug>` из частых topics топ-10) и Индекс работают сами; колонка `источник` показывает, откуда строка. Скилл для агента лежит в `skill/SKILL.md` и подключён симлинком `~/.agents/skills/repo-scout`.

Ход работы: stderr и `~/.local/state/repo-scout/run.log` (`tail -f` из другого терминала; `$REPO_SCOUT_LOG`, `-q`).
