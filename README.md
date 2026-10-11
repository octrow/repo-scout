# repo-scout

Ищет на GitHub готовые решения перед тем, как писать своё, и делает Шаг 1 триажа из `~/dev/docs/repo-triage.md`: стоп-правила (мёртвый / игрушка), флаги (форк, stars≫commits, archived, новый), баллы свежести и популярности.

```bash
./scout.py "query" "another query language:python" [--months 6] [--new-days 60] [--limit 50] [--all] [--json]
python3 test_scout.py
```

Зависимости: Python 3.10+ и авторизованный `gh`. Скилл для агента лежит в `skill/SKILL.md` и подключён симлинком `~/.agents/skills/repo-scout`.
