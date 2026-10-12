"""Verdict dialog: shared between Run and Index views. Saves to Index and notifies caller."""
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from nicegui import ui

from ..index import Index, default_path, validate_verdict
from ..log import log
from . import runs_logic as rl
from .kit import layout

DB_ERRORS = (sqlite3.Error, OSError)
DB_ERROR_TEXT = "Failed to access Index. See logs."


def notify_db_error(context: str) -> None:
    """Logs current exception with context and notifies user with short message."""
    log.exception("%s", context)
    ui.notify(DB_ERROR_TEXT, type="negative")


@contextmanager
def open_index() -> Iterator[Index]:
    idx = Index(default_path())
    try:
        yield idx
    finally:
        idx.db.close()


def _last_context(repo: str) -> tuple[str, str]:
    """Project and task of last Verdict for repo: hint for dialog without Run."""
    try:
        with open_index() as idx:
            rows = [v for v in idx.verdicts() if v[1] == repo.lower()]
    except DB_ERRORS:  # hint should not block the dialog
        log.warning("Index project and task hints unavailable", exc_info=True)
        return "", ""
    # (project, name, verdict, task, date): last by date, on ties latest record
    last = max(reversed(rows), key=lambda v: v[4]) if rows else None
    return (last[0], last[3]) if last else ("", "")


class VerdictDialog:
    """One dialog per page; `open(repo, project, task)` populates and shows it."""

    def __init__(self, on_saved: Callable[[str], None]) -> None:
        self.on_saved = on_saved
        self.repo = ""
        with ui.dialog() as self.dialog, layout.section_card():
            self.title = layout.heading("Verdict", level=2)
            self.name = ui.label().classes("t-mono")
            self.kind = ui.select(rl.VERDICT_KINDS, value="watch", label="Verdict",
                                  on_change=lambda: self._sync_note()).props("outlined dense stack-label").classes("w-full")
            self.note = layout.field("Explanation", hint="Single line")
            self.project = layout.field("Project", required=True)
            self.task = layout.field("Task", required=True, hint="Brief: which project task")
            self.error = ui.label().classes("ic-status--error")
            with layout.actions_row():
                layout.button("Cancel", kind="quiet", on_click=self.dialog.close)
                layout.button("Save verdict", kind="primary", on_click=self.save)

    def _sync_note(self) -> None:
        label = rl.NOTE_LABELS.get(self.kind.value)
        self.note.set_visibility(label is not None)
        if label:
            self.note.props(f'label="{label}"')

    def open(self, repo: str, project: str = "", task: str = "") -> None:
        self.repo = repo
        last_project, last_task = ("", "") if (project and task) else _last_context(repo)
        self.name.set_text(repo)
        self.project.value, self.task.value = project or last_project, task or last_task
        self.kind.value, self.note.value = "watch", ""
        self.error.set_text("")
        self._sync_note()
        self.dialog.open()

    def save(self) -> None:
        project, task = (self.project.value or "").strip(), (self.task.value or "").strip()
        try:
            text = rl.compose_verdict(self.kind.value, self.note.value or "")
            validate_verdict(self.repo, text, project, task)
            with open_index() as idx:
                idx.add_verdict(self.repo, text, project, task)
        except ValueError as e:
            self.error.set_text(str(e))
            return
        except DB_ERRORS:
            notify_db_error(f"Failed to save Verdict: {self.repo}")
            return
        self.dialog.close()
        ui.notify(f"Verdict saved: {self.repo}", type="positive")
        self.on_saved(self.repo)
