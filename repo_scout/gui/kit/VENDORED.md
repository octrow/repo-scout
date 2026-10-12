**English** | **[Русский](VENDORED.ru.md)**

# Vendored nicegui-kit

Copied from `~/dev/pylibs/nicegui-kit/src/nicegui_kit/`, commit `adf21c1`, copy date 2026-10-11.
Modules: `theme`, `layout`, `table`, `run_pool`, `run_monitor`, `assets/fonts` (Inter, OFL, `LICENSE.txt`). `hotkeys` was not vendored.

Every code modification is marked with `# repo-scout:`. General improvements should be submitted upstream to the kit via `docs/proposals/`.

## Modifications

- `run_monitor.py`: absolute `nicegui_kit` imports replaced with relative imports.
- `__init__.py`: docstring replaced with reference to this file (marked `# repo-scout:`).
- Everything else unchanged (`nicegui-kit` strings in constants — localStorage key and task name — left as is).
- Files longer than 400 lines (`theme.py`) are kept as-is since this is a vendored copy.
- Python: vendored copy works on 3.12; `requires-python >=3.11` constraint is maintained as tests pass.
