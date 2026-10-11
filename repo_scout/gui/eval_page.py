"""Страница «Eval» (`/eval`): наборы eval/*.toml, запуск подпроцессом, отчёт из `--out`."""
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
FLAG_LABELS = {"detail": "Список репо по наборам", "sweep": "Пороги Близости 0.50–0.90", "no_round2": "Без второго круга",
               "calls": "Число вызовов API", "index_check": "Проверка Индекса (Фаза 5)",
               "fake_stars": "Флаг «всплеск звёзд» (eval/fake-stars)", "all_grid": "С ним: вся сетка порогов"}


def report_path(now: datetime) -> Path:
    return runs.runs_dir().parent / REPORTS_DIR / f"{now.strftime('%Y%m%d-%H%M%S-%f')}.md"


def _projects() -> list[str]:
    try:
        with open_index() as idx:
            return list(dict.fromkeys(v[0] for v in idx.verdicts()))
    except (sqlite3.Error, OSError):  # без Индекса выбор проекта просто пуст
        log.warning("Проекты из Индекса недоступны", exc_info=True)
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
        run = run_pool.submit(argv, label=label, meta={"out": str(out)})
        if run is None:
            ui.notify("Очередь запусков переполнена: дождитесь завершения", type="warning")
            return
        self.pending[run.run_id] = out
        ui.notify("Eval запущен", type="positive")

    def start(self) -> None:
        o = self.options()
        if errors := el.eval_errors(o):
            ui.notify(errors[0], type="negative")
            return
        out = report_path(datetime.now())
        names = ", ".join(s.name for s in self.sets if s.path in o.sets) or "fake-stars"
        self.submit(el.eval_argv(o, out), out, f"eval: {names}")

    def watch(self) -> None:
        """ui.* только в таймере страницы: из on_line вызывать нельзя."""
        for run_id, out in list(self.pending.items()):
            state = run_pool.RUNS.get(run_id)
            if state is None or state.status in run_pool.PENDING_STATUSES:
                continue
            self.pending.pop(run_id)
            self.report.clear()
            with self.report:
                if state.status == run_pool.DONE and out.is_file():
                    layout.heading("Отчёт", level=2)
                    layout.markdown_reader(out.read_text(encoding="utf-8"))
                elif state.status == run_pool.FAILED:
                    layout.failed("Eval завершился с ошибкой: подробности в логе запуска выше")

    def cards(self) -> None:
        with layout.grid(min_col="18rem"):
            for s in self.sets:
                with layout.section_card(recessive=True):
                    ui.checkbox(s.name, on_change=lambda e, p=s.path: self.picked.add(p) if e.value else self.picked.discard(p))
                    ui.label(s.task[:160]).classes("t-meta")
                    ui.label(f"Ожидаемых: {s.n_expected} · снимок: {s.snapshot}").classes("t-meta")

    def controls(self) -> None:
        with layout.section_card():
            self.opts["mode"] = ui.toggle({"replay": "Снапшоты (без сети)", "record": "Записать снапшоты (сеть)"}, value="replay")
            with layout.grid():
                for key, label in FLAG_LABELS.items():
                    self.opts[key] = ui.checkbox(label).classes("ic-span-6")
                self.opts["top"] = ui.number("Вывести топ-N выдачи (0 — не выводить)", value=0, min=0, precision=0) \
                    .props("outlined dense stack-label").classes("ic-span-6 w-full")
            export = self.export_dialog()
            with layout.actions_row(end=False):
                layout.button("Запустить eval", kind="primary", icon="play_arrow", on_click=self.start)
                layout.button("Экспортировать вердикты", icon="download", on_click=export.open)

    def export_dialog(self) -> ui.dialog:
        with ui.dialog() as dialog, layout.section_card():
            layout.heading("Экспорт вердиктов", level=2)
            ui.label("Вердикты Индекса как блоки [[expected]] для наборов.").classes("t-meta")
            project = ui.select(_projects(), label="Проект", clearable=True) \
                .props('outlined dense stack-label hint="Пусто: все проекты"').classes("w-full")

            def go() -> None:
                out = report_path(datetime.now())
                self.submit(el.export_argv(project.value, out), out, "eval: экспорт вердиктов")
                dialog.close()

            with layout.actions_row():
                layout.button("Отмена", kind="quiet", on_click=dialog.close)
                layout.button("Экспортировать", kind="primary", on_click=go)
        return dialog

    def build(self) -> None:
        if not self.sets:
            layout.empty("Наборы eval/*.toml не найдены")
        else:
            self.cards()
        self.controls()
        layout.heading("Запуски", level=2)
        run_monitor.attach_run_monitor(idle_text="Запусков пока не было")
        self.report = ui.column().classes("w-full ic-stack")
        ui.timer(POLL_PERIOD, self.watch)


def eval_page() -> None:
    shell.shell("/eval", layout.PAGE_MAX_WIDTH_WIDE)
    with layout.page_container(max_width=layout.PAGE_MAX_WIDTH_WIDE):
        layout.heading("Eval", level=1)
        EvalPage().build()


def register() -> None:
    ui.page("/eval")(eval_page)
