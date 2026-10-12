"""Navigation header shared across all pages (patterned after `_shell` from showcase nicegui-kit)."""
from nicegui import ui

from .i18n import LANGS, current, set_lang, t
from .kit import theme

PAGES = {"/": "Search", "/runs": "Runs", "/index": "Index", "/eval": "Eval"}
BRAND = "repo-scout"


def shell(here: str, max_width: str) -> None:
    """Header: brand, navigation, theme toggle. `here` highlights current section."""
    header = ui.header().style("flex-direction: column; align-items: stretch;"
                               " gap: var(--ic-s3); padding: var(--ic-s3) 0 0")
    with header, ui.row().classes(f"ic-split w-full {max_width} mx-auto items-center justify-between") \
            .style("padding: 0 var(--ic-s6); flex-wrap: nowrap"):
        with ui.row().classes("items-center").style(
                "gap: var(--ic-s4) var(--ic-s6); flex-wrap: nowrap; min-width: 0"):
            ui.label(BRAND).classes("t-brand gt-xs")
            with ui.element("nav").style("display: flex; flex-direction: row; gap: var(--ic-s4)"):
                for path, title in PAGES.items():
                    link = ui.link(t(title), path).classes("ic-nav-link")
                    if path == here or (path != "/" and here.startswith(path + "/")):
                        link.classes("ic-nav-link--here").props('aria-current="page"')
        with ui.row().classes("items-center").style("gap: var(--ic-s3); flex-wrap: nowrap"):
            _lang_toggle()
            theme.theme_toggle()


def _lang_toggle() -> None:
    """EN | RU switch: saves the choice and reloads the page so every label is drawn in the new language."""
    def pick(e) -> None:
        if e.value and e.value != current():
            set_lang(e.value)
            ui.navigate.reload()
    ui.toggle({lang: lang.upper() for lang in LANGS}, value=current(), on_change=pick) \
        .props(f'dense flat no-caps aria-label="{t("Interface language")}"')
