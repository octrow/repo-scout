"""Single Run page `/runs/{id}`: parameters, filters, table, detail panel, Verdicts."""

from nicegui import ui

from .. import runs
from . import runs_logic as rl
from . import shell
from .i18n import t
from .kit import layout, table
from .verdict_dialog import DB_ERRORS, VerdictDialog, notify_db_error, open_index, readme_view

# Fits the window, no sideways scroll: related fields share a column (second line), and
# priority 2/3 columns hide as the table narrows; the repo panel shows every field
COLUMNS = [
    {"name": "repo", "label": "Repo", "field": "repo", "align": "left", "sortable": True, "sub": "desc"},
    {"name": "close", "label": "Closeness", "field": "close", "align": "right", "sortable": True,
     "hint": "README closeness to the task, 0-1"},
    {"name": "fit", "label": "Fit", "field": "fit", "align": "right", "sortable": True},  # advanced mode only
    {"name": "score", "label": "Score", "field": "score_n", "align": "right", "sortable": True,
     "hint": "Score: f = freshness, p = popularity", "priority": 2},
    {"name": "stars", "label": "★", "field": "stars", "align": "right", "sortable": True, "sub": "activity"},
    {"name": "pushed", "label": "Pushed, d", "field": "pushed", "align": "right", "sortable": True,
     "hint": "Days since the last push; below: created", "sub": "created", "priority": 2},
    {"name": "flags", "label": "Flags / drop", "field": "flags", "align": "left", "priority": 2},
    {"name": "seen", "label": "Seen", "field": "seen", "align": "left", "priority": 2},
    {"name": "source", "label": "Source", "field": "source", "align": "left", "sortable": True, "priority": 3},
    {"name": "lang", "label": "Language", "field": "lang", "align": "left", "priority": 3},
]
# Kit theme lets every cell wrap; here every row is short, free text is cut with
# an ellipsis (full text in the tooltip and the detail panel)
TABLE_CSS = """
.rs-run-table .q-table td { white-space: nowrap; }
.rs-clamp, .rs-repo { display: block; max-width: min(var(--ic-cell-max), var(--ic-cell-share));
  overflow: hidden; text-overflow: ellipsis; }
.rs-run-table tbody tr { cursor: pointer; }
.rs-repo { font-weight: var(--ic-fw-semibold); color: var(--ic-accent-700); }
tr:hover .rs-repo { text-decoration: underline; }
"""
HEADER_SLOT = ('<q-th :props="props">{{ props.col.label }}'
               '<q-tooltip v-if="props.col.hint">{{ props.col.hint }}</q-tooltip></q-th>')
SCORE_SLOT = ('<q-td :props="props"><b>{{ props.row.score_n }}</b> '
              '<span class="t-meta">{{ props.row.score_parts }}</span>'
              '<q-tooltip>{{ props.row.score }}</q-tooltip></q-td>')
FLAGS_SLOT = ('<q-td :props="props"><span v-for="f in props.row.flag_list" :key="f" '
              'class="ic-chip ic-chip--neutral q-mr-xs">{{ f }}</span>'
              '<span v-if="!props.row.flag_list.length">—</span></q-td>')
CLAMP_SLOT = '<q-td :props="props"><div class="rs-clamp" :title="props.value">{{ props.value }}</div></q-td>'
REPO_SLOT = ('<q-td :props="props"><span class="rs-repo">{{ props.value }}</span>'
             '<div class="ic-cell-sub" :title="props.row.desc">{{ props.row.desc }}</div></q-td>')
METRICS = (("Closeness", "close"), ("Source", "source"), ("Score", "score"), ("★", "stars"), ("Forks", "forks"),
           ("Commits", "commits"), ("Pushed, days ago", "pushed"), ("Created", "created"), ("Language", "lang"))


def _labeled(options: list[str]) -> dict[str, str]:
    """Select options: the "All ..." choices are translated, data values (sources, flags) stay as they are."""
    return {o: t(o) if o in (rl.SOURCES_ALL, rl.FLAGS_ALL) else o for o in options}


def _params_line(params: dict) -> str:
    parts = [t("project: {name}").format(name=params["project"])] if params.get("project") else []
    parts.append(t("queries: {n}").format(n=len(params.get("queries", []))))
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

    def columns(self) -> list[dict]:
        """Fit only in advanced mode, Seen only once some repo has a verdict."""
        hidden = {name for name, key in (("fit", "fit"), ("seen", "seen")) if not any(r.get(key) for r in self.rows)}
        return [{**c, "label": t(c["label"]), **({"hint": t(c["hint"])} if "hint" in c else {})}
                for c in COLUMNS if c["name"] not in hidden]

    def refresh(self) -> None:
        shown = self.visible()
        self.table.set_columns(self.columns())  # type: ignore[union-attr]
        self.table.set_rows([rl.table_row(r) for r in shown])  # type: ignore[union-attr]
        self.count.set_text(t("Showing {shown} of {total}").format(shown=len(shown), total=len(self.rows)))  # type: ignore[union-attr]

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
        with layout.filter_bar() as self.bar:
            layout.search_field(t("Search by repo and description"), on_change=lambda e: self.set_filter("text", e.value))
            ui.select(_labeled(rl.source_options(self.rows)), value=rl.SOURCES_ALL,
                      on_change=lambda e: self.set_filter("source", e.value)) \
                .props(f'outlined dense aria-label="{t("Source")}"')
            ui.select(_labeled(rl.flag_options(self.rows)), value=rl.FLAGS_ALL,
                      on_change=lambda e: self.set_filter("flag", e.value)).props(f'outlined dense aria-label="{t("Flag")}"')
            ui.switch(t("Show dropped"), on_change=lambda e: self.set_filter("stopped", e.value))
            ui.space()
            self.count = ui.label().classes("t-meta")

    def open_panel(self, repo: str) -> None:
        row = self.by_repo[repo]
        self.panel.clear()
        cells = rl.table_row(row)
        with self.panel, layout.section_card().style(shell.PANEL_STYLE):
            with ui.row().classes("ic-split w-full items-start flex-nowrap"):
                layout.heading(repo, level=2).classes("min-w-0")
                ui.button(icon="close", on_click=self.panel.close) \
                    .props(f'flat round dense aria-label="{t("Close")}"').classes("shrink-0")
            ui.link(t("Open on GitHub"), row.get("url", ""), new_tab=True)
            ui.label(cells["desc"]).classes("t-meta")
            with ui.row().classes("items-center gap-2"):
                for label, key in METRICS:
                    ui.label(f"{t(label)}: {cells[key]}").classes("ic-chip ic-chip--neutral")
            ui.label(t("Flags and drop: {flags}").format(flags=cells["flags"]))
            ui.label(t("Already seen: {seen}").format(seen=cells["seen"]))
            ui.separator()
            readme_view(repo)
            with layout.actions_row():
                layout.button(t("Close"), kind="quiet", on_click=self.panel.close)
                ui.space()
                for kind, label in rl.VERDICT_KINDS.items():
                    layout.button(t(label), on_click=lambda k=kind: self.verdicts.open(
                        repo, self.params.get("project") or "", self.params.get("task") or "", kind=k))
        self.panel.open()

    def build(self) -> None:
        ui.add_css(TABLE_CSS)
        with ui.row().classes("ic-split w-full items-start sm:flex-nowrap"):
            layout.heading(self.params.get("task") or self.stem, level=1).classes("min-w-0")
            layout.button(t("Rerun as draft"), icon="replay",
                          on_click=lambda: ui.navigate.to(f"/?draft=run:{self.stem}")).classes("shrink-0")
        ui.label(_params_line(self.params)).classes("t-meta")
        if self.data.get("round2_topics"):
            with ui.row().classes("items-center gap-1"):
                ui.label(t("Round 2:")).classes("t-meta")
                for topic in self.data["round2_topics"]:
                    ui.label(topic).classes("ic-chip ic-chip--neutral")
        self.filters()
        self.table = table.empty_aware_table(self.columns(), row_key="repo", pagination={"rowsPerPage": 25},
                                             empty_text=t("No rows match these filters."))
        self.table.table.classes("rs-run-table").props("flat dense")
        self.table.table.add_slot("header-cell", HEADER_SLOT)
        self.table.table.add_slot("body-cell-score", SCORE_SLOT)
        self.table.table.add_slot("body-cell-repo", REPO_SLOT)
        self.table.table.add_slot("body-cell-flags", FLAGS_SLOT)
        self.table.table.add_slot("body-cell-seen", CLAMP_SLOT)
        with self.bar:
            self.table.column_picker("repo-scout-run-columns")
        self.table.table.on("rowClick", lambda e: self.open_panel(e.args[1]["repo"]))
        self.refresh()


def run_page(run_id: str) -> None:
    shell.shell("/runs")
    with layout.page_container(max_width=shell.PAGE_WIDTH):
        path = rl.resolve_run(run_id)
        try:
            data = runs.load(path) if path else None
        except (ValueError, OSError):
            data = None
        if data is None:
            layout.failed(t("Run not found or unreadable"))
            layout.button(t("Back to runs"), kind="quiet", on_click=lambda: ui.navigate.to("/runs"))
            return
        RunView(run_id, data).build()
