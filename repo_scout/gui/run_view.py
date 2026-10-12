"""Single Run page `/runs/{id}`: parameters, filters, table, detail panel, Verdicts."""

from nicegui import ui

from .. import runs
from ..log import log
from . import runs_logic as rl
from . import shell
from .kit import layout, table
from .verdict_dialog import DB_ERRORS, VerdictDialog, notify_db_error, open_index

COLUMNS = [
    {"name": "close", "label": "Closeness", "field": "close", "align": "right", "sortable": True},
    {"name": "source", "label": "Source", "field": "source", "align": "left", "sortable": True},
    {"name": "score", "label": "Score", "field": "score", "align": "left"},
    {"name": "repo", "label": "Repo", "field": "repo", "align": "left", "sortable": True},
    {"name": "stars", "label": "★", "field": "stars", "align": "right", "sortable": True},
    {"name": "forks", "label": "Forks", "field": "forks", "align": "right", "sortable": True},
    {"name": "commits", "label": "Commits", "field": "commits", "align": "right", "sortable": True},
    {"name": "pushed", "label": "Pushed, d", "field": "pushed", "align": "right", "sortable": True},
    {"name": "created", "label": "Created", "field": "created", "align": "left", "sortable": True},
    {"name": "lang", "label": "Language", "field": "lang", "align": "left"},
    {"name": "flags", "label": "Flags / drop", "field": "flags", "align": "left"},
    {"name": "seen", "label": "Seen", "field": "seen", "align": "left"},
    {"name": "desc", "label": "Description", "field": "desc", "align": "left"},
]
METRICS = (("Closeness", "close"), ("Source", "source"), ("Score", "score"), ("★", "stars"), ("Forks", "forks"),
           ("Commits", "commits"), ("Pushed, days ago", "pushed"), ("Created", "created"), ("Language", "lang"))


def _params_line(params: dict) -> str:
    parts = [f"project: {params['project']}"] if params.get("project") else []
    parts.append(f"queries: {len(params.get('queries', []))}")
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
        self.count.set_text(f"Showing {len(shown)} of {len(self.rows)}")  # type: ignore[union-attr]

    def set_filter(self, key: str, value: str | bool | None) -> None:
        self.flt[key] = value if key == "stopped" else (value or "")
        if key in ("source", "flag") and not value:
            self.flt[key] = rl.SOURCES_ALL if key == "source" else rl.FLAGS_ALL
        self.refresh()

    def on_saved(self, repo: str) -> None:
        """'Seen' updates in place without reloading the page."""
        try:
            with open_index() as idx:
                self.by_repo[repo]["seen"] = idx.seen([repo]).get(repo.lower(), "")
        except DB_ERRORS:
            notify_db_error(f"Failed to update 'Seen': {repo}")
        self.refresh()
        self.open_panel(repo)

    def filters(self) -> None:
        with layout.filter_bar():
            layout.search_field("Search by repo and description", on_change=lambda e: self.set_filter("text", e.value))
            ui.select(rl.source_options(self.rows), value=rl.SOURCES_ALL,
                      on_change=lambda e: self.set_filter("source", e.value)).props('outlined dense aria-label="Source"')
            ui.select(rl.flag_options(self.rows), value=rl.FLAGS_ALL,
                      on_change=lambda e: self.set_filter("flag", e.value)).props('outlined dense aria-label="Flag"')
            ui.switch("Show dropped", on_change=lambda e: self.set_filter("stopped", e.value))
            ui.space()
            self.count = ui.label().classes("t-meta")

    def open_panel(self, repo: str) -> None:
        row = self.by_repo[repo]
        self.panel.clear()
        t = rl.table_row(row)
        with self.panel, layout.section_card():
            layout.heading(repo, level=2)
            ui.link("Open on GitHub", row.get("url", ""), new_tab=True)
            ui.label(t["desc"]).classes("t-meta")
            with layout.grid(min_col="10rem"):
                for label, key in METRICS:
                    with ui.column().classes("ic-stack"):
                        ui.label(label).classes("t-meta")
                        ui.label(str(t[key]))
            ui.label(f"Flags and drop: {t['flags']}")
            ui.label(f"Already seen: {t['seen']}")
            self._readme(repo)
            with layout.actions_row():
                layout.button("Close", kind="quiet", on_click=self.panel.close)
                layout.button("Set verdict", kind="primary", icon="rate_review",
                              on_click=lambda: self.verdicts.open(repo, self.params.get("project") or "",
                                                                  self.params.get("task") or ""))
        self.panel.open()

    @staticmethod
    def _readme(repo: str) -> None:
        try:
            with open_index() as idx:
                readme = idx.readme(repo)
        except DB_ERRORS:
            log.warning("README from Index could not be read: %s", repo, exc_info=True)
            readme = None
        if readme:
            layout.markdown_reader(readme, max_height="60vh")
        else:
            ui.label("No README in Index: check on GitHub").classes("t-meta")

    def build(self) -> None:
        with ui.row().classes("ic-split w-full items-center justify-between"):
            layout.heading(self.params.get("task") or self.stem, level=1)
            layout.button("Rerun as draft", icon="replay", on_click=lambda: ui.navigate.to(f"/?draft=run:{self.stem}"))
        ui.label(_params_line(self.params)).classes("t-meta")
        if self.data.get("round2_topics"):
            ui.label("Round 2: " + ", ".join(self.data.get("round2_topics"))).classes("t-meta")
        self.filters()
        self.table = table.empty_aware_table(COLUMNS, row_key="repo", pagination={"rowsPerPage": 25},
                                             empty_text="No rows match these filters.")
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
            layout.failed("Run not found or file is corrupt")
            layout.button("Back to runs", kind="quiet", on_click=lambda: ui.navigate.to("/runs"))
            return
        RunView(run_id, data).build()
