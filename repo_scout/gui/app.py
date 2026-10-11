"""GUI repo-scout на NiceGUI: `repo-scout` без аргументов или `repo-scout gui [--port 8790]`."""
import argparse
import os
import sys

from nicegui import app, ui

from . import eval_page, index_page, runs_page, search_page
from . import port as portmod
from .kit import run_pool, theme

DEFAULT_PORT = 8790


async def _stop() -> None:
    await run_pool.terminate_all_live_processes()


def register_pages() -> None:
    search_page.register()
    runs_page.register()
    index_page.register()
    eval_page.register()
    app.add_api_route(portmod.HEALTH_PATH, lambda: {"app": portmod.APP_ID, "pid": os.getpid()})


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="repo-scout gui")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    a = ap.parse_args(argv)
    try:
        port = portmod.choose(a.port)
    except RuntimeError as e:
        sys.exit(f"gui: {e}")
    if port is None:
        return
    print(f"GUI: http://{portmod.HOST}:{port}/")
    theme.apply_theme()
    register_pages()
    app.on_shutdown(_stop)
    # reload=False: страницы регистрируются в этом процессе, поэтому literal-guard NiceGUI
    # (`__name__ in {"__main__", "__mp_main__"}`) не нужен: main() вызывается из консольной команды
    ui.run(host=portmod.HOST, port=port, reload=False, language="ru", show=False, title="repo-scout")


if __name__ in {"__main__", "__mp_main__"}:  # python -m repo_scout.gui.app
    main()
