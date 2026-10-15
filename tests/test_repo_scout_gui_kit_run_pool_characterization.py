import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from repo_scout.gui.kit import run_pool
from repo_scout.gui.kit.run_pool import (
    CANCELLED,
    DONE,
    FAILED,
    FINISHED_HISTORY_LIMIT,
    MAX_PARALLEL_RUNS,
    MAX_TOTAL_PENDING,
    QUEUED,
    RUNNING,
    RunState,
)
from repo_scout.gui.kit.texts import tr

# --------------------------------------------------------------------------- fakes

class FakeStream:
    def __init__(self, items=(), gate=None, started=None):
        self.items = list(items)
        self.gate = gate
        self.started = started

    async def readline(self):
        if self.started is not None:
            self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        if not self.items:
            return b""
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

class FakeProcess:
    def __init__(self, lines=(), final=0, gate=None, started=None,
                 terminate_raises=False, returncode=None):
        self.stdout = FakeStream(lines, gate=gate, started=started)
        self.final = final
        self.returncode = returncode
        self.terminated = 0
        self.terminate_raises = terminate_raises
        self.wait_calls = 0

    def terminate(self):
        self.terminated += 1
        if self.terminate_raises:
            raise ProcessLookupError()

    async def wait(self):
        self.wait_calls += 1
        self.returncode = self.final
        return self.final

def patch_exec(monkeypatch, process=None, exc=None, on_call=None):
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        if on_call is not None:
            on_call()
        if exc is not None:
            raise exc
        return process

    monkeypatch.setattr(run_pool.asyncio, "create_subprocess_exec", fake_exec)
    return calls

def make_state(run_id="r1", **kwargs):
    kwargs.setdefault("argv", ["prog", "arg"])
    state = RunState(run_id=run_id, **kwargs)
    run_pool.RUNS[run_id] = state
    return state

@pytest.fixture(autouse=True)
def _clean_pool():
    run_pool.reset_pool_for_tests()
    yield
    run_pool.reset_pool_for_tests()

# --------------------------------------------------------------------------- RunState / pool state

def test_runstate_defaults():
    state = RunState(run_id="abc", argv=["x"])
    assert state.label == ""
    assert state.meta == {}
    assert state.status == QUEUED
    assert state.env == {}
    assert state.lines == []
    assert state.process is None
    assert state.return_code is None
    assert state.started_at is None
    assert state.finished_at is None
    assert state.cancelled is False
    assert state.created_at.tzinfo is timezone.utc

def test_slots_is_lazy_singleton_until_reset():
    sem = run_pool.slots()
    assert run_pool.slots() is sem
    run_pool.reset_pool_for_tests()
    assert run_pool.slots() is not sem

def test_reset_clears_runs_and_applies_max_parallel():
    make_state()
    run_pool.reset_pool_for_tests(max_parallel=1)
    assert run_pool.RUNS == {}

    async def scenario():
        sem = run_pool.slots()
        await sem.acquire()
        return sem.locked()

    assert asyncio.run(scenario()) is True

def test_reset_default_max_parallel_is_constant():
    run_pool.reset_pool_for_tests(max_parallel=1)
    run_pool.reset_pool_for_tests()

    async def scenario():
        sem = run_pool.slots()
        for _ in range(MAX_PARALLEL_RUNS):
            await sem.acquire()
        return sem.locked()

    assert asyncio.run(scenario()) is True

# --------------------------------------------------------------------------- submit

def test_submit_registers_state_and_calls_spawner():
    spawned = []

    def spawn(coro, **kwargs):
        spawned.append(kwargs)
        coro.close()

    argv = ["python", "-V"]
    env = {"A": "1"}
    meta = {"k": "v"}
    state = run_pool.submit(argv, label="L", env=env, meta=meta, spawn=spawn)

    assert state is not None
    assert run_pool.RUNS[state.run_id] is state
    assert len(state.run_id) == 8
    assert state.argv == argv and state.argv is not argv
    assert state.label == "L"
    assert state.env == env and state.env is not env
    assert state.meta == meta and state.meta is not meta
    assert state.status == QUEUED
    assert spawned == [{"name": f"nicegui-kit-run-{state.run_id}"}]

def test_submit_none_env_and_meta_become_empty():
    state = run_pool.submit(["x"], spawn=lambda coro, **kw: coro.close())
    assert state.env == {}
    assert state.meta == {}

def test_submit_uses_background_tasks_create_by_default(monkeypatch):
    seen = []

    def fake_create(coro, **kwargs):
        seen.append(kwargs)
        coro.close()

    monkeypatch.setattr(run_pool.background_tasks, "create", fake_create)
    state = run_pool.submit(["x"])
    assert seen == [{"name": f"nicegui-kit-run-{state.run_id}"}]

def test_submit_returns_none_when_pending_limit_reached():
    for i in range(MAX_TOTAL_PENDING):
        make_state(run_id=f"x{i}", status=QUEUED if i % 2 else RUNNING)
    calls = []
    result = run_pool.submit(["x"], spawn=lambda coro, **kw: calls.append(coro))
    assert result is None
    assert calls == []
    assert len(run_pool.RUNS) == MAX_TOTAL_PENDING

def test_submit_allowed_just_below_limit():
    for i in range(MAX_TOTAL_PENDING - 1):
        make_state(run_id=f"x{i}", status=QUEUED)
    state = run_pool.submit(["x"], spawn=lambda coro, **kw: coro.close())
    assert state is not None

def test_finished_runs_do_not_count_towards_pending_limit():
    for i in range(MAX_TOTAL_PENDING):
        make_state(run_id=f"x{i}", status=DONE)
    state = run_pool.submit(["x"], spawn=lambda coro, **kw: coro.close())
    assert state is not None

def test_submit_prunes_oldest_finished_but_keeps_pending():
    make_state(run_id="pending", status=QUEUED)
    for i in range(25):
        make_state(run_id=f"d{i:02d}", status=DONE)
    state = run_pool.submit(["x"], spawn=lambda coro, **kw: coro.close())
    finished = [s for s in run_pool.RUNS.values() if s.status == DONE]
    assert len(finished) == FINISHED_HISTORY_LIMIT
    assert [s.run_id for s in finished][0] == "d05"
    assert "pending" in run_pool.RUNS
    assert state.run_id in run_pool.RUNS

# --------------------------------------------------------------------------- _pump_output

def test_pump_output_collects_decoded_lines_and_calls_on_line():
    state = make_state()
    state.process = FakeProcess(lines=[b"one\n", b"two\r\n", b"\n", b"bad\xff\n", b"last"])
    got = []
    asyncio.run(run_pool._pump_output(state, got.append))
    expected = ["one", "two\r", "", "bad\ufffd", "last"]
    assert state.lines == expected
    assert got == expected

def test_pump_output_without_callback():
    state = make_state()
    state.process = FakeProcess(lines=[b"a\n"])
    asyncio.run(run_pool._pump_output(state, None))
    assert state.lines == ["a"]

def test_pump_output_swallows_callback_errors(caplog):
    state = make_state()
    state.process = FakeProcess(lines=[b"a\n", b"b\n"])

    def boom(line):
        raise RuntimeError("cb")

    asyncio.run(run_pool._pump_output(state, boom))
    assert state.lines == ["a", "b"]
    assert any("on_line callback failed" in r.getMessage() for r in caplog.records)

def test_pump_output_overlong_line_recorded_and_reading_continues():
    state = make_state()
    state.process = FakeProcess(lines=[ValueError("too long"), b"ok\n"])
    asyncio.run(run_pool._pump_output(state, None))
    assert state.lines == [tr("overlong_line"), "ok"]

# --------------------------------------------------------------------------- lifecycle

def test_lifecycle_success(monkeypatch, tmp_path):
    state = make_state(env={"A": "1"})
    proc = FakeProcess(lines=[b"hello\n"], final=0)
    calls = patch_exec(monkeypatch, process=proc)
    asyncio.run(run_pool._run_lifecycle(state, tmp_path, None))

    assert state.status == DONE
    assert state.return_code == 0
    assert state.lines == ["hello"]
    assert state.process is proc
    assert state.started_at is not None
    assert state.finished_at is not None
    assert proc.terminated == 0

    (args, kwargs), = calls
    assert args == ("prog", "arg")
    assert kwargs["stdout"] == asyncio.subprocess.PIPE
    assert kwargs["stderr"] == asyncio.subprocess.STDOUT
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["env"] == {"A": "1"}
    assert kwargs["limit"] == run_pool.STREAM_LINE_LIMIT

def test_lifecycle_empty_env_and_no_cwd_pass_none(monkeypatch):
    state = make_state()
    calls = patch_exec(monkeypatch, process=FakeProcess())
    asyncio.run(run_pool._run_lifecycle(state, None, None))
    (_, kwargs), = calls
    assert kwargs["cwd"] is None
    assert kwargs["env"] is None

def test_lifecycle_nonzero_exit_is_failed(monkeypatch):
    state = make_state()
    patch_exec(monkeypatch, process=FakeProcess(final=3))
    asyncio.run(run_pool._run_lifecycle(state, None, None))
    assert state.status == FAILED
    assert state.return_code == 3
    assert state.finished_at is not None

def test_lifecycle_spawn_oserror_is_failed(monkeypatch):
    state = make_state()
    exc = FileNotFoundError("nope")
    patch_exec(monkeypatch, exc=exc)
    asyncio.run(run_pool._run_lifecycle(state, None, None))
    assert state.status == FAILED
    assert state.process is None
    assert state.return_code is None
    assert state.lines == [tr("spawn_failed", error=exc)]
    assert state.started_at is not None
    assert state.finished_at is not None

def test_lifecycle_cancel_during_spawn_terminates_and_marks_cancelled(monkeypatch):
    state = make_state()
    proc = FakeProcess(final=-15)

    def flag_cancel():
        state.cancelled = True

    patch_exec(monkeypatch, process=proc, on_call=flag_cancel)
    asyncio.run(run_pool._run_lifecycle(state, None, None))
    assert proc.terminated == 1
    assert state.status == CANCELLED
    assert state.return_code == -15

def test_lifecycle_cancelled_flag_set_in_queue_skips_spawn(monkeypatch):
    state = make_state()
    state.cancelled = True
    calls = patch_exec(monkeypatch, process=FakeProcess())
    asyncio.run(run_pool._run_lifecycle(state, None, None))
    assert calls == []
    assert state.status == CANCELLED
    assert state.finished_at is not None
    assert state.started_at is None

def test_lifecycle_already_cancelled_status_keeps_finished_at(monkeypatch):
    stamp = datetime(2020, 1, 1, tzinfo=timezone.utc)
    state = make_state(status=CANCELLED, finished_at=stamp)
    calls = patch_exec(monkeypatch, process=FakeProcess())
    asyncio.run(run_pool._run_lifecycle(state, None, None))
    assert calls == []
    assert state.status == CANCELLED
    assert state.finished_at == stamp

def test_lifecycle_task_cancellation_terminates_process(monkeypatch):
    state = make_state()
    proc = FakeProcess()

    async def scenario():
        started = asyncio.Event()
        gate = asyncio.Event()  # never set: reader blocks forever
        proc.stdout = FakeStream(gate=gate, started=started)
        patch_exec(monkeypatch, process=proc)
        task = asyncio.ensure_future(run_pool._run_lifecycle(state, None, None))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert proc.terminated == 1
    assert state.status == CANCELLED
    assert state.return_code is None
    assert state.finished_at is not None

def test_slots_limit_parallelism_and_queue_positions(monkeypatch):
    run_pool.reset_pool_for_tests(max_parallel=1)

    async def scenario():
        gate = asyncio.Event()
        started = asyncio.Event()
        procs = [FakeProcess(lines=[b"a\n"], gate=gate, started=started), FakeProcess()]

        async def fake_exec(*args, **kwargs):
            return procs.pop(0)

        monkeypatch.setattr(run_pool.asyncio, "create_subprocess_exec", fake_exec)
        tasks = []

        def spawn(coro, **kwargs):
            tasks.append(asyncio.ensure_future(coro))

        s1 = run_pool.submit(["one"], spawn=spawn)
        s2 = run_pool.submit(["two"], spawn=spawn)
        await started.wait()
        snapshot = {
            "statuses": (s1.status, s2.status),
            "positions": (run_pool.queued_position(s1), run_pool.queued_position(s2)),
            "active": list(run_pool.active_runs()),
            "queued": list(run_pool.queued_runs()),
            "live": list(run_pool.live_runs()),
            "all": list(run_pool.all_runs()),
        }
        gate.set()
        await asyncio.gather(*tasks)
        return s1, s2, snapshot

    s1, s2, snap = asyncio.run(scenario())
    assert snap["statuses"] == (RUNNING, QUEUED)
    assert snap["positions"] == (0, 1)
    assert snap["active"] == [s1]
    assert snap["queued"] == [s2]
    assert snap["live"] == [s1, s2]
    assert snap["all"] == [s1, s2]
    assert s1.status == DONE and s2.status == DONE

# --------------------------------------------------------------------------- _finalize

def test_finalize_terminates_live_process_and_marks_cancelled():
    proc = FakeProcess()
    state = make_state(status=RUNNING)
    state.process = proc
    run_pool._finalize(state)
    assert proc.terminated == 1
    assert state.status == CANCELLED
    assert state.finished_at is not None

def test_finalize_ignores_exited_process_and_final_status():
    proc = FakeProcess(returncode=0)
    state = make_state(status=DONE)
    state.process = proc
    run_pool._finalize(state)
    assert proc.terminated == 0
    assert state.status == DONE

def test_finalize_suppresses_process_lookup_error():
    proc = FakeProcess(terminate_raises=True)
    state = make_state(status=RUNNING)
    state.process = proc
    run_pool._finalize(state)
    assert proc.terminated == 1
    assert state.status == CANCELLED

# --------------------------------------------------------------------------- request_cancel

def test_request_cancel_unknown_run():
    assert run_pool.request_cancel("missing") is False

@pytest.mark.parametrize("status", [DONE, FAILED, CANCELLED])
def test_request_cancel_finished_run(status):
    state = make_state(status=status)
    assert run_pool.request_cancel("r1") is False
    assert state.cancelled is False

def test_request_cancel_queued():
    state = make_state(status=QUEUED)
    assert run_pool.request_cancel("r1") is True
    assert state.cancelled is True
    assert state.status == CANCELLED
    assert state.finished_at is not None

def test_request_cancel_running_without_process_yet():
    state = make_state(status=RUNNING)
    assert run_pool.request_cancel("r1") is True
    assert state.cancelled is True
    assert state.status == RUNNING
    assert state.finished_at is None

def test_request_cancel_running_with_live_process():
    proc = FakeProcess()
    state = make_state(status=RUNNING)
    state.process = proc
    assert run_pool.request_cancel("r1") is True
    assert proc.terminated == 1
    assert state.cancelled is True
    assert state.status == RUNNING  # final status is delivered by the lifecycle

def test_request_cancel_running_process_already_exited():
    proc = FakeProcess(returncode=0)
    state = make_state(status=RUNNING)
    state.process = proc
    assert run_pool.request_cancel("r1") is False
    assert proc.terminated == 0
    assert state.cancelled is True

def test_request_cancel_suppresses_process_lookup_error():
    proc = FakeProcess(terminate_raises=True)
    state = make_state(status=RUNNING)
    state.process = proc
    assert run_pool.request_cancel("r1") is True
    assert proc.terminated == 1

# --------------------------------------------------------------------------- UI helpers

def test_listing_helpers_preserve_insertion_order():
    a = make_state("a", status=DONE)
    b = make_state("b", status=RUNNING)
    c = make_state("c", status=QUEUED)
    d = make_state("d", status=FAILED)
    e = make_state("e", status=QUEUED)
    assert run_pool.all_runs() == [a, b, c, d, e]
    assert run_pool.active_runs() == [b]
    assert run_pool.queued_runs() == [c, e]
    assert run_pool.live_runs() == [b, c, e]
    assert run_pool.queued_position(c) == 1
    assert run_pool.queued_position(e) == 2
    assert run_pool.queued_position(b) == 0
    assert run_pool.queued_position(a) == 0

def test_queued_position_of_unregistered_state_is_zero():
    assert run_pool.queued_position(RunState(run_id="zz", argv=[])) == 0

def test_run_duration_empty_when_not_started():
    assert run_pool.run_duration(RunState(run_id="a", argv=[])) == ""

def test_run_duration_formats_minutes_and_seconds():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    state = RunState(run_id="a", argv=[], started_at=start,
                     finished_at=start + timedelta(seconds=65))
    assert run_pool.run_duration(state) == "1:05"
    state.finished_at = start + timedelta(seconds=5)
    assert run_pool.run_duration(state) == "0:05"
    state.finished_at = start + timedelta(seconds=3661)
    assert run_pool.run_duration(state) == "61:01"

def test_run_duration_uses_now_while_running(monkeypatch):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(run_pool, "_now", lambda: start + timedelta(seconds=125))
    state = RunState(run_id="a", argv=[], started_at=start)
    assert run_pool.run_duration(state) == "2:05"

def test_run_duration_clamps_negative_to_zero():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    state = RunState(run_id="a", argv=[], started_at=start,
                     finished_at=start - timedelta(seconds=10))
    assert run_pool.run_duration(state) == "0:00"

# --------------------------------------------------------------------------- terminate_all_live_processes

def test_terminate_all_terminates_only_live_processes_without_waiting():
    live = FakeProcess()
    exited = FakeProcess(returncode=0)
    s1 = make_state("a", status=RUNNING)
    s1.process = live
    s2 = make_state("b", status=DONE)
    s2.process = exited
    make_state("c", status=QUEUED)  # no process at all

    asyncio.run(run_pool.terminate_all_live_processes())
    assert live.terminated == 1
    assert exited.terminated == 0
    assert live.wait_calls == 0

def test_terminate_all_suppresses_process_lookup_error():
    proc = FakeProcess(terminate_raises=True)
    make_state("a", status=RUNNING).process = proc
    asyncio.run(run_pool.terminate_all_live_processes())
    assert proc.terminated == 1

def test_terminate_all_waits_for_processes_when_grace_given():
    p1, p2 = FakeProcess(), FakeProcess()
    make_state("a", status=RUNNING).process = p1
    make_state("b", status=RUNNING).process = p2
    asyncio.run(run_pool.terminate_all_live_processes(grace_seconds=5))
    assert (p1.terminated, p2.terminated) == (1, 1)
    assert (p1.wait_calls, p2.wait_calls) == (1, 1)

def test_terminate_all_grace_timeout_is_swallowed(monkeypatch):
    timeouts = []

    async def fake_wait_for(aw, timeout):
        timeouts.append(timeout)
        aw.cancel()
        raise TimeoutError()

    monkeypatch.setattr(run_pool.asyncio, "wait_for", fake_wait_for)
    proc = FakeProcess()
    make_state("a", status=RUNNING).process = proc
    asyncio.run(run_pool.terminate_all_live_processes(grace_seconds=1.5))
    assert timeouts == [1.5]
    assert proc.terminated == 1

def test_terminate_all_grace_without_live_processes_does_not_wait(monkeypatch):
    timeouts = []

    async def fake_wait_for(aw, timeout):
        timeouts.append(timeout)

    monkeypatch.setattr(run_pool.asyncio, "wait_for", fake_wait_for)
    make_state("a", status=DONE)
    asyncio.run(run_pool.terminate_all_live_processes(grace_seconds=3))
    assert timeouts == []
