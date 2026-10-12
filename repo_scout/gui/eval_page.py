"""Eval page (`/eval`): eval/*.toml datasets, subprocess execution, report from `--out`."""
import sqlite3
from datetime import datetime
from pathlib import Path

from nicegui import ui

from .. import runs
from ..log import log
from . import eval_logic as el
from . import shell
from .kit import layout, run_monitor, run_pool
from .search_form import EVAL_DIR
from .verdict_dialog import open_index

POLL_PERIOD = 1.0
REPORTS_DIR = "eval-reports"
FLAG_LABELS = {"detail": "List repos by dataset", "sweep": "Closeness thresholds 0.50–0.90", "no_round2": "Skip round 2",
               "calls": "API call counts", "index_check": "Index check (Phase 5)",
               "fake_stars": "Flag 'burst★' (eval/fake-stars)", "all_grid": "With it: full threshold grid"}


def report_path(now: datetime) -> Path:
    return runs.runs_dir().parent / REPORTS_DIR / f"{now.strftime('%Y%m%d-%H%M%S-%f')}.md"


def _projects() -> list[str]:
    try:
        with open_index() as idx:
            return list(dict.fromkeys(v[0] for v in idx.verdicts()))
    except (sqlite3.Error, OSError):  # without Index project list is simply empty
        log.warning("Index projects unavailable", exc_info=True)
        return []


class EvalPage:
    def __init__(self) -> None:
        self.sets = el.list_sets(EVAL_DIR)
        self.picked: set[Path] = set()
        self.opts: dict[str, ui.element] = {}
        self.pending: dict[str, Path] = {}
        self.report: ui.column | None = None

    def options(self) -> el.EvalOptions:
        o = el.EvalOptions(sets=[s.path for s in self.sets if s.path in self.picked],
                           record=self.opts["mode"].value == "record", top=int(self.opts["top"].value or 0))
        for key in FLAG_LABELS:
            setattr(o, key, bool(self.opts[key].value))
        return o

    def submit(self, argv: list[str], out: Path, label: str) -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        run_item = run_pool.submit(argv, label=label, meta={"out": str(out)})
        if run_item is None:
            ui.notify("Execution queue is full: wait for completion", type="warning")
            return
        self.pending[run_item.run_id] = out
        ui.notify("Eval started", type="positive")

    def start(self) -> None:
        o = self.options()
        if errors := el.eval_errors(o):
            ui.notify(errors[0], type="negative")
            return
        out = report_path(datetime.now())
        names = ", ".join(s.name for s in self.sets if s.path in o.sets) or "fake-stars"
        self.submit(el.eval_argv(o, out), out, f"eval: {names}")

    def watch(self) -> None:
        """ui.* only in page timer: must not call from on_line."""
        for run_id, out in list(self.pending.items()):
            state = run_pool.RUNS.get(run_id)
            if state is None or state.status in run_pool.PENDING_STATUSES:
                continue
            self.pending.pop(run_id)
            self.report.clear()
            with self.report:
                if state.status == run_pool.DONE and out.is_file():
                    layout.heading("Report", level=2)
                    layout.markdown_reader(out.read_text(encoding="utf-8"))
                elif state.status == run_pool.FAILED:
                    layout.failed("Eval failed with error: see execution log above for details")

    def cards(self) -> None:
        with layout.grid(min_col="18rem"):
            for s in self.sets:
                with layout.section_card(recessive=True):
                    ui.checkbox(s.name, on_change=lambda e, p=s.path: self.picked.add(p) if e.value else self.picked.discard(p))
                    ui.label(s.task[:160]).classes("t-meta")
                    ui.label(f"Expected: {s.n_expected} · snapshot: {s.snapshot}").classes("t-meta")

    def controls(self) -> None:
        with layout.section_card():
            self.opts["mode"] = ui.toggle({"replay": "Snapshots (offline)", "record": "Record snapshots (network)"}, value="replay")
            with layout.grid():
                for key, label in FLAG_LABELS.items():
                    self.opts[key] = ui.checkbox(label).classes("ic-span-6")
                self.opts["top"] = ui.number("Show top-N results (0 — do not show)", value=0, min=0, precision=0) \
                    .props("outlined dense stack-label").classes("ic-span-6 w-full")
            export = self.export_dialog()
            with layout.actions_row(end=False):
                layout.button("Launch eval", kind="primary", icon="play_arrow", on_click=self.start)
                layout.button("Export verdicts", icon="download", on_click=export.open)

    def export_dialog(self) -> ui.dialog:
        with ui.dialog() as dialog, layout.section_card():
            layout.heading("Export verdicts", level=2)
            ui.label("Index verdicts as [[expected]] blocks for datasets.").classes("t-meta")
            project = ui.select(_projects(), label="Project", clearable=True) \
                .props('outlined dense stack-label hint="Empty: all projects"').classes("w-full")

            def go() -> None:
                out = report_path(datetime.now())
                self.submit(el.export_argv(project.value, out), out, "eval: export verdicts")
                dialog.close()

            with layout.actions_row():
                layout.button("Cancel", kind="quiet", on_click=dialog.close)
                layout.button("Export", kind="primary", on_click=go)
        return dialog

    def build(self) -> None:
        if not self.sets:
            layout.empty("eval/*.toml datasets not found")
        else:
            self.cards()
        self.controls()
        layout.heading("Runs", level=2)
        run_monitor.attach_run_monitor(idle_text="No runs yet")
        self.report = ui.column().classes("w-full ic-stack")
        ui.timer(POLL_PERIOD, self.watch)


def eval_page() -> None:
    shell.shell("/eval", layout.PAGE_MAX_WIDTH_WIDE)
    with layout.page_container(max_width=layout.PAGE_MAX_WIDTH_WIDE):
        layout.heading("Eval", level=1)
        EvalPage().build()


def register() -> None:
    ui.page("/eval")(eval_page)
