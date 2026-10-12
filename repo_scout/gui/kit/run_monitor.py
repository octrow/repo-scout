"""Live run monitor for run_pool: queue, status, log, cancellation.

Key rule: timer NEVER rebuilds elements of existing runs, only mutates them
(NiceGUI has no virtual DOM — rebuilding kills expansion state, log scroll, and focus).
Deletion is only for runs evicted from the pool by history limit (see `run_pool.FINISHED_HISTORY_LIMIT`).
"""

from collections.abc import Callable
from dataclasses import dataclass

from nicegui import ui

from . import layout, run_pool
from .run_pool import RunState

DEFAULT_LOG_MAX_LINES = 2000  # DOM cap only; RunState.lines keeps the full log
DEFAULT_ERROR_TAIL_LINES = 15
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
LOG_VISIBLE_LINES = 14  # the log grows with its lines up to this, then scrolls
COPY_TEXT = "Copy for chat"  # icon-only button: tooltip + aria-label

_STATUS_CSS_CLASSES = {
    run_pool.QUEUED: "ic-status--idle",
    run_pool.RUNNING: "ic-status--running",
    run_pool.DONE: "ic-status--ok",
    run_pool.CANCELLED: "ic-status--cancel",
}


@dataclass
class RunView:
    """Widgets of a single run in the monitor + counters of rendered content."""

    expansion: ui.expansion
    status_label: ui.label
    duration_label: ui.label
    log: ui.log
    log_caption: ui.label
    cancel_button: ui.button
    copy_button: ui.button
    shown: int = 0


def run_status_text(state: RunState) -> tuple[str, str]:
    """(human status, css class) - shared by every page that lists runs."""
    css_class = _STATUS_CSS_CLASSES.get(state.status, "ic-status--error")
    if state.status == run_pool.QUEUED:
        text = f"queued · #{run_pool.queued_position(state)}"
    elif state.status == run_pool.RUNNING:
        text = "running"
    elif state.status == run_pool.DONE:
        text = "done"
    elif state.status == run_pool.CANCELLED:
        text = "cancelled by user"
    else:
        text = f"error · code {state.return_code}"
    return text, css_class


def _chat_report(state: RunState, error_tail_lines: int) -> str:
    """Chat export content: label, status, log tail without log parsing."""
    tail = "\n".join(state.lines[-error_tail_lines:])
    return f"{state.label or 'run'}: {run_status_text(state)[0]}\n\n{tail}"


def _confirm_cancel(state: RunState) -> None:
    """Cancellation requires confirmation dialog."""
    with ui.dialog() as dialog, ui.card().classes("ic-card p-4 items-stretch"):
        ui.label("Stop this run?").classes("t-title-section")
        ui.label(state.label or "—").classes("t-meta")
        with layout.actions_row():
            layout.button("Cancel", kind="quiet", on_click=dialog.close)

            def _confirm() -> None:
                dialog.close()
                run_pool.request_cancel(state.run_id)

            layout.button("Stop", kind="danger", on_click=_confirm)
    dialog.open()


def _create_run_view(
    runs_container: ui.column, state: RunState, *, log_max_lines: int, error_tail_lines: int,
) -> RunView:
    """Header columns: [label] [status badge] [duration]. Inside: single log with header."""
    with runs_container:
        with ui.expansion().classes("w-full ic-run border rounded") as expansion:
            with expansion.add_slot("header"), ui.row().classes("ic-run-head"):
                ui.label(state.label or "run").classes("ic-run-title")
                status_label = ui.label("").classes("ic-badge ic-status--idle")
                duration_label = ui.label("").classes("t-meta ic-run-time")
            with ui.column().classes("ic-log-panel w-full"):
                with ui.row().classes("ic-log-head w-full items-center justify-between"):
                    log_caption = ui.label("").classes("t-meta ic-log-caption")
                    with ui.row().classes("ic-actions items-center"):
                        cancel_button = layout.button("Stop", kind="danger", size="row")
                        copy_button = layout.button(
                            kind="quiet", size="row", icon="content_copy",
                            on_click=lambda: _copy_report(state, error_tail_lines),
                        ).props(f'round aria-label="{COPY_TEXT}"').tooltip(COPY_TEXT)
                log = ui.log(max_lines=log_max_lines).classes("w-full")
            cancel_button.on_click(lambda: _confirm_cancel(state))
    return RunView(
        expansion=expansion, status_label=status_label, duration_label=duration_label,
        log=log, log_caption=log_caption, cancel_button=cancel_button, copy_button=copy_button,
    )


def _copy_report(state: RunState, error_tail_lines: int) -> None:
    ui.clipboard.write(_chat_report(state, error_tail_lines))
    ui.notify(layout.COPIED_TEXT, type="positive")


def _lines_word(n: int) -> str:
    return "line" if n == 1 else "lines"


def _update_run_view(view: RunView, state: RunState) -> None:
    text, status_class = run_status_text(state)
    view.status_label.text = text
    view.status_label.classes(replace=f"ic-badge {status_class}")
    view.duration_label.text = run_pool.run_duration(state) or ""
    is_pending = state.status in run_pool.PENDING_STATUSES
    view.cancel_button.set_visibility(is_pending)
    view.cancel_button.set_text(
        "Remove from queue" if state.status == run_pool.QUEUED else "Stop",
    )
    view.copy_button.set_visibility(bool(state.lines))
    if view.shown == len(state.lines) and view.log_caption.text:
        return
    while view.shown < len(state.lines):
        view.log.push(state.lines[view.shown])
        view.shown += 1
    n = len(state.lines)
    view.log_caption.text = f"Output: {n} {_lines_word(n)}" if n else "No output yet"
    # ui.log is a QScrollArea and can't grow by itself: its height follows the line count
    view.log.style(f"--ic-log-lines: {min(max(n, 1), LOG_VISIBLE_LINES)}")


def attach_run_monitor(
    *,
    run_filter: "Callable[[RunState], bool] | None" = None,
    idle_text: str = "Nothing is currently running",
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    log_max_lines: int = DEFAULT_LOG_MAX_LINES,
    error_tail_lines: int = DEFAULT_ERROR_TAIL_LINES,
) -> None:
    """Live list of pool runs: queue, active, and history."""
    empty_label = ui.label(idle_text).classes("t-status ic-status--idle")
    runs_container = ui.column().classes("ic-stack w-full items-stretch")
    views: dict[str, RunView] = {}

    def _tick() -> None:
        states = [
            state
            for state in run_pool.RUNS.values()
            if run_filter is None or run_filter(state)
        ]
        empty_label.set_visibility(not states)
        for state in states:
            view = views.get(state.run_id)
            if view is None:
                view = _create_run_view(
                    runs_container, state,
                    log_max_lines=log_max_lines, error_tail_lines=error_tail_lines,
                )
                views[state.run_id] = view
                if state is states[-1]:
                    view.expansion.open()
            _update_run_view(view, state)
        alive = {state.run_id for state in states}
        for run_id in [run_id for run_id in views if run_id not in alive]:
            views.pop(run_id).expansion.delete()

    ui.timer(poll_interval_seconds, _tick)
