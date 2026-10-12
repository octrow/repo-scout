"""Runs pages: list `/runs` and single Run `/runs/{id}`."""
from nicegui import ui

from .. import runs
from . import shell
from .kit import layout, table
from .run_view import run_page
from .runs_logic import resolve_run

COLUMNS = [
    {"name": "date", "label": "Date", "field": "date", "align": "left", "sortable": True},
    {"name": "task", "label": "Task", "field": "task", "align": "left"},
    {"name": "project", "label": "Project", "field": "project", "align": "left", "sortable": True},
    {"name": "count", "label": "Kept / total", "field": "count", "align": "right"},
    {"name": "actions", "label": "", "field": "id", "align": "right"},
]
TASK_SLOT = """<q-td :props="props">
<a v-if="!props.row.error" :href="'/runs/' + props.row.id">{{ props.row.task }}</a>
<span v-else class="ic-status--error">{{ props.row.task }}</span></q-td>"""
DELETE_SLOT = """<q-td :props="props"><q-btn outline dense no-caps color="negative" label="Delete"
@click="() => $parent.$emit('delete', props.row)" /></q-td>"""


def summary_row(s: runs.Summary) -> dict:
    if s.error:
        return {"id": s.path.stem, "date": "", "task": f"File corrupt: {s.path.name}", "project": "",
                "count": "", "error": True}
    return {"id": s.path.stem, "date": (s.created_at or "")[:16].replace("T", " "), "task": s.task or s.path.stem,
                "project": s.project or "—", "count": f"{s.n_kept} / {s.n_total}", "error": False}


class RunsList:
    def __init__(self) -> None:
        self.table: table.EmptyAwareTable | None = None
        self.dialog = ui.dialog()

    def refresh(self) -> None:
        self.table.set_rows([summary_row(s) for s in runs.list_runs()])  # type: ignore[union-attr]

    def confirm_delete(self, row: dict) -> None:
        self.dialog.clear()
        with self.dialog, layout.section_card():
            layout.heading("Delete run?", level=2)
            ui.label(f"{row['task']}: the file will be deleted permanently.").classes("t-meta")

            def delete() -> None:
                try:
                    path = resolve_run(str(row.get("id", "")))
                    if path is not None:
                        runs.delete(path)
                except OSError as e:
                    ui.notify(f"Failed to delete: {e.strerror or e}", type="negative")
                self.dialog.close()
                self.refresh()

            with layout.actions_row():
                layout.button("Cancel", kind="quiet", on_click=self.dialog.close)
                layout.button("Delete", kind="danger", on_click=delete)
        self.dialog.open()

    def build(self) -> None:
        self.table = table.empty_aware_table(COLUMNS, row_key="id", pagination={"rowsPerPage": 25},
                                             empty_text="No runs yet: launch a search from the Search page.")
        self.table.table.add_slot("body-cell-task", TASK_SLOT)
        self.table.table.add_slot("body-cell-actions", DELETE_SLOT)
        self.table.table.on("delete", lambda e: self.confirm_delete(e.args))
        self.refresh()


def runs_list() -> None:
    shell.shell("/runs", layout.PAGE_MAX_WIDTH_WIDE)
    with layout.page_container(max_width=layout.PAGE_MAX_WIDTH_WIDE):
        layout.heading("Runs", level=1)
        RunsList().build()


def register() -> None:
    ui.page("/runs")(runs_list)
    ui.page("/runs/{run_id}")(run_page)
