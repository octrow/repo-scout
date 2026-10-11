# Vendored nicegui-kit

Копия из `~/dev/pylibs/nicegui-kit/src/nicegui_kit/`, коммит `adf21c1`, дата копирования 2026-10-11.
Модули: `theme`, `layout`, `table`, `run_pool`, `run_monitor`, `assets/fonts` (Inter, OFL, `LICENSE.txt`). `hotkeys` не копировался.

Каждая правка кода помечена `# repo-scout:`. Общие улучшения отправлять в кит через `docs/proposals/`.

## Правки

- `run_monitor.py`: абсолютные импорты `nicegui_kit` заменены на относительные.
- `__init__.py`: докстринг заменён на ссылку на этот файл (помечено `# repo-scout:`).
- Остальное без изменений (строки `nicegui-kit` в константах — ключ localStorage и имя таска — оставлены как есть).
- Файлы длиннее 400 строк (`theme.py`) не правим: это копия.
- Python: копия работает на 3.12; ограничение `requires-python >=3.11` сохранено, если тесты проходят.
