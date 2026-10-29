**[English](CHANGELOG.md)** | **Русский**

# Журнал изменений

Формат по [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии по [SemVer](https://semver.org/lang/ru/).

## [Unreleased]

### Исправлено
- Поиск больше не падает, когда GitHub отдаёт пустой (null) коммит в истории репозитория.
- `eval --fake-stars` закрывает прочитанный файл с метками.
- Поиск больше не падает, когда GitHub не смог обновить репозиторий из Index; репозиторий остаётся в Index.

## [0.1.7] - 2026-10-14

### Добавлено
- Демо-GIF реального поиска и сравнение с похожими инструментами в README.
- Таблицы GUI помещаются в окно; колонки скрываются по приоритету только в узком окне, одно значение на колонку.
- Строки kit в GUI переключаются вместе с языком.

### Исправлено
- Frontmatter агентского skill загружается в агентах.

### Безопасность
- Actions закреплены по SHA коммитов, токены по умолчанию только на чтение, gitleaks и zizmor в CI,
  OpenSSF Scorecard, cooldown в Dependabot, хуки pre-commit.

## [0.1.6] - 2026-10-12
### Изменено
- Картинки README не попадают в sdist (2,6 МБ → 0,8 МБ); скриншот Eval убран из README.

## [0.1.5] - 2026-10-12
### Добавлено
- Более плотные и читаемые таблицы и панели репозиториев в GUI; обрезанные скриншоты в README.
- Кодекс поведения Contributor Covenant 2.1.

## [0.1.4] - 2026-10-12
### Добавлено
- GUI на английском или русском, переключатель в шапке.
- Файлы сообщества, шаблоны issue и PR, Dependabot, ruff в CI.

## [0.1.3] - 2026-10-12
### Изменено
- Тексты README, GUI, CLI, `doctor`, `config` и установщиков переписаны простым языком.

## [0.1.2] - 2026-10-12
### Добавлено
- Расширенный режим с OpenAI-совместимой LLM и колонкой соответствия System One.
### Изменено
- Снимки eval не попадают в sdist (22 МБ → 0,8 МБ).

## [0.1.1] - 2026-10-12
### Добавлено
- Автономные сборки в релизах, `repo-scout config`, необязательный файл настроек LLM.
### Исправлено
- Очистка логов не трогает логи параллельных процессов, которые ещё могут работать.

## [0.1.0] - 2026-10-12
Первый публичный релиз.

[Unreleased]: https://github.com/octrow/repo-scout/compare/v0.1.7...HEAD
[0.1.7]: https://github.com/octrow/repo-scout/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/octrow/repo-scout/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/octrow/repo-scout/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/octrow/repo-scout/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/octrow/repo-scout/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/octrow/repo-scout/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/octrow/repo-scout/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/octrow/repo-scout/releases/tag/v0.1.0
