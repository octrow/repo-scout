"""Страница одного Прогона `/runs/{id}`: параметры, фильтры, таблица, панель строки, Вердикты."""

from nicegui import ui

from .. import runs
from ..log import log
from . import runs_logic as rl
from . import shell
from .kit import layout, table
from .verdict_dialog import DB_ERRORS, VerdictDialog, notify_db_error, open_index

COLUMNS = [
    {"name": "close", "label": "Близость", "field": "close", "align": "right", "sortable": True},
    {"name": "source", "label": "Источник", "field": "source", "align": "left", "sortable": True},
    {"name": "score", "label": "Баллы", "field": "score", "align": "left"},
    {"name": "repo", "label": "Репо", "field": "repo", "align": "left", "sortable": True},
    {"name": "stars", "label": "★", "field": "stars", "align": "right", "sortable": True},
    {"name": "forks", "label": "Forks", "field": "forks", "align": "right", "sortable": True},
    {"name": "commits", "label": "Коммитов", "field": "commits", "align": "right", "sortable": True},
    {"name": "pushed", "label": "Push, дн", "field": "pushed", "align": "right", "sortable": True},
    {"name": "created", "label": "Создан", "field": "created", "align": "left", "sortable": True},
    {"name": "lang", "label": "Язык", "field": "lang", "align": "left"},
    {"name": "flags", "label": "Флаги / отсев", "field": "flags", "align": "left"},
    {"name": "seen", "label": "Уже смотрели", "field": "seen", "align": "left"},
    {"name": "desc", "label": "Описание", "field": "desc", "align": "left"},
]
METRICS = (("Близость", "close"), ("Источник", "source"), ("Баллы", "score"), ("★", "stars"), ("Forks", "forks"),
           ("Коммитов", "commits"), ("Push, дней назад", "pushed"), ("Создан", "created"), ("Язык", "lang"))


def _params_line(params: dict) -> str:
    parts = [f"проект: {params['project']}"] if params.get("project") else []
    parts.append(f"запросов: {len(params.get('queries', []))}")
    return " · ".join(parts)


class RunView:
    def __init__(self, stem: str, data: dict) -> None:
        self.stem, self.data = stem, data
        self.params = data["params"]
        self.rows = rl.sorted_rows(data["rows"])
        self.by_repo = {r.get("repo", "?"): r for r in self.rows}
        self.flt = {"text": "", "source": rl.SOURCES_ALL, "flag": rl.FLAGS_ALL, "stopped": False}
        self.verdicts = VerdictDialog(self.on_saved)
        self.panel = ui.dialog()
        self.table: table.EmptyAwareTable | None = None
        self.count: ui.label | None = None

    def visible(self) -> list[dict]:
        return rl.filter_rows(self.rows, text=self.flt["text"], source=self.flt["source"],
                              flag=self.flt["flag"], show_stopped=self.flt["stopped"])

    def refresh(self) -> None:
        shown = self.visible()
        self.table.set_rows([rl.table_row(r) for r in shown])  # type: ignore[union-attr]
        self.count.set_text(f"Показано {len(shown)} из {len(self.rows)}")  # type: ignore[union-attr]

    def set_filter(self, key: str, value: str | bool | None) -> None:
        self.flt[key] = value if key == "stopped" else (value or "")
        if key in ("source", "flag") and not value:
            self.flt[key] = rl.SOURCES_ALL if key == "source" else rl.FLAGS_ALL
        self.refresh()

    def on_saved(self, repo: str) -> None:
        """«Уже смотрели» обновляется на месте, без перезагрузки страницы."""
        try:
            with open_index() as idx:
                self.by_repo[repo]["seen"] = idx.seen([repo]).get(repo.lower(), "")
        except DB_ERRORS:
            notify_db_error(f"Не обновлено «Уже смотрели»: {repo}")
        self.refresh()
        self.open_panel(repo)

    def filters(self) -> None:
        with layout.filter_bar():
            layout.search_field("Поиск по репо и описанию", on_change=lambda e: self.set_filter("text", e.value))
            ui.select(rl.source_options(self.rows), value=rl.SOURCES_ALL,
                      on_change=lambda e: self.set_filter("source", e.value)).props('outlined dense aria-label="Источник"')
            ui.select(rl.flag_options(self.rows), value=rl.FLAGS_ALL,
                      on_change=lambda e: self.set_filter("flag", e.value)).props('outlined dense aria-label="Флаг"')
            ui.switch("Показать отсеянные", on_change=lambda e: self.set_filter("stopped", e.value))
            ui.space()
            self.count = ui.label().classes("t-meta")

    def open_panel(self, repo: str) -> None:
        row = self.by_repo[repo]
        self.panel.clear()
        t = rl.table_row(row)
        with self.panel, layout.section_card():
            layout.heading(repo, level=2)
            ui.link("Открыть на GitHub", row.get("url", ""), new_tab=True)
            ui.label(t["desc"]).classes("t-meta")
            with layout.grid(min_col="10rem"):
                for label, key in METRICS:
                    with ui.column().classes("ic-stack"):
                        ui.label(label).classes("t-meta")
                        ui.label(str(t[key]))
            ui.label(f"Флаги и отсев: {t['flags']}")
            ui.label(f"Уже смотрели: {t['seen']}")
            self._readme(repo)
            with layout.actions_row():
                layout.button("Закрыть", kind="quiet", on_click=self.panel.close)
                layout.button("Поставить вердикт", kind="primary", icon="rate_review",
                              on_click=lambda: self.verdicts.open(repo, self.params.get("project") or "",
                                                                  self.params.get("task") or ""))
        self.panel.open()

    @staticmethod
    def _readme(repo: str) -> None:
        try:
            with open_index() as idx:
                readme = idx.readme(repo)
        except DB_ERRORS:
            log.warning("README из Индекса не прочитан: %s", repo, exc_info=True)
            readme = None
        if readme:
            layout.markdown_reader(readme, max_height="60vh")
        else:
            ui.label("README нет в Индексе: смотрите на GitHub").classes("t-meta")

    def build(self) -> None:
        with ui.row().classes("ic-split w-full items-center justify-between"):
            layout.heading(self.params.get("task") or self.stem, level=1)
            layout.button("Повторить как черновик", icon="replay", on_click=lambda: ui.navigate.to(f"/?draft=run:{self.stem}"))
        ui.label(_params_line(self.params)).classes("t-meta")
        if self.data.get("round2_topics"):
            ui.label("Второй круг: " + ", ".join(self.data.get("round2_topics"))).classes("t-meta")
        self.filters()
        self.table = table.empty_aware_table(COLUMNS, row_key="repo", pagination={"rowsPerPage": 25},
                                             empty_text="Под эти фильтры строк нет.")
        self.table.table.on("rowClick", lambda e: self.open_panel(e.args[1]["repo"]))
        self.refresh()


def run_page(run_id: str) -> None:
    shell.shell("/runs", layout.PAGE_MAX_WIDTH_WIDE)
    with layout.page_container(max_width=layout.PAGE_MAX_WIDTH_WIDE):
        path = rl.resolve_run(run_id)
        try:
            data = runs.load(path) if path else None
        except (ValueError, OSError):
            data = None
        if data is None:
            layout.failed("Прогон не найден или файл повреждён")
            layout.button("К списку прогонов", kind="quiet", on_click=lambda: ui.navigate.to("/runs"))
            return
        RunView(run_id, data).build()
