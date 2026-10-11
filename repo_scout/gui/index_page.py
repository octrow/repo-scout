"""Страница «Индекс» (`/index`): репо Индекса, Вердикты, переименование и «забыть»."""
import re

from nicegui import ui

from ..index import Index
from . import runs_logic as rl
from . import shell
from .kit import layout, table
from .verdict_dialog import DB_ERRORS, VerdictDialog, notify_db_error, open_index

REPO_RE = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", re.ASCII)
ALL_PROJECTS = "Все проекты"
COLUMNS = [
    {"name": "name", "label": "Репо", "field": "name", "align": "left", "sortable": True},
    {"name": "desc", "label": "Описание", "field": "desc", "align": "left"},
    {"name": "stars", "label": "★", "field": "stars", "align": "right", "sortable": True},
    {"name": "lang", "label": "Язык", "field": "lang", "align": "left"},
    {"name": "date", "label": "Добавлен", "field": "date", "align": "left", "sortable": True},
    {"name": "readme", "label": "README", "field": "readme", "align": "left"},
    {"name": "seen", "label": "Вердикты", "field": "seen", "align": "left"},
]


def check_repo(value: str) -> str | None:
    """Ошибка имени вида owner/repo или None."""
    v = (value or "").strip()
    if not REPO_RE.fullmatch(v) or v.split("/")[1] in (".", ".."):
        return "Нужен вид owner/repo"
    return None


def index_rows(idx: Index, *, project: str = "", kind: str = "", text: str = "") -> list[dict]:
    """Строки таблицы: репо Индекса под фильтры проекта, вида Вердикта и текста."""
    verdicts = idx.verdicts(project or None)
    prefix = rl.VERDICT_PREFIX.get(kind, "")
    allowed = {v[1] for v in verdicts if v[2].startswith(prefix)} if (project or prefix) else None
    all_rows = idx.rows()
    seen = idx.seen([r["name"] for r in all_rows])
    needle = text.strip().lower()
    out = []
    for r in all_rows:
        m = r["meta"]
        if allowed is not None and r["key"] not in allowed:
            continue
        if needle and needle not in f"{r['name']} {m.get('desc', '')} {m.get('lang', '')}".lower():
            continue
        out.append({"key": r["key"], "name": r["name"], "desc": (m.get("desc") or "")[:rl.DESC_LIMIT],
                    "stars": m.get("stars"), "lang": m.get("lang") or "—", "date": (r["fetched_at"] or "")[:10],
                    "readme": "есть" if r["has_readme"] else "нет", "seen": seen.get(r["key"], "—"),
                    "url": m.get("url") or f"https://github.com/{r['name']}"})
    return out


class IndexPage:
    def __init__(self) -> None:
        self.flt = {"project": "", "kind": "", "text": ""}
        self.rows: dict[str, dict] = {}
        self.verdicts = VerdictDialog(lambda _: self.refresh())
        self.panel, self.confirm = ui.dialog(), ui.dialog()
        self.table: table.EmptyAwareTable | None = None
        self.count: ui.label | None = None

    def refresh(self) -> None:
        try:
            with open_index() as idx:
                rows = index_rows(idx, **self.flt)
                total = len(idx.rows())
        except DB_ERRORS:
            notify_db_error("Не прочитан Индекс для страницы «Индекс»")
            return
        self.rows = {r["key"]: r for r in rows}
        self.table.set_rows(rows)  # type: ignore[union-attr]
        self.count.set_text(f"Показано {len(rows)} из {total}")  # type: ignore[union-attr]

    def set_filter(self, key: str, value: str | None) -> None:
        self.flt[key] = value or ""
        if key == "project" and value == ALL_PROJECTS:
            self.flt[key] = ""
        self.refresh()

    def filters(self) -> None:
        with open_index() as idx:
            projects = list(dict.fromkeys(v[0] for v in idx.verdicts()))
        with layout.filter_bar():
            layout.search_field("Поиск по репо и описанию", on_change=lambda e: self.set_filter("text", e.value))
            ui.select([ALL_PROJECTS, *projects], value=ALL_PROJECTS,
                      on_change=lambda e: self.set_filter("project", e.value)).props('outlined dense aria-label="Проект"')
            ui.select(rl.verdict_filter_options(), value="",
                      on_change=lambda e: self.set_filter("kind", e.value)).props('outlined dense aria-label="Вердикт"')
            ui.space()
            self.count = ui.label().classes("t-meta")

    def open_panel(self, key: str) -> None:
        row = self.rows[key]
        self.panel.clear()
        with self.panel, layout.section_card():
            layout.heading(row["name"], level=2)
            ui.link("Открыть на GitHub", row["url"], new_tab=True)
            ui.label(row["desc"]).classes("t-meta")
            ui.label(f"Вердикты: {row['seen']}")
            with open_index() as idx:
                readme = idx.readme(row["name"])
            if readme:
                layout.markdown_reader(readme, max_height="60vh")
            else:
                ui.label("README нет в Индексе").classes("t-meta")
            with layout.actions_row():
                layout.button("Закрыть", kind="quiet", on_click=self.panel.close)
                layout.button("Переименовать", icon="edit", on_click=lambda: self.rename_dialog(row["name"]))
                layout.button("Забыть", kind="danger", on_click=lambda: self.forget_dialog(row["name"]))
                layout.button("Поставить вердикт", kind="primary", icon="rate_review",
                              on_click=lambda: self.verdicts.open(row["name"]))
        self.panel.open()

    def rename_dialog(self, name: str) -> None:
        self.confirm.clear()
        with self.confirm, layout.section_card():
            layout.heading("Переименовать репо", level=2)
            ui.label("Старая запись уйдёт из Индекса, Вердикты переедут на новое имя.").classes("t-meta")
            new = layout.field("Новое имя", value=name, hint="owner/repo", validation={
                "Нужен вид owner/repo": lambda v: check_repo(v) is None})

            def apply() -> None:
                if not new.validate():
                    return
                try:
                    with open_index() as idx:
                        idx.rename(name, new.value.strip())
                except DB_ERRORS:
                    notify_db_error(f"Не переименовано: {name}")
                    return
                self.confirm.close()
                self.panel.close()
                ui.notify(f"Переименовано: {new.value.strip()}", type="positive")
                self.refresh()

            with layout.actions_row():
                layout.button("Отмена", kind="quiet", on_click=self.confirm.close)
                layout.button("Переименовать", kind="primary", on_click=apply)
        self.confirm.open()

    def forget_dialog(self, name: str) -> None:
        self.confirm.clear()
        with self.confirm, layout.section_card():
            layout.heading("Забыть репо?", level=2)
            ui.label(f"{name} уйдёт из поиска по Индексу. Вердикты останутся.").classes("t-meta")

            def forget() -> None:
                try:
                    with open_index() as idx:
                        idx.forget(name)
                except DB_ERRORS:
                    notify_db_error(f"Не удалено из Индекса: {name}")
                    return
                self.confirm.close()
                self.panel.close()
                self.refresh()

            with layout.actions_row():
                layout.button("Отмена", kind="quiet", on_click=self.confirm.close)
                layout.button("Забыть", kind="danger", on_click=forget)
        self.confirm.open()

    def build(self) -> None:
        self.filters()
        self.table = table.empty_aware_table(COLUMNS, row_key="key", pagination={"rowsPerPage": 25},
                                             empty_text="В Индексе пока нет репо: они появляются после поиска.")
        self.table.table.on("rowClick", lambda e: self.open_panel(e.args[1]["key"]))
        self.refresh()


def index_page() -> None:
    shell.shell("/index", layout.PAGE_MAX_WIDTH_WIDE)
    with layout.page_container(max_width=layout.PAGE_MAX_WIDTH_WIDE):
        layout.heading("Индекс", level=1)
        IndexPage().build()


def register() -> None:
    ui.page("/index")(index_page)
