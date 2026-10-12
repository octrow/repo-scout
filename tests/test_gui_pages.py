import asyncio
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from nicegui import ui
from nicegui.events import GenericEventArguments, handle_event
from nicegui.testing import User

from repo_scout import runs
from repo_scout.gui.kit import run_pool
from repo_scout.index import Index, default_path
from tests.test_runs_logic import row

pytestmark = pytest.mark.nicegui_main_file(str(Path(__file__).parent / "gui_main.py"))
NOW = datetime(2026, 5, 1, 12, 30, 5, tzinfo=UTC)
ROWS = [row("a/alpha", closeness=0.9), row("b/beta", closeness=0.5, flags=["new"], source="round 2"),
        row("c/dead", stop="dead")]


def fire(user: User, event: str, *args) -> None:
    """Quasar table event bypassing browser."""
    table = user.find(ui.table).elements.pop()
    for listener in table._event_listeners.values():
        if listener.type == event:
            handle_event(listener.handler, GenericEventArguments(sender=table, client=table.client, args=list(args) if len(args) > 1 else args[0]))


def press(user: User, label: str) -> None:
    """Click newest button with given label."""
    button = max((b for b in user.find(ui.button).elements if b.text == label), key=lambda b: b.id)
    for listener in button._event_listeners.values():
        if listener.type == "click":
            handle_event(listener.handler, GenericEventArguments(sender=button, client=button.client, args=[]))


def make_run(project: str | None = "proj", task: str = "Find thing") -> Path:
    return runs.save({"task": task, "queries": ["q"], "project": project}, ROWS, ["topic-x"], NOW)


def make_index() -> Index:
    idx = Index(default_path(), model="m1")
    meta = {"repo": "a/Alpha", "url": "https://github.com/a/Alpha", "desc": "alpha tool", "topics": [], "stars": 7, "lang": "Go"}
    idx.upsert(meta, "# Alpha readme\n\nHello", np.array([1, 0]))
    idx.upsert({**meta, "repo": "b/beta", "desc": "beta", "lang": "Rust"}, None, np.array([0, 1]))
    return idx


async def test_runs_list_shows_runs_and_empty(user: User) -> None:
    await user.open("/runs")
    await user.should_see("No runs yet")
    make_run()
    (runs.runs_dir() / "broken.json").write_text("{")
    await user.open("/runs")
    rows = user.find(ui.table).elements.pop().rows
    assert any(r["task"] == "Find thing" and r["count"] == "2 / 3" and r["project"] == "proj" for r in rows)
    assert any(r["error"] and "corrupt" in r["task"].lower() for r in rows)


async def test_runs_list_delete_needs_confirmation(user: User) -> None:
    path = make_run()
    await user.open("/runs")
    fire(user, "delete", {"id": path.stem, "task": "Find thing"})
    await user.should_see("Delete run?")
    assert path.exists()
    press(user, "Cancel")
    assert path.exists()
    fire(user, "delete", {"id": path.stem, "task": "Find thing"})
    press(user, "Delete")
    assert not path.exists()
    await user.should_see("No runs yet")


async def test_run_page_header_filters_and_draft_link(user: User) -> None:
    path = make_run()
    await user.open(f"/runs/{path.stem}")
    await user.should_see("Find thing")
    await user.should_see("Round 2: topic-x")
    table = user.find(ui.table).elements.pop()
    assert [r["repo"] for r in table.rows] == ["a/alpha", "b/beta"]
    user.find(ui.switch).elements.pop().set_value(True)
    assert len(table.rows) == 3
    user.find(content="Rerun as draft").click()


async def test_run_page_rejects_foreign_ids(user: User) -> None:
    await user.open("/runs/nope")
    await user.should_see("Run not found")
    runs.runs_dir().mkdir(parents=True, exist_ok=True)
    (runs.runs_dir() / "bad.json").write_text("{")
    await user.open("/runs/bad")
    await user.should_see("corrupt")


async def test_run_panel_and_verdict_updates_seen(user: User) -> None:
    make_index()
    path = make_run()
    await user.open(f"/runs/{path.stem}")
    fire(user, "rowClick", {}, {"repo": "a/alpha"}, 0)
    await user.should_see("Open on GitHub")
    await user.should_see("Alpha readme")
    user.find(content="Set verdict").click()
    await user.should_see("Save verdict")
    sel = next(e for e in user.find(ui.select).elements if e.props.get("label") == "Verdict")
    sel.set_value("drop")
    user.find(content="Save verdict").click()
    await user.should_see("explanation required")
    note = next(e for e in user.find(ui.input).elements if e.props.get("label") == "Drop reason")
    note.set_value("dead")
    user.find(content="Save verdict").click()
    assert Index(default_path(), model="m1").seen(["a/alpha"])["a/alpha"].startswith("proj: drop (dead)")
    table = user.find(ui.table).elements.pop()
    assert next(r for r in table.rows if r["repo"] == "a/alpha")["seen"].startswith("proj: drop (dead)")


async def test_verdict_asks_for_missing_project(user: User) -> None:
    make_index()
    path = make_run(project=None)
    await user.open(f"/runs/{path.stem}")
    fire(user, "rowClick", {}, {"repo": "a/alpha"}, 0)
    user.find(content="Set verdict").click()
    user.find(content="Save verdict").click()
    await user.should_see("Project")
    assert Index(default_path(), model="m1").verdicts() == []
    proj = next(e for e in user.find(ui.input).elements if e.props.get("label") == "Project")
    proj.set_value("newproj")
    user.find(content="Save verdict").click()
    assert Index(default_path(), model="m1").verdicts()[0][:3] == ("newproj", "a/alpha", "→ Inspect")


async def test_panel_without_readme_does_not_fetch(user: User) -> None:
    make_index()
    path = make_run()
    await user.open(f"/runs/{path.stem}")
    fire(user, "rowClick", {}, {"repo": "b/beta"}, 0)
    await user.should_see("No README in Index")


async def test_index_page_lists_filters_and_forgets(user: User) -> None:
    await user.open("/index")
    await user.should_see("No repos in Index yet")
    idx = make_index()
    idx.add_verdict("a/alpha", "→ Inspect", "proj", "task", NOW)
    await user.open("/index")
    table = user.find(ui.table).elements.pop()
    assert [r["name"] for r in table.rows] == ["a/Alpha", "b/beta"]
    assert table.rows[0]["seen"].startswith("proj: → Inspect")
    sel = next(e for e in user.find(ui.select).elements if e.props.get("aria-label") == "Project")
    sel.set_value("proj")
    assert [r["name"] for r in table.rows] == ["a/Alpha"]
    sel.set_value("All projects")
    fire(user, "rowClick", {}, {"key": "b/beta"}, 0)
    press(user, "Forget")
    await user.should_see("Forget repo?")
    assert len(Index(default_path(), model="m1").rows()) == 2
    press(user, "Forget")
    assert [r["name"] for r in Index(default_path(), model="m1").rows()] == ["a/Alpha"]


async def test_index_rename_validates(user: User) -> None:
    idx = make_index()
    idx.add_verdict("b/beta", "→ Inspect", "proj", "task", NOW)
    await user.open("/index")
    fire(user, "rowClick", {}, {"key": "b/beta"}, 0)
    press(user, "Rename")
    new = next(e for e in user.find(ui.input).elements if e.props.get("label") == "New name")
    new.set_value("bad name")
    press(user, "Rename")
    assert [r["name"] for r in Index(default_path(), model="m1").rows()] == ["a/Alpha", "b/beta"]
    await user.should_see("Must be owner/repo format")
    new.set_value("o/new")
    press(user, "Rename")
    assert Index(default_path(), model="m1").verdicts()[0][1] == "o/new"


async def test_eval_page_cards_and_run(user: User, monkeypatch) -> None:
    calls = []

    def fake_submit(argv, *, label="", meta=None, **kw):
        out = Path(argv[-1])
        out.write_text("# Report\n\n| set |\n|---|\n| buy-smarter |\n", encoding="utf-8")
        state = run_pool.RunState(run_id="e1", argv=argv, label=label, meta=meta or {}, status=run_pool.DONE)
        run_pool.RUNS["e1"] = state
        calls.append(argv)
        return state

    monkeypatch.setattr(run_pool, "submit", fake_submit)
    run_pool.RUNS.clear()
    await user.open("/eval")
    await user.should_see("buy-smarter")
    user.find(content="Launch eval").click()
    user.notify.contains("Select at least one set")
    assert not calls
    next(c for c in user.find(ui.checkbox).elements if c.text == "buy-smarter").set_value(True)
    user.find(content="Launch eval").click()
    assert calls[0][1:4] == ["-m", "repo_scout", "eval"] and calls[0][4].endswith("buy-smarter.toml")
    assert "--replay" in calls[0] and calls[0][-2] == "--out"
    await asyncio.sleep(1.5)
    await user.should_see("Report")
    await user.should_see("buy-smarter")
    run_pool.RUNS.clear()
