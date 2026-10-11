# repo-scout

Ищет на GitHub готовые решения перед тем, как писать своё, и делает Шаг 1 триажа из `docs/repo-triage.md`: стоп-правила (мёртвый / игрушка), флаги (форк, stars≫commits, archived, новый), баллы свежести и популярности.

```bash
repo-scout "query" "another query language:python" [--lang python] [--exclude RE] [--must RE] [--months 6] [--new-days 60] [--limit 50] [--all] [--json]
uv sync && uv run pytest -q
uv tool install --editable .   # команда repo-scout в PATH
```

Зависимости: Python 3.11+ (uv) и авторизованный `gh`. Скилл для агента лежит в `skill/SKILL.md` и подключён симлинком `~/.agents/skills/repo-scout`.
