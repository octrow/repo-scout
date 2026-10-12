<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="repo-scout: найди репозиторий, на базе которого можно строить решение, до написания собственного кода.">
</p>

<p align="center">
  <a href="https://github.com/octrow/repo-scout/actions/workflows/test.yml"><img src="https://github.com/octrow/repo-scout/actions/workflows/test.yml/badge.svg" alt="test"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+">
</p>

<p align="center">
  <a href="README.md">English</a> | <b>Русский</b>
</p>

Поиск решений на GitHub, которые можно переиспользовать, до того как писать код с нуля. Небольшие новые проекты тоже учитываются: они ранжируются по смысловой близости к вашей задаче, а не по количеству звёзд.

<p align="center">
  <img src="./assets/readme/triage.svg" width="100%" alt="Строки из реального прогона поиска инструментов аудита README. Репозиторий с 22 звёздами на первом месте с близостью 0.84. Флаги отмечают новый репо, 100% ранний всплеск звёзд и только косметические коммиты. Правила отсева отсекают заброшенные репозитории, списки awesome и игрушечные проекты.">
</p>

repo-scout выполняет серию поисковых запросов к GitHub, объединяет результаты и проводит автоматический первичный отбор по правилам [`docs/repo-triage.ru.md`](docs/repo-triage.ru.md). Отбор включает стоп-правила (мёртвый, игрушка, шум, нет кода, не по теме), флаги (форк, звёзды ≫ коммиты, архивный, новый, шаблон, только косметика, всплеск звёзд), а также баллы свежести и популярности. Результаты сортируются по смысловой близости к описанию задачи с помощью локальной CPU-модели эмбеддингов. Ранжирование никогда не вызывает LLM.

## Установка

Одна команда. Она ставит [uv](https://docs.astral.sh/uv/) (он сам скачает Python) и [GitHub CLI](https://cli.github.com/), если их нет, устанавливает последний [релиз](https://github.com/octrow/repo-scout/releases), один раз проводит через `gh auth login`, скачивает локальную модель эмбеддингов и предлагает открыть GUI.

```bash
# macOS / Linux
curl -LsSf https://raw.githubusercontent.com/octrow/repo-scout/main/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/octrow/repo-scout/main/install.ps1 | iex"
```

Повторный запуск той же команды обновляет приложение. Опции: `sh -s -- --version 0.1.0`, `--main` (текущая ветка main вместо релиза), `--no-launch`, `--uninstall` (прогоны и индекс остаются). В Windows перед запуском задайте `$env:REPO_SCOUT_VERSION`, `$env:REPO_SCOUT_MAIN=1`, `$env:REPO_SCOUT_NO_LAUNCH=1` или `$env:REPO_SCOUT_UNINSTALL=1`.

Что-то не работает? `repo-scout doctor` проверяет gh, вход в GitHub и модель и подсказывает, как исправить каждый пункт.

### Или скачайте готовую сборку

В каждом [релизе](https://github.com/octrow/repo-scout/releases/latest) есть автономные сборки, которым не нужны Python и uv. Распакуйте архив и запустите `repo-scout` внутри него (в Windows — двойной щелчок по `repo-scout.exe`). Без аргументов он открывает GUI в браузере.

| Система | Файл |
|---|---|
| Windows x64 | `repo-scout-<версия>-windows-x86_64.zip` |
| macOS Apple Silicon | `repo-scout-<версия>-macos-arm64.tar.gz` |
| Linux x64 (glibc 2.35+, например Ubuntu 22.04+) | `repo-scout-<версия>-linux-x86_64.tar.gz` |
| Linux arm64 | `repo-scout-<версия>-linux-arm64.tar.gz` |

[GitHub CLI](https://cli.github.com/) по-прежнему нужен, а `gh auth login` надо один раз выполнить; `repo-scout doctor --fix` это проверит и скачает модель. Сборки не подписаны: Windows SmartScreen попросит подтвердить запуск («Подробнее» → «Выполнить в любом случае»), а на macOS для сборки, скачанной браузером, один раз нужен `xattr -dr com.apple.quarantine repo-scout`. На Mac с Intel используйте установку одной командой.

## Быстрый старт

Из клона, при наличии Python 3.11+, uv и авторизованного `gh`:

```bash
uv sync && uv tool install --editable .   # добавляет repo-scout в PATH
repo-scout --task "Live speech transcription with an overlay, runs on Linux" \
  "whisper live transcription" "speech to text overlay language:python" "topic:asr linux"
repo-scout                                # без аргументов: открывает GUI в браузере
```

## Как работает поиск

1. **Запросы**: каждый позиционный аргумент — поисковый запрос к GitHub (`language:`, `topic:`, `in:readme`). Рекомендуется 3–6 вариантов с синонимами. Не используйте `stars:`, так как малое число звёзд не является поводом для отсева.
2. **Второй круг** запускается автоматически. Формирует до 5 запросов вида `topic:<slug>` из наиболее частых тем в топ-10 (`--round2-k`, `--no-round2`).
3. **Индекс**: локальное хранилище ранее найденных кандидатов и их README добавляет ближайшие совпадения в пул (`--from-index N`, по умолчанию 50). База хранится в `~/.local/share/repo-scout/index.db` (`$REPO_SCOUT_INDEX`).
4. **Отбор (Triage)** применяет стоп-правила и флаги. Кандидаты ниже порога близости (`--min-closeness`, 0.64) отсеиваются как не по теме. Флаг `--all` показывает отсеянные строки.
5. **Всплеск звёзд**: топ-10 с ≥50★ проверяются по истории звёзд (`--stars-k`, `--no-stars-check`). Флаг показывает долю первых ~1000★, набранных в пиковые дни. Накрутка и вирусный запуск выглядят одинаково, поэтому флаг является измерением, а не вердиктом.

Жёсткие условия: `--lang python`, `--must REGEX` (обязательная группа слов, повторяемый), `--exclude REGEX` (запрещённые слова). Дополнительные опции: `--months 6`, `--new-days 60`, `--limit 50`, `--json`. Полный список доступен по `repo-scout --help`.

## Прогоны, вердикты и GUI

Каждый поиск сохраняется как прогон в `~/.local/share/repo-scout/runs/<date>-<slug>.json` (`$REPO_SCOUT_RUNS`). Используйте `--out FILE` для задания пути или `--no-save` для отключения сохранения. Флаг `--project P` привязывает прогон к проекту.

```bash
repo-scout verdict owner/repo "→ Разбор (как окно скрывается от захвата экрана)" --project P --task "..."
repo-scout gui [--port 8790]   # Поиск, Прогоны, Индекс, Eval
```

Вердикт сохраняется в Индексе и отображается в будущих поисках, никогда не скрывая репозиторий принудительно. GUI открывает сохранённые прогоны в виде интерактивной таблицы с README из Индекса и возможностью выставить вердикт в два клика. Поиски и eval запускаются в подпроцессах с живым логом и кнопкой отмены. GUI построен на встроенной копии nicegui-kit ([`repo_scout/gui/kit/VENDORED.ru.md`](repo_scout/gui/kit/VENDORED.ru.md)).

Логи пишутся в stderr и в `~/.local/state/repo-scout/run.log` (`$REPO_SCOUT_LOG`). Используйте `-q` для вывода только в файл лога.

## Черновик из LLM (опционально)

Всё описанное выше работает без каких-либо API-ключей. Черновик из LLM — дополнение: если задан `OMNIROUTE_API_KEY`, модель может преобразовать потребность на любом языке в описание задачи, поисковые запросы и жёсткие условия. Она лишь заполняет черновик — вы проверяете его и запускаете поиск самостоятельно.

```bash
repo-scout draft "<что нужно найти на любом языке>"   # выводит готовую команду `repo-scout …`
```

| Переменная | По умолчанию |
|---|---|
| `OMNIROUTE_API_KEY` | не задана (функция отключена) |
| `OMNIROUTE_MODEL` | `free-stack` |
| `OMNIROUTE_BASE_URL` | `http://127.0.0.1:20128/v1` (OpenAI-совместимый `/chat/completions`) |

`repo-scout config` спрашивает эти значения и сохраняет в `~/.config/repo-scout/.env` (`$REPO_SCOUT_ENV`, файл доступен только вам). Enter оставляет значение, `-` очищает. `repo-scout doctor` показывает, включён ли черновик. Настоящие переменные окружения важнее файла. В клоне работает и `.env` в корне репозитория (в `.gitignore`), он переопределяет пользовательский файл. `REPO_SCOUT_GUI_DRAFT=1` показывает кнопку «Черновик» в GUI.

## Оценка качества (Eval)

Эталонные наборы в `eval/*.toml` содержат прошлые поиски и репозитории с известными вердиктами. Воспроизведение офлайн из снапшотов GitHub позволяет измерять полноту выдачи ([`eval/README.ru.md`](eval/README.ru.md), [`eval/BASELINE.ru.md`](eval/BASELINE.ru.md)).

```bash
repo-scout eval eval/*.toml [--no-round2] [--calls]      # офлайн, из снапшотов
repo-scout eval eval/*.toml --llm-draft [--record]       # запросы агента vs черновик LLM vs объединение
repo-scout eval --fake-stars [--all-grid]                # точность/полнота/FPR флага всплеска звёзд
```

## Агентский навык (Skill)

[`skill/SKILL.ru.md`](skill/SKILL.ru.md) описывает полный рабочий процесс для AI-агентов: поиск, осмотр и вердикты. Установка: `ln -s "$PWD/skill" ~/.agents/skills/repo-scout`.

## Разработка

```bash
uv sync && uv run pytest -q
```

Глоссарий предметной области находится в [`CONTEXT.ru.md`](CONTEXT.ru.md), архитектурные решения — в [`docs/adr/`](docs/adr/).

## Лицензия

[MIT](LICENSE). Сторонний код, данные и шрифты перечислены в [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
