# repo-scout

Ищет на GitHub готовые решения перед тем, как писать своё, и делает Шаг 1 триажа из `docs/repo-triage.md`: стоп-правила (мёртвый / игрушка), флаги (форк, stars≫commits, archived, новый, всплеск★), баллы свежести и популярности.

```bash
repo-scout --task "English task description" "query" "another query language:python" [--lang python] [--exclude RE] [--must RE] [--months 6] [--new-days 60] [--limit 50] [--no-round2] [--round2-k 10] [--from-index 50] [--stars-k 10] [--no-stars-check] [--project P] [--out FILE] [--no-save] [--all] [--json]
repo-scout                     # без аргументов = GUI (то же, что repo-scout gui [--port 8790]): Поиск, Прогоны, Индекс, Eval (127.0.0.1)
# порт занят другой программой — предложит следующий свободный; уже запущенным GUI — ссылка и перезапуск по желанию (по умолчанию нет)
repo-scout draft "<потребность на любом языке>"   # Черновик LLM: одна строка `repo-scout …` (нужен ключ, см. ниже)
repo-scout eval eval/*.toml --llm-draft [--record]   # полнота: Запросы агента / Черновик LLM / объединение, токены и время
repo-scout verdict owner/repo "→ Осмотр" --project P --task "..."
repo-scout eval eval/*.toml [--no-round2] [--calls]   # Золотые наборы, офлайн по снапшотам
repo-scout eval --fake-stars [--all-grid]   # precision/recall/FPR флага «всплеск★» (tune/test) на eval/fake-stars (офлайн; --record — сеть)
uv sync && uv run pytest -q
uv tool install --editable .   # команда repo-scout в PATH
```

Зависимости: Python 3.11+ (uv) и авторизованный `gh`. Второй круг (один раз `topic:<slug>` из частых topics топ-10) и Индекс работают сами; колонка `источник` показывает, откуда строка. Скилл для агента лежит в `skill/SKILL.md` и подключён симлинком `~/.agents/skills/repo-scout`.

Каждый поиск сохраняется как Прогон: `~/.local/share/repo-scout/runs/<дата>-<slug>.json` (`$REPO_SCOUT_RUNS`; `--out` — свой путь, `--no-save` — не сохранять, при `--record`/`--replay` не сохраняется). Прогоны открываются в GUI: таблица с фильтрами, README из Индекса, Вердикт в два клика.

GUI (`repo_scout/gui/`) построен на копии nicegui-kit (`repo_scout/gui/kit/VENDORED.md`); поиск и eval запускаются подпроцессом с живым логом и отменой.

Ход работы: stderr и `~/.local/state/repo-scout/run.log` (`tail -f` из другого терминала; `$REPO_SCOUT_LOG`, `-q`).

Черновик LLM (опционально, Без LLM остаётся умолчанием): переменные окружения `OMNIROUTE_API_KEY` (без него фичи нет), `OMNIROUTE_MODEL` (по умолчанию `free-stack`), `OMNIROUTE_BASE_URL` (по умолчанию `http://127.0.0.1:20128/v1`, OpenAI-совместимый `/chat/completions`). Реальное окружение главнее файла `.env` в корне репозитория (в git не попадает). По Потребности модель предлагает Описание задачи, Запросы и Жёсткие условия: `repo-scout draft "…"` печатает готовую команду, в GUI («Поиск») появляется поле «Что ищем» и кнопка «Черновик из LLM», которая только заполняет форму. Снапшоты `--record`/`--replay` кэшируют и ответы модели (`llm/` рядом со снапшотами GitHub).
