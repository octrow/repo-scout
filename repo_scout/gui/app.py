"""NiceGUI interface for repo-scout: `repo-scout` without arguments or `repo-scout gui [--port 8790]`."""
import argparse
import os
import sys

from nicegui import app, ui

from . import eval_page, index_page, runs_page, search_page
from . import port as portmod
from .i18n import QUASAR, current
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
    ap.add_argument("--open", action="store_true", help="open the GUI in the default browser")
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
    # reload=False: pages are registered in this process, so NiceGUI literal-guard
    # (`__name__ in {"__main__", "__mp_main__"}`) is not needed: main() is called from CLI command
    # Quasar's own texts (pagination etc.) follow the language at start; the header switch changes them on restart
    ui.run(host=portmod.HOST, port=port, reload=False, language=QUASAR[current()], show=a.open, title="repo-scout")


if __name__ in {"__main__", "__mp_main__"}:  # python -m repo_scout.gui.app
    main()
