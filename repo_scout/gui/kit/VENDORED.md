**English** | **[Русский](VENDORED.ru.md)**

# Vendored nicegui-kit

Copied from `~/dev/pylibs/nicegui-kit/src/nicegui_kit/`, commit `34dd42a` (branch `feat/nicegui-kit-texts-tokens-wide-tables`;
`texts`, design tokens, wide tables), copy date 2026-10-12.
Modules: `theme`, `layout`, `table`, `texts`, `run_pool`, `run_monitor`, `assets/fonts` (Inter, OFL, `LICENSE.txt`). `hotkeys` was not vendored.

The modules are byte-identical to the kit; general improvements go upstream via the kit's `docs/proposals/`.

## Modifications

- `__init__.py`: docstring replaced with a reference to this file.
- Nothing else. Kit strings follow the GUI language through `i18n.sync_kit()` (called by `shell.shell()`),
  not by editing the copy.
