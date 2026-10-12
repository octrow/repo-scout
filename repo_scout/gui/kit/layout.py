"""Page, heading, button and state helpers matching the kit's spacing rhythm.

Gaps and sizes come from theme.py classes (`ic-page`, `ic-card`, ...), never
from Tailwind gap-* (NiceGUI #2171) or px written by a page. Each helper also
keeps its non-gap Tailwind structure (w-full, items-*): apps with their own
theme (jobs, tlf) use these helpers without the kit's CSS.
"""

from collections.abc import Callable

from nicegui import ui

from .texts import tr

HEADING_CLASSES = {
    1: "t-title-page",
    2: "t-title-section",
    3: "t-title-group",
}
PAGE_MAX_WIDTH_FORM = "max-w-4xl"
PAGE_MAX_WIDTH_WIDE = "max-w-6xl"

# Button kind -> Quasar look. One primary per screen; danger = stops, erases or
# sends out, and stands apart (after ui.space()) from the everyday buttons.
BUTTON_KINDS = {
    "primary": "unelevated color=primary",
    "normal": "outline color=primary",
    "quiet": "flat color=primary",
    "danger": "outline color=negative",
}

# Field kind -> native input attributes: the right mobile keyboard (inputmode),
# browser/password-manager autofill (autocomplete) and the Enter key label
# (enterkeyhint). Quasar forwards these attrs to the <input>.
FIELD_KINDS: dict[str, dict[str, str]] = {
    "text": {},
    "name": {"autocomplete": "name", "autocapitalize": "words"},
    "email": {"type": "email", "inputmode": "email", "autocomplete": "email",
              "autocapitalize": "off", "spellcheck": "false"},
    "tel": {"type": "tel", "inputmode": "tel", "autocomplete": "tel"},
    "url": {"type": "url", "inputmode": "url", "autocomplete": "url",
            "autocapitalize": "off", "spellcheck": "false"},
    "search": {"type": "search", "inputmode": "search", "enterkeyhint": "search",
               "autocomplete": "off"},
    "number": {"inputmode": "decimal", "autocomplete": "off"},
    "integer": {"inputmode": "numeric", "autocomplete": "off"},
    "code": {"inputmode": "numeric", "autocomplete": "one-time-code", "spellcheck": "false"},
    "password": {"autocomplete": "current-password"},
    "new-password": {"autocomplete": "new-password"},
}


def heading(text: str, *, level: int = 2) -> ui.element:
    """Real h1/h2/h3 tag (screen-reader navigable) with the matching type role."""
    with ui.element(f"h{level}").classes(HEADING_CLASSES[level]) as element:
        ui.label(text)
    return element


def page_container(*, max_width: str = PAGE_MAX_WIDTH_FORM) -> ui.column:
    """Centred page column; every page puts all of its content inside one."""
    ui.query(".nicegui-content").style("padding: 0; gap: 0")
    return ui.column().classes(f"ic-page w-full mx-auto p-6 items-stretch {max_width}")


def section_card(*, recessive: bool = False) -> ui.card:
    """Card with the project spacing rhythm; recessive=True for secondary content
    (sunken, borderless: it sits back from the regular cards)."""
    card = ui.card().classes("ic-card w-full items-stretch")
    if recessive:
        card.props("flat").classes("ic-card--recessive")
    return card


def filter_bar() -> ui.row:
    """One row for filter controls (topic/status/text/...) — the `ic-filters`
    convention: one control height across select/toggle/search, and full-width
    stacking under 700px (see theme.py). Used with `with layout.filter_bar():`."""
    return ui.row().classes("ic-filters w-full items-center flex-wrap")


def actions_row(*, end: bool = True) -> ui.row:
    """Buttons at the end of a dialog or card: right-aligned (`end=True`, dialogs,
    confirmations), or `end=False` for a top-to-bottom form, where the primary
    button sits on the fields' left edge, right under the last field the eye left."""
    align = "justify-end" if end else "justify-start ic-actions--start"
    return ui.row().classes(f"ic-actions w-full {align} items-center")


def button(
    text: str = "", *, kind: str = "normal", size: str = "ctl",
    on_click: Callable | None = None, **kwargs,
) -> ui.button:
    """The kit's button: `kind` from BUTTON_KINDS, `size` "ctl" (as tall as a
    field, for page controls) or "row" (compact, inside a list row)."""
    return ui.button(text, on_click=on_click, **kwargs).props(
        f"{BUTTON_KINDS[kind]} no-caps",
    ).classes(f"ic-btn-{size}")


def grid(*, min_col: str | None = None) -> ui.column:
    """A column grid with the kit gutter. Default: 12 columns, children take
    `.classes("ic-span-N")` and collapse to full width under 700px. With
    `min_col` (e.g. "18rem"): as many equal columns as fit, no spans needed."""
    if min_col is None:
        return ui.column().classes("ic-grid-12 w-full")
    return ui.column().classes("ic-grid w-full").style(f"--ic-col-min: {min_col}")


def _attr(value: str) -> str:
    return value.replace('"', "'")


def field(
    label: str, *, kind: str = "text", value: str = "", required: bool = False,
    hint: str | None = None, validation: dict[str, Callable] | None = None,
    suggestions: list[str] | None = None, enter: str | None = None,
    full_width: bool = True, on_change: Callable | None = None,
) -> ui.input:
    """The kit's text field: label on top (always, even when empty: never read
    as a placeholder), `hint` under it, error replaces hint.

    `kind` picks keyboard + autofill (FIELD_KINDS). Validation runs on blur, not
    while typing; once an error shows, every keystroke re-checks so it clears
    the moment the value is fixed. `required` adds the rule, a visible `*` and
    aria-required. `suggestions` -> inline autocomplete; `enter` -> enterkeyhint
    ("next", "done", "send", ...)."""
    rules = {tr("required", label=label): lambda v: bool(str(v or "").strip())} if required else {}
    rules.update(validation or {})
    password = kind in ("password", "new-password")
    el = ui.input(label, value=value, password=password, password_toggle_button=password,
                  autocomplete=suggestions, on_change=on_change, validation=rules or None)
    attrs = dict(FIELD_KINDS[kind])
    if enter:
        attrs["enterkeyhint"] = enter
    if required:
        attrs["aria-required"] = "true"
        el.classes("ic-required")
    if hint:
        attrs["hint"] = hint
    # bottom-slots: every field keeps the hint/error line, so a form's rhythm is even
    el.props("outlined dense stack-label bottom-slots " + " ".join(f'{k}="{_attr(v)}"' for k, v in attrs.items()))
    if full_width:
        el.classes("w-full")
    if rules:
        el.without_auto_validation()
        el.on("blur", lambda: el.validate())
        el.on_value_change(lambda: el.error is not None and el.validate())
    return el


def search_field(placeholder: str, *, on_change: Callable | None = None) -> ui.input:
    """Filter-bar search: magnifier + placeholder instead of a floating label, so
    it matches the select/toggle next to it; aria-label keeps the name for
    screen readers. The query itself is the field's content, so nothing is lost."""
    el = ui.input(placeholder=placeholder, on_change=on_change).props(
        'outlined dense clearable ' + " ".join(
            f'{k}="{v}"' for k, v in {**FIELD_KINDS["search"], "aria-label": _attr(placeholder)}.items()))
    with el.add_slot("prepend"):
        ui.icon("search").props('aria-hidden="true"')
    return el


def empty(text: str, action: tuple[str, Callable] | None = None) -> ui.row:
    """Nothing here yet: say what will appear and, if any, the one way to get it."""
    with ui.row().classes("ic-state items-center") as row:
        ui.label(text).classes("t-muted")
        if action:
            button(action[0], kind="quiet", size="row", on_click=action[1])
    return row


def waiting(text: str | None = None) -> ui.row:
    """A spinner with words, for anything slower than a blink."""
    with ui.row().classes("ic-state items-center") as row:
        ui.spinner(size="var(--ic-icon)", color="primary")
        ui.label(text or tr("loading")).classes("t-meta")
    return row


def failed(text: str, retry: Callable | None = None) -> ui.row:
    """What went wrong and what to do; no traces, no internal names."""
    with ui.row().classes("ic-state items-center") as row:
        ui.icon("error_outline").classes("ic-status--error").props('aria-hidden="true"')
        ui.label(text).classes("ic-status--error")
        if retry:
            button(tr("retry"), size="row", on_click=retry)
    return row


def markdown_reader(
    text: str, *, classes: str = "", max_height: str | None = None,
) -> ui.column:
    """A `.md-body` reading surface holding `ui.markdown(text)` — the shared shape
    for "render one document" pages (digest, transcript, job description).
    `max_height` (e.g. "60vh") makes it independently scrollable, for a dialog
    or side pane; omit it to let the surrounding layout size the column."""
    column = ui.column().classes(f"md-body {classes}".strip())
    if max_height is not None:
        column.style(f"max-height: {max_height}; overflow-y: auto")
    with column:
        ui.markdown(text)
    return column


def copy_for_chat_button(text: str) -> ui.button:
    """One button to copy `text` to the clipboard, with a confirmation toast."""

    def _copy() -> None:
        ui.clipboard.write(text)
        ui.notify(tr("copied"), type="positive")

    return button(tr("copy_for_chat"), icon="content_copy", on_click=_copy)
