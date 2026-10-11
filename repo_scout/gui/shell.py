"""Шапка с навигацией, общая для всех страниц (по образцу `_shell` из showcase nicegui-kit)."""
from nicegui import ui

from .kit import theme

PAGES = {"/": "Поиск", "/runs": "Прогоны", "/index": "Индекс", "/eval": "Eval"}
BRAND = "repo-scout"


def shell(here: str, max_width: str) -> None:
    """Шапка: бренд, навигация, переключатель темы. `here` подсвечивает текущий раздел."""
    header = ui.header().style("flex-direction: column; align-items: stretch;"
                               " gap: var(--ic-s3); padding: var(--ic-s3) 0 0")
    with header, ui.row().classes(f"ic-split w-full {max_width} mx-auto items-center justify-between") \
            .style("padding: 0 var(--ic-s6); flex-wrap: nowrap"):
        with ui.row().classes("items-center").style(
                "gap: var(--ic-s4) var(--ic-s6); flex-wrap: nowrap; min-width: 0"):
            ui.label(BRAND).classes("t-brand gt-xs")
            with ui.element("nav").style("display: flex; flex-direction: row; gap: var(--ic-s4)"):
                for path, title in PAGES.items():
                    link = ui.link(title, path).classes("ic-nav-link")
                    if path == here or (path != "/" and here.startswith(path + "/")):
                        link.classes("ic-nav-link--here").props('aria-current="page"')
        theme.theme_toggle()
