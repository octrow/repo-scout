"""Пул параллельных подпроцессов: слоты + очередь, без единого `ui.*`.

Модуль сознательно не знает про nicegui-виджеты (кроме дефолтного спавнера
`background_tasks.create`) — вся логика тестируется без запущенного приложения.

Правила, за которые здесь платили кровью:
- `_run_lifecycle` и `_pump_output` НЕ вызывают `ui.*` (в т.ч. `ui.notify`):
  у background-таски пустой slot-stack, любой `ui.*` падает RuntimeError.
- `_run_lifecycle` cancel-safe: при остановке сервиса NiceGUI отменяет все
  background-таски (бюджет 2 c), и без `terminate()` в `finally` подпроцесс
  осиротеет и продолжит жить/писать в лог/держать порт.
- семафор слотов создаётся лениво: один `asyncio.Semaphore` нельзя
  переиспользовать между event loop'ами (asyncio/mixins.py).
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from nicegui import background_tasks

from .texts import tr

logger = logging.getLogger(__name__)

# --- константы пула ---------------------------------------------------------

MAX_PARALLEL_RUNS = 3
MAX_TOTAL_PENDING = 20  # queued + running: предохранитель от бесконечной очереди
FINISHED_HISTORY_LIMIT = 20  # завершённых храним не больше, старейшие вытесняются
STREAM_LINE_LIMIT = 1024 * 1024  # байт на строку вывода (дефолт asyncio 64 KiB рвёт пайп)

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"
PENDING_STATUSES = (QUEUED, RUNNING)

Spawner = Callable[..., Any]
OnLine = Callable[[str], None]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RunState:
    """Один прогон: очередь → запуск → финал. Читается UI как есть.

    Доменные поля исходника (kind, env_name, uuid_value) обобщены до
    `label` (заголовок для UI) + `meta` (что угодно доменное, читает вызывающий).
    """

    run_id: str
    argv: list[str]
    label: str = ""
    meta: dict = field(default_factory=dict)
    status: str = QUEUED
    env: dict[str, str] = field(default_factory=dict)  # снимок на момент постановки
    lines: list[str] = field(default_factory=list)  # merged stdout+stderr
    process: "asyncio.subprocess.Process | None" = None
    return_code: int | None = None
    created_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancelled: bool = False  # пользователь запросил остановку этого рана


# --- модульное состояние (процесс-глобальное, сознательно) ------------------

RUNS: dict[str, RunState] = {}  # insertion-ordered: очередь + активные + история

_SLOTS: asyncio.Semaphore | None = None
_MAX_PARALLEL = MAX_PARALLEL_RUNS


def slots() -> asyncio.Semaphore:
    """Семафор пула; создаётся при первом обращении внутри работающего лупа."""
    global _SLOTS
    if _SLOTS is None:
        _SLOTS = asyncio.Semaphore(_MAX_PARALLEL)
    return _SLOTS


def reset_pool_for_tests(*, max_parallel: int | None = None) -> None:
    """Чистит RUNS и роняет семафор (новый луп — новый семафор). Только для тестов."""
    global _SLOTS, _MAX_PARALLEL
    RUNS.clear()
    _SLOTS = None
    _MAX_PARALLEL = MAX_PARALLEL_RUNS if max_parallel is None else max_parallel


def _prune_finished_history() -> None:
    """Держит не больше FINISHED_HISTORY_LIMIT завершённых; queued/running неприкасаемы."""
    finished = [
        run_id for run_id, state in RUNS.items() if state.status not in PENDING_STATUSES
    ]
    for run_id in finished[: max(0, len(finished) - FINISHED_HISTORY_LIMIT)]:
        RUNS.pop(run_id, None)


def submit(
    argv: list[str],
    *,
    label: str = "",
    cwd: "str | Path | None" = None,
    env: dict[str, str] | None = None,
    meta: dict | None = None,
    on_line: OnLine | None = None,
    spawn: Spawner | None = None,
) -> RunState | None:
    """Ставит подпроцесс в очередь и спавнит его жизненный цикл.

    None — очередь переполнена (MAX_TOTAL_PENDING). `argv` — полная командная
    строка (executable + args); `cwd`/`env` идут как есть в subprocess_exec;
    `on_line` вызывается на каждую строку merged stdout+stderr (не из ui-контекста
    — см. предупреждение в докстринге модуля).
    """
    if len(queued_runs()) + len(active_runs()) >= MAX_TOTAL_PENDING:
        return None
    state = RunState(
        run_id=uuid4().hex[:8],
        argv=list(argv),
        label=label,
        meta=dict(meta or {}),
        env=dict(env) if env is not None else {},
    )
    RUNS[state.run_id] = state
    _prune_finished_history()
    spawner = spawn if spawn is not None else background_tasks.create
    spawner(_run_lifecycle(state, cwd, on_line), name=f"nicegui-kit-run-{state.run_id}")
    return state


async def _pump_output(state: RunState, on_line: OnLine | None) -> None:
    """Читает merged stdout/stderr построчно в state.lines; опционально шлёт on_line."""
    process = state.process
    assert process is not None and process.stdout is not None
    while True:
        try:
            raw = await process.stdout.readline()
        except ValueError:  # строка > limit: asyncio уже выкинул её из буфера
            state.lines.append(tr("overlong_line"))
            continue
        if not raw:
            break
        line = raw.decode(errors="replace").rstrip("\n")
        state.lines.append(line)
        if on_line is not None:
            try:
                on_line(line)
            except Exception:  # чужой колбэк не должен рвать пайп и гасить процесс
                logger.exception("on_line callback failed for run %s", state.run_id)


async def _run_lifecycle(
    state: RunState, cwd: "str | Path | None", on_line: OnLine | None,
) -> None:
    """Ждёт слот, запускает подпроцесс, качает лог, выставляет финальный статус."""
    try:
        async with slots():
            if state.status == CANCELLED or state.cancelled:
                return  # отменён, пока стоял в очереди — не стартуем вовсе
            await _execute(state, cwd, on_line)
    finally:
        _finalize(state)


async def _execute(state: RunState, cwd: "str | Path | None", on_line: OnLine | None) -> None:
    """Слот уже наш: стартуем процесс, читаем вывод до конца, ставим done/failed/cancelled."""
    state.status = RUNNING
    state.started_at = _now()
    try:
        state.process = await asyncio.create_subprocess_exec(
            *state.argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(cwd) if cwd is not None else None,
            env=state.env or None,
            limit=STREAM_LINE_LIMIT,
        )
    except OSError as exc:  # нет бинарника / cwd / прав: это FAILED, а не "остановлено"
        state.lines.append(tr("spawn_failed", error=exc))
        state.status = FAILED
        return
    if state.cancelled:  # cancel пришёл, пока процесс ещё спавнился
        state.process.terminate()
    await _pump_output(state, on_line)
    state.return_code = await state.process.wait()
    if state.cancelled:
        state.status = CANCELLED
    else:
        state.status = DONE if state.return_code == 0 else FAILED


def _finalize(state: RunState) -> None:
    """Отмена таски (teardown NiceGUI, бюджет 2 c) не должна оставлять сироту."""
    process = state.process
    if process is not None and process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
    if state.status in PENDING_STATUSES:
        state.status = CANCELLED
    if state.finished_at is None:
        state.finished_at = _now()


def request_cancel(run_id: str) -> bool:
    """Останавливает ран: queued — сразу, running — сигналом; False если нечего гасить."""
    state = RUNS.get(run_id)
    if state is None or state.status not in PENDING_STATUSES:
        return False
    state.cancelled = True
    if state.status == QUEUED:
        state.status = CANCELLED
        state.finished_at = _now()
        return True
    process = state.process
    if process is None:
        return True  # ещё спавнится: _execute увидит cancelled и погасит сам
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):  # успел выйти сам
            process.terminate()  # статус доставит _run_lifecycle
        return True
    return False


# --- хелперы для UI ---------------------------------------------------------


def active_runs() -> list[RunState]:
    return [state for state in RUNS.values() if state.status == RUNNING]


def queued_runs() -> list[RunState]:
    return [state for state in RUNS.values() if state.status == QUEUED]


def live_runs() -> list[RunState]:
    """queued + running, в порядке появления."""
    return [state for state in RUNS.values() if state.status in PENDING_STATUSES]


def all_runs() -> list[RunState]:
    """Всё, что есть в пуле (очередь + активные + история)."""
    return list(RUNS.values())


def queued_position(state: RunState) -> int:
    """1-based позиция в очереди; 0 — ран уже не queued."""
    queued = queued_runs()
    if state not in queued:
        return 0
    return queued.index(state) + 1


def run_duration(state: RunState) -> str:
    """M:SS since the run started; empty while it is still queued."""
    if state.started_at is None:
        return ""
    end = state.finished_at or _now()
    seconds = max(0, int((end - state.started_at).total_seconds()))
    return f"{seconds // 60}:{seconds % 60:02d}"


async def terminate_all_live_processes(grace_seconds: float = 0.0) -> None:
    """Страховка для app.on_shutdown: гасит всё, что ещё дышит.

    `grace_seconds > 0` — после SIGTERM ждёт до `grace_seconds` (бюджет общий на все
    процессы, не на каждый), чтобы ребёнок с graceful-обработчиком успел дописать своё и
    выйти сам. Кто не успел — остаётся жить: что с ним делать дальше, решает вызывающий.

    Корутина, потому что ждать `process.wait()` иначе нечем; `app.on_shutdown` принимает и
    корутину, и это единственное место, где ожидание вообще имеет смысл — оно выполняется
    до того, как NiceGUI начнёт отменять background-таски своим бюджетом ~2 c.
    """
    live = [
        state.process for state in RUNS.values()
        if state.process is not None and state.process.returncode is None
    ]
    for process in live:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
    if grace_seconds > 0 and live:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(
                asyncio.gather(*(process.wait() for process in live),
                               return_exceptions=True),
                grace_seconds,
            )
