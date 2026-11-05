# Варианты установки

Установка одной командой описана в [README](../README.ru.md#установка). Здесь остальное.

## Опции установщика

Чтобы обновиться, запустите ту же команду ещё раз. Опции: `sh -s -- --version 0.1.0`, `--main` (текущая ветка main вместо релиза), `--no-launch`, `--uninstall` (прогоны и индекс остаются). В Windows перед запуском задайте `$env:REPO_SCOUT_VERSION`, `$env:REPO_SCOUT_MAIN=1`, `$env:REPO_SCOUT_NO_LAUNCH=1` или `$env:REPO_SCOUT_UNINSTALL=1`.

На PyPI repo-scout нет. Пакет `repo-scout` там - чужой проект, и `pip install repo-scout` поставит чужой код.

Если что-то не работает, запустите `repo-scout doctor`. Он проверит gh, вход в GitHub и модель и подскажет, как исправить каждую проблему.

## Готовая сборка

В каждом [релизе](https://github.com/octrow/repo-scout/releases/latest) есть автономные сборки, которым не нужны Python и uv. Распакуйте архив и запустите `repo-scout` внутри него (в Windows дважды щёлкните `repo-scout.exe`). Без аргументов он открывает GUI в браузере.

| Система | Файл |
|---|---|
| Windows x64 | `repo-scout-<версия>-windows-x86_64.zip` |
| macOS Apple Silicon | `repo-scout-<версия>-macos-arm64.tar.gz` |
| Linux x64 (glibc 2.35+, например Ubuntu 22.04+) | `repo-scout-<версия>-linux-x86_64.tar.gz` |
| Linux arm64 | `repo-scout-<версия>-linux-arm64.tar.gz` |

[GitHub CLI](https://cli.github.com/) всё равно нужен, и `gh auth login` нужно один раз выполнить. `repo-scout doctor --fix` проверит это и скачает модель.

Сборки не подписаны. Windows SmartScreen попросит подтвердить запуск («Подробнее» → «Выполнить в любом случае»). На macOS сборке, скачанной через браузер, один раз нужен `xattr -dr com.apple.quarantine repo-scout`. На Mac с Intel используйте установку одной командой.

## Из клона

Нужны Python 3.11+, uv и `gh` с выполненным входом:

```bash
uv sync && uv tool install --editable .   # добавляет repo-scout в PATH
```
