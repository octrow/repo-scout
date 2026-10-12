**[English](VENDORED.md)** | **Русский**

# Vendored nicegui-kit

Копия из `~/dev/pylibs/nicegui-kit/src/nicegui_kit/`, коммит `34dd42a` (ветка `feat/nicegui-kit-texts-tokens-wide-tables`;
`texts`, токены дизайн-системы, широкие таблицы), дата копирования 2026-10-12.
Модули: `theme`, `layout`, `table`, `texts`, `run_pool`, `run_monitor`, `assets/fonts` (Inter, OFL, `LICENSE.txt`). `hotkeys` не копировался.

Модули побайтно совпадают с kit; общие улучшения отправлять в kit через его `docs/proposals/`.

## Правки

- `__init__.py`: докстринг заменён на ссылку на этот файл.
- Больше ничего. Строки kit переключаются вместе с языком GUI через `i18n.sync_kit()` (вызывается в `shell.shell()`),
  а не правкой копии.
