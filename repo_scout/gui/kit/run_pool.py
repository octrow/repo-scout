"""Pool of parallel subprocesses: slots + queue, without any `ui.*`.

This module intentionally does not know about NiceGUI widgets (except the default spawner
`background_tasks.create`) — all logic is testable without a running app.

Rules paid for in blood:
- `_run_lifecycle` and `_pump_output` do NOT call `ui.*` (including `ui.notify`):
  a background task has an empty slot-stack, any `ui.*` call raises RuntimeError.
- `_run_lifecycle` is cancel-safe: when stopping the service NiceGUI cancels all
  background tasks (~2s budget), and without `terminate()` in `finally` the subprocess
  is orphaned and keeps running/logging/holding ports.
- slot semaphore is created lazily: an `asyncio.Semaphore` cannot be reused
  across event loops (asyncio/mixins.py).
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

logger = logging.getLogger(__name__)

# --- pool constants ---------------------------------------------------------

MAX_PARALLEL_RUNS = 3
MAX_TOTAL_PENDING = 20  # queued + running: guard against infinite queue
FINISHED_HISTORY_LIMIT = 20  # max finished kept, oldest evicted
STREAM_LINE_LIMIT = 1024 * 1024  # bytes per output line (asyncio default 64 KiB breaks pipe)
OVERLONG_LINE_MARKER = "[nicegui-kit: line longer than STREAM_LINE_LIMIT truncated]"

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
    """A single run: queue → execution → completion. Consumed by UI as-is.

    Domain fields from source (kind, env_name, uuid_value) are generalized into
    `label` (heading for UI) + `meta` (arbitrary domain dict for caller).
    """

    run_id: str
    argv: list[str]
    label: str = ""
    meta: dict = field(default_factory=dict)
    status: str = QUEUED
    env: dict[str, str] = field(default_factory=dict)  # snapshot at submission
    lines: list[str] = field(default_factory=list)  # merged stdout+stderr
    process: "asyncio.subprocess.Process | None" = None
    return_code: int | None = None
    created_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancelled: bool = False  # user requested cancel of this run


# --- module state (process-global by design) ---------------------------------

RUNS: dict[str, RunState] = {}  # insertion-ordered: queue + active + history

_SLOTS: asyncio.Semaphore | None = None
_MAX_PARALLEL = MAX_PARALLEL_RUNS


def slots() -> asyncio.Semaphore:
    """Pool semaphore; created on first access inside running loop."""
    global _SLOTS
    if _SLOTS is None:
        _SLOTS = asyncio.Semaphore(_MAX_PARALLEL)
    return _SLOTS


def reset_pool_for_tests(*, max_parallel: int | None = None) -> None:
    """Clears RUNS and drops semaphore (new loop — new semaphore). For tests only."""
    global _SLOTS, _MAX_PARALLEL
    RUNS.clear()
    _SLOTS = None
    _MAX_PARALLEL = MAX_PARALLEL_RUNS if max_parallel is None else max_parallel


def _prune_finished_history() -> None:
    """Keeps at most FINISHED_HISTORY_LIMIT completed runs; queued/running are untouched."""
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
    """Queues a subprocess and spawns its lifecycle.

    None — queue overflow (MAX_TOTAL_PENDING). `argv` — full command line
    (executable + args); `cwd`/`env` passed to subprocess_exec as-is;
    `on_line` called on each merged stdout+stderr line (not from UI context —
    see module docstring warning).
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
    """Reads merged stdout/stderr line by line into state.lines; optionally notifies on_line."""
    process = state.process
    assert process is not None and process.stdout is not None
    while True:
        try:
            raw = await process.stdout.readline()
        except ValueError:  # line > limit: asyncio dropped it from buffer
            state.lines.append(OVERLONG_LINE_MARKER)
            continue
        if not raw:
            break
        line = raw.decode(errors="replace").rstrip("\n")
        state.lines.append(line)
        if on_line is not None:
            try:
                on_line(line)
            except Exception:  # external callback must not break pipe or kill process
                logger.exception("on_line callback failed for run %s", state.run_id)


async def _run_lifecycle(
    state: RunState, cwd: "str | Path | None", on_line: OnLine | None,
) -> None:
    """Waits for slot, starts subprocess, pumps log, sets final status."""
    try:
        async with slots():
            if state.status == CANCELLED or state.cancelled:
                return  # cancelled while in queue — do not start at all
            await _execute(state, cwd, on_line)
    finally:
        _finalize(state)


async def _execute(state: RunState, cwd: "str | Path | None", on_line: OnLine | None) -> None:
    """Slot acquired: start process, stream output to end, set done/failed/cancelled."""
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
    except OSError as exc:  # missing binary / cwd / permission: this is FAILED, not cancelled
        state.lines.append(f"failed to start: {exc}")
        state.status = FAILED
        return
    if state.cancelled:  # cancel arrived while process was spawning
        state.process.terminate()
    await _pump_output(state, on_line)
    state.return_code = await state.process.wait()
    if state.cancelled:
        state.status = CANCELLED
    else:
        state.status = DONE if state.return_code == 0 else FAILED


def _finalize(state: RunState) -> None:
    """Task cancellation (NiceGUI teardown, 2s budget) must not leave orphans."""
    process = state.process
    if process is not None and process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
    if state.status in PENDING_STATUSES:
        state.status = CANCELLED
    if state.finished_at is None:
        state.finished_at = _now()


def request_cancel(run_id: str) -> bool:
    """Stops run: queued — immediately, running — by signal; False if nothing to cancel."""
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
        return True  # still spawning: _execute will see cancelled and terminate
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):  # exited on its own
            process.terminate()  # status delivered by _run_lifecycle
        return True
    return False


# --- UI helpers --------------------------------------------------------------


def active_runs() -> list[RunState]:
    return [state for state in RUNS.values() if state.status == RUNNING]


def queued_runs() -> list[RunState]:
    return [state for state in RUNS.values() if state.status == QUEUED]


def live_runs() -> list[RunState]:
    """queued + running, in arrival order."""
    return [state for state in RUNS.values() if state.status in PENDING_STATUSES]


def all_runs() -> list[RunState]:
    """Everything in the pool (queue + active + history)."""
    return list(RUNS.values())


def queued_position(state: RunState) -> int:
    """1-based position in queue; 0 if run is not queued."""
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
    """Safety guard for app.on_shutdown: terminates all surviving processes.

    `grace_seconds > 0` — waits up to `grace_seconds` after SIGTERM (shared budget across
    all processes, not per process), giving children with graceful handlers time to finish.
    Unfinished processes remain alive for caller to handle.

    Coroutine because `process.wait()` requires it; `app.on_shutdown` accepts coroutines,
    and this runs before NiceGUI cancels background tasks with its ~2s budget.
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
