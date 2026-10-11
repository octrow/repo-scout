"""Страница «Поиск» (`/`): форма, команда, запуск подпроцессом с живым логом."""
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
from .kit import layout, run_monitor, run_pool

NOTIFY_PERIOD = 1.0
COMMAND_HINT = "Заполните задачу и запросы: команда появится здесь"
NUMBER_LABELS = {"months": "Месяцев с последнего push (0 — без фильтра)", "new_days": "Флаг «новый»: младше, дней",
                 "limit": "Результатов на запрос", "min_closeness": "Порог Близости",
                 "from_index": "Ближайших из Индекса", "round2_k": "Тем для второго круга",
                 "stars_k": "Репо для проверки звёзд"}
FLAG_LABELS = {"no_round2": "Без второго круга", "no_stars_check": "Без проверки всплеска звёзд"}


def _verdict_projects() -> list[str]:
    try:
        return list(dict.fromkeys(v[0] for v in Index(default_path()).verdicts()))
    except (sqlite3.Error, OSError):  # Индекс только для подсказок: сломанный не мешает искать
        log.warning("Проекты из Индекса недоступны", exc_info=True)
        return []


class SearchForm:
    """Поля формы и их связь с состоянием; логика значений живёт в `search_form`."""

    def __init__(self) -> None:
        self.fields: dict[str, ui.element] = {}
        self.command: ui.label | None = None  # создаётся на странице, где ему место
        self.drafts = {d.key: d for d in sf.list_drafts()}

    def state(self) -> dict:
        return {k: el.value for k, el in self.fields.items()}

    def fill(self, state: dict, *, validate: bool = True) -> None:
        for key, value in state.items():
            if key in self.fields:  # поле Потребности есть только при ключе LLM
                self.fields[key].value = value
        for el in self.fields.values():
            if validate and isinstance(el, ui.input):
                el.validate()
        self.refresh()

    def refresh(self) -> None:
        if self.command is not None:
            self.command.set_text("$ " + (sf.command_text(self.state()) or COMMAND_HINT))

    def add(self, key: str, el: ui.element) -> ui.element:
        self.fields[key] = el
        el.on_value_change(self.refresh)
        return el

    def text(self, key: str, label: str, check: Callable[[str], str | None] | None = None, **kw) -> ui.input:
        # validation: callable, возвращающий текст ошибки; field() подключает проверку при blur
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
        log.warning("Черновик не загружен: %s", key, exc_info=True)
        ui.notify("Не удалось загрузить черновик: файл повреждён или недоступен", type="negative")
        return
    form.fill(state)


LLM_FAILED = "Черновик не получен: модель не ответила или ответ не прошёл проверку. Подробности в логе."


async def _llm_draft(form: SearchForm, button: ui.button) -> None:
    """Черновик из LLM заполняет форму; поиск не запускает. Ошибки без внутренних подробностей."""
    need = (form.state().get("need") or "").strip()
    if not need:
        ui.notify("Опишите, что ищем", type="negative")
        return
    button.disable()
    try:
        d = await run.io_bound(llm.draft, need)
    except llm.LLMError as e:
        log.warning("Черновик LLM не получен: %s", e)
        ui.notify(LLM_FAILED, type="negative")
        return
    finally:
        button.enable()
    form.fill(sf.draft_to_state(d, need))
    ui.notify("Черновик заполнен: проверьте и запустите поиск", type="positive")


def _need_row(form: SearchForm) -> None:
    form.area("need", "Что ищем (любым языком)", hint="Своими словами, без названий готовых решений")
    button = layout.button("Черновик из LLM", icon="auto_awesome")
    button.on_click(lambda: _llm_draft(form, button))


def _fields(form: SearchForm) -> None:
    if llm.available():
        _need_row(form)
    drafts = {k: d.label for k, d in form.drafts.items()}
    ui.select(drafts, label="Черновик", with_input=True, clearable=True,
              on_change=lambda e: e.value and _load_draft(form, e.value)) \
        .props('outlined dense stack-label hint="Из прошлого Прогона или набора eval"').classes("w-full")
    form.area("task", "Задача (англ.)", required=True, hint="1-3 фразы: что нужно найти")
    form.area("queries", "Запросы", sf.check_queries, hint="По одному на строку; 3-6 вариантов")
    form.text("project", "Проект", suggestions=sf.project_suggestions(_verdict_projects()))
    with layout.grid():
        form.text("lang", "Язык", hint="Например python").classes("ic-span-4")
        form.area("must", "Обязательные слова", lambda v: sf.check_regexes("--must", v),
                  hint="Регулярки, по одной на строку").classes("ic-span-4")
        form.area("exclude", "Запрещённые слова", lambda v: sf.check_regexes("--exclude", v),
                  hint="Регулярки, по одной на строку").classes("ic-span-4")


def _advanced(form: SearchForm) -> None:
    defaults = sf.default_state()
    with ui.expansion("Дополнительно").classes("w-full"):
        with layout.grid():
            for key, label in NUMBER_LABELS.items():
                form.add(key, ui.number(label, value=defaults[key]).props("outlined dense stack-label")
                         .classes("ic-span-4 w-full"))
            for key, label in FLAG_LABELS.items():
                form.add(key, ui.checkbox(label, value=defaults[key]).classes("ic-span-6"))


def _paste_dialog(form: SearchForm) -> ui.dialog:
    with ui.dialog() as dialog, layout.section_card():
        layout.heading("Вставить команду", level=2)
        area = layout.field("Команда", hint="Строка repo-scout …").props("type=textarea autogrow rows=3")
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
            layout.button("Отмена", kind="quiet", on_click=dialog.close)
            layout.button("Применить", kind="primary", on_click=apply)
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
    run = run_pool.submit(sf.run_argv(state, out), label=state["task"].strip(), meta={"out": str(out)})
    if run is None:
        ui.notify("Очередь запусков переполнена: дождитесь завершения", type="warning")
        return
    started[run.run_id] = out.stem
    ui.notify("Поиск запущен", type="positive")


def _watch_done(started: dict[str, str]) -> None:
    """ui.* только здесь, в таймере страницы: из on_line вызывать нельзя."""
    for run_id, stem in list(started.items()):
        state = run_pool.RUNS.get(run_id)
        if state is None or state.status in run_pool.PENDING_STATUSES:
            continue
        started.pop(run_id)
        if state.status == run_pool.DONE:
            title = html.escape(state.label)
            ui.notify(f'Готово: {title}. <a href="/runs/{stem}">Открыть прогон</a>', type="positive",
                      html=True, close_button="Закрыть", timeout=0)


def _buttons(form: SearchForm, started: dict[str, str]) -> None:
    paste = _paste_dialog(form)
    with layout.actions_row(end=False):
        layout.button("Запустить", kind="primary", icon="search", on_click=lambda: _start(form, started))

        def copy_prompt() -> None:
            ui.clipboard.write(sf.agent_prompt(form.state()["task"]))
            ui.notify(layout.COPIED_TEXT, type="positive")

        layout.button("Промпт для агента", icon="content_copy", on_click=copy_prompt)
        layout.button("Вставить команду", kind="quiet", icon="content_paste", on_click=paste.open)


def search(draft: str | None = None) -> None:
    shell.shell("/", layout.PAGE_MAX_WIDTH_FORM)
    started: dict[str, str] = {}
    with layout.page_container():
        layout.heading("Поиск", level=1)
        with ui.column().classes("w-full").style("gap: var(--ic-s4)"):
            form = SearchForm()
            with layout.section_card():
                _fields(form)
                _advanced(form)
            with layout.section_card(recessive=True):
                with ui.row().classes("ic-split w-full items-start justify-between no-wrap"):
                    form.command = ui.label().classes("t-mono").style("min-width: 0; overflow-wrap: anywhere")
                    layout.button("Копировать", kind="quiet", icon="content_copy", on_click=lambda: (
                        ui.clipboard.write((sf.command_text(form.state()) or "")), ui.notify(layout.COPIED_TEXT)))
                _buttons(form, started)
            layout.heading("Запуски", level=2)
            run_monitor.attach_run_monitor(idle_text="Запусков пока не было")
            ui.timer(NOTIFY_PERIOD, lambda: _watch_done(started))
    if draft in form.drafts:
        form.fill(sf.load_draft(form.drafts[draft]))
    else:
        form.fill(sf.default_state(), validate=False)


def register() -> None:
    ui.page("/")(search)
