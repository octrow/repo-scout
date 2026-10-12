[English](CONTRIBUTING.md) | **Русский**

# Как поучаствовать

Баг-репорты, идеи и pull request'ы приветствуются. Участвуя, вы принимаете [Кодекс поведения](CODE_OF_CONDUCT.md) (на английском). Перед большим изменением откройте issue, чтобы договориться о подходе.

## Подготовка

Нужны Python 3.11+, [uv](https://docs.astral.sh/uv/) и [GitHub CLI](https://cli.github.com/), в котором выполнен `gh auth login`.

```bash
git clone https://github.com/octrow/repo-scout && cd repo-scout
uv sync
uv run repo-scout doctor --fix   # проверяет gh и скачивает модель эмбеддингов
uv run repo-scout                # открывает GUI
```

## Перед pull request

```bash
uv run ruff check .
uv run pytest -q
```

- На новое поведение добавьте тест. Тесты не ходят в GitHub и к внешним моделям: они используют снапшоты и monkeypatch.
- Если меняете поведение или опции, обновите README.md и README.ru.md.
- Используйте термины из [CONTEXT.ru.md](CONTEXT.ru.md) (Кандидат, Отсев, Близость, Пригодность...). Крупное архитектурное решение оформите как ADR в [docs/adr/](docs/adr/).
- Ранжирование остаётся детерминированным. Внешние модели могут добавлять информацию, но не отбрасывают и не переупорядочивают строки ([ADR 0002](docs/adr/0002-advanced-mode-external-models.ru.md)).
- Сообщения коммитов: `<type>: <description>`, где type - feat, fix, refactor, docs, test, chore, perf или ci.

## Релизы

Поднимите `version` в pyproject.toml, влейте в main и запушьте тег `vX.Y.Z`. Release-workflow прогонит тесты, соберёт пакеты для Linux, macOS и Windows и опубликует релиз.
