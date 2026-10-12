"""Search page (`/`): form, command preview, subprocess execution with live logs."""
import html
import sqlite3
import tomllib
from collections.abc import Callable
from datetime import datetime

from nicegui import run, ui

from .. import cli, llm
from ..index import Index, default_path
from ..log import log
from . import search_form as sf
from . import shell
from .i18n import t
from .kit import layout, run_monitor, run_pool
from .kit.texts import tr

NOTIFY_PERIOD = 1.0
COMMAND_HINT = "Fill in the task and queries to see the command"
NUMBER_LABELS = {"months": "Months since last push (0 = any)", "new_days": "Days a repo counts as new",
                 "limit": "Results per query", "min_closeness": "Closeness threshold",
                 "from_index": "Closest repos from Index", "round2_k": "Repos for round 2 topics",
                 "stars_k": "Repos to check for star bursts"}
FLAG_LABELS = {"no_round2": "Skip round 2", "no_stars_check": "Skip star burst check"}


def _verdict_projects() -> list[str]:
    try:
        return list(dict.fromkeys(v[0] for v in Index(default_path()).verdicts()))
    except (sqlite3.Error, OSError):  # Index only for autocomplete: broken index does not block search
        log.warning("Index projects unavailable", exc_info=True)
        return []


class SearchForm:
    """Form fields and their connection to state; values logic lives in `search_form`."""

    def __init__(self) -> None:
        self.fields: dict[str, ui.element] = {}
        self.command: ui.label | None = None
        self.drafts = {d.key: d for d in sf.list_drafts()}

    def state(self) -> dict:
        return {k: el.value for k, el in self.fields.items()}

    def fill(self, state: dict, *, validate: bool = True) -> None:
        for key, value in state.items():
            if key in self.fields:
                self.fields[key].value = value
        for el in self.fields.values():
            if validate and isinstance(el, ui.input):
                el.validate()
        self.refresh()

    def refresh(self) -> None:
        if self.command is not None:
            self.command.set_text("$ " + (sf.command_text(self.state()) or t(COMMAND_HINT)))

    def add(self, key: str, el: ui.element) -> ui.element:
        self.fields[key] = el
        el.on_value_change(self.refresh)
        return el

    def text(self, key: str, label: str, check: Callable[[str], str | None] | None = None, **kw) -> ui.input:
        el = layout.field(label, validation={"": lambda v: True} if check else None, **kw)
        if check:
            el.validation = lambda v: check(v or "")
        return self.add(key, el)  # type: ignore[return-value]

    def area(self, key: str, label: str, check: Callable[[str], str | None] | None = None, **kw) -> ui.input:
        return self.text(key, label, check, **kw).props("type=textarea autogrow rows=2")


def _load_draft(form: SearchForm, key: str) -> None:
    try:
        state = sf.load_draft(form.drafts[key])
    except (ValueError, OSError, tomllib.TOMLDecodeError):
        log.warning("Draft not loaded: %s", key, exc_info=True)
        ui.notify(t("Could not load the draft: the file is damaged or unreadable"), type="negative")
        return
    form.fill(state)


LLM_FAILED = "Draft failed: the model did not answer or sent an invalid answer. See the log."


async def _llm_draft(form: SearchForm, button: ui.button) -> None:
    """LLM draft fills form; does not start search. Errors without internal details."""
    need = (form.state().get("need") or "").strip()
    if not need:
        ui.notify(t("Describe what to find"), type="negative")
        return
    button.disable()
    try:
        d = await run.io_bound(llm.draft, need)
    except llm.LLMError as e:
        log.warning("LLM draft failed: %s", e)
        ui.notify(t(LLM_FAILED), type="negative")
        return
    finally:
        button.enable()
    form.fill(sf.draft_to_state(d, need))
    ui.notify(t("Draft ready. Check it, then launch the search."), type="positive")


def _need_row(form: SearchForm) -> None:
    form.area("need", t("What to search for (any language)"), hint=t("In your own words, without tool names"))
    button = layout.button(t("Draft from LLM"), icon="auto_awesome")
    button.on_click(lambda: _llm_draft(form, button))


def _fields(form: SearchForm) -> None:
    if llm.gui_enabled():
        _need_row(form)
    drafts = {k: d.label for k, d in form.drafts.items()}
    ui.select(drafts, label=t("Draft"), with_input=True, clearable=True,
              on_change=lambda e: e.value and _load_draft(form, e.value)) \
        .props(f'outlined dense stack-label hint="{t("From a past Run or eval dataset")}"').classes("w-full")
    form.area("task", t("Task (English)"), required=True, hint=t("1-3 sentences: what you need"))
    form.area("queries", t("Queries"), sf.check_queries, hint=t("One per line; 3-6 variants"))
    form.text("project", t("Project"), suggestions=sf.project_suggestions(_verdict_projects()))
    with layout.grid():
        form.text("lang", t("Language"), hint=t("For example python")).classes("ic-span-4")
        form.area("must", t("Required words"), lambda v: sf.check_regexes("--must", v),
                  hint=t("Regexes, one per line")).classes("ic-span-4")
        form.area("exclude", t("Excluded words"), lambda v: sf.check_regexes("--exclude", v),
                  hint=t("Regexes, one per line")).classes("ic-span-4")


def _advanced(form: SearchForm) -> None:
    defaults = sf.default_state()
    with ui.expansion(t("Advanced")).classes("w-full"):
        with layout.grid():
            for key, label in NUMBER_LABELS.items():
                form.add(key, ui.number(t(label), value=defaults[key]).props("outlined dense stack-label")
                         .classes("ic-span-4 w-full"))
            for key, label in FLAG_LABELS.items():
                form.add(key, ui.checkbox(t(label), value=defaults[key]).classes("ic-span-6"))


def _paste_dialog(form: SearchForm) -> ui.dialog:
    with ui.dialog() as dialog, layout.section_card():
        layout.heading(t("Paste command"), level=2)
        area = layout.field(t("Command"), hint=t("A repo-scout command")).props("type=textarea autogrow rows=3")
        error = ui.label().classes("ic-status--error")

        def apply() -> None:
            try:
                state = sf.params_to_state(cli.search_params(cli.parse_command(area.value or "")))
            except ValueError as e:
                error.set_text(str(e))
                return
            error.set_text("")
            form.fill(state)
            dialog.close()

        with layout.actions_row():
            layout.button(t("Cancel"), kind="quiet", on_click=dialog.close)
            layout.button(t("Apply"), kind="primary", on_click=apply)
    return dialog


def _start(form: SearchForm, started: dict[str, str]) -> None:
    state = form.state()
    for el in form.fields.values():
        if isinstance(el, ui.input):
            el.validate()
    if errors := sf.form_errors(state):
        ui.notify(errors[0], type="negative")
        return
    out = sf.out_path(state["task"], datetime.now())
    run_item = run_pool.submit(sf.run_argv(state, out), label=state["task"].strip(), meta={"out": str(out)})
    if run_item is None:
        ui.notify(t("Too many runs at once. Wait for one to finish."), type="warning")
        return
    started[run_item.run_id] = out.stem
    ui.notify(t("Search started"), type="positive")


def _watch_done(started: dict[str, str]) -> None:
    """ui.* only here in page timer: must not call from on_line."""
    for run_id, stem in list(started.items()):
        state = run_pool.RUNS.get(run_id)
        if state is None or state.status in run_pool.PENDING_STATUSES:
            continue
        started.pop(run_id)
        if state.status == run_pool.DONE:
            title = html.escape(state.label)
            ui.notify(t('Done: {title}. <a href="/runs/{stem}">Open run</a>').format(title=title, stem=stem),
                      type="positive", html=True, close_button=t("Close"), timeout=0)


def _buttons(form: SearchForm, started: dict[str, str]) -> None:
    paste = _paste_dialog(form)
    with layout.actions_row(end=False):
        layout.button(t("Launch"), kind="primary", icon="search", on_click=lambda: _start(form, started))

        def copy_prompt() -> None:
            ui.clipboard.write(sf.agent_prompt(form.state()["task"]))
            ui.notify(tr("copied"), type="positive")

        layout.button(t("Agent prompt"), icon="content_copy", on_click=copy_prompt)
        layout.button(t("Paste command"), kind="quiet", icon="content_paste", on_click=paste.open)


def search(draft: str | None = None) -> None:
    shell.shell("/")
    started: dict[str, str] = {}
    with layout.page_container(max_width=shell.PAGE_WIDTH):
        layout.heading(t("Search"), level=1)
        with ui.column().classes("w-full").style("gap: var(--ic-s4)"):
            form = SearchForm()
            with layout.section_card():
                _fields(form)
                _advanced(form)
            with layout.section_card(recessive=True):
                with ui.row().classes("ic-split w-full items-start justify-between no-wrap"):
                    form.command = ui.label().classes("t-mono").style("min-width: 0; overflow-wrap: anywhere")
                    ui.button(icon="content_copy", on_click=lambda: (
                        ui.clipboard.write((sf.command_text(form.state()) or "")), ui.notify(tr("copied")))) \
                        .props(f'flat round dense aria-label="{t("Copy")}"').classes("shrink-0") \
                        .tooltip(t("Copy"))
                _buttons(form, started)
            layout.heading(t("Runs"), level=2)
            run_monitor.attach_run_monitor(idle_text=t("No runs yet"))
            ui.timer(NOTIFY_PERIOD, lambda: _watch_done(started))
    if draft in form.drafts:
        form.fill(sf.load_draft(form.drafts[draft]))
    else:
        form.fill(sf.default_state(), validate=False)


def register() -> None:
    ui.page("/")(search)
