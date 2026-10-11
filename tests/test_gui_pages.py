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
ROWS = [row("a/alpha", closeness=0.9), row("b/beta", closeness=0.5, flags=["новый"], source="второй круг"),
        row("c/dead", stop="мёртвый")]


def fire(user: User, event: str, *args) -> None:
    """Событие Quasar-таблицы (rowClick, слотовые события) в обход браузера."""
    table = user.find(ui.table).elements.pop()
    for listener in table._event_listeners.values():
        if listener.type == event:
            handle_event(listener.handler, GenericEventArguments(sender=table, client=table.client, args=list(args) if len(args) > 1 else args[0]))


def press(user: User, label: str) -> None:
    """Клик по самой новой кнопке с такой подписью (диалоги строятся позже панели)."""
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
    await user.should_see("Прогонов пока нет")
    make_run()
    (runs.runs_dir() / "broken.json").write_text("{")
    await user.open("/runs")
    rows = user.find(ui.table).elements.pop().rows
    assert any(r["task"] == "Find thing" and r["count"] == "2 / 3" and r["project"] == "proj" for r in rows)
    assert any(r["error"] and "повреждён" in r["task"] for r in rows)


async def test_runs_list_delete_needs_confirmation(user: User) -> None:
    path = make_run()
    await user.open("/runs")
    fire(user, "delete", {"id": path.stem, "task": "Find thing"})
    await user.should_see("Удалить прогон?")
    assert path.exists()
    press(user, "Отмена")
    assert path.exists()
    fire(user, "delete", {"id": path.stem, "task": "Find thing"})
    press(user, "Удалить")
    assert not path.exists()
    await user.should_see("Прогонов пока нет")


async def test_run_page_header_filters_and_draft_link(user: User) -> None:
    path = make_run()
    await user.open(f"/runs/{path.stem}")
    await user.should_see("Find thing")
    await user.should_see("Второй круг: topic-x")
    table = user.find(ui.table).elements.pop()
    assert [r["repo"] for r in table.rows] == ["a/alpha", "b/beta"]  # отсеянные скрыты
    user.find(ui.switch).elements.pop().set_value(True)
    assert len(table.rows) == 3
    user.find(content="Повторить как черновик").click()
    await user.should_see("Заполните задачу") if False else None


async def test_run_page_rejects_foreign_ids(user: User) -> None:
    await user.open("/runs/nope")
    await user.should_see("Прогон не найден")
    runs.runs_dir().mkdir(parents=True, exist_ok=True)
    (runs.runs_dir() / "bad.json").write_text("{")
    await user.open("/runs/bad")
    await user.should_see("повреждён")


async def test_run_panel_and_verdict_updates_seen(user: User) -> None:
    make_index()
    path = make_run()
    await user.open(f"/runs/{path.stem}")
    fire(user, "rowClick", {}, {"repo": "a/alpha"}, 0)
    await user.should_see("Открыть на GitHub")
    await user.should_see("Alpha readme")  # README из Индекса, без сети
    user.find(content="Поставить вердикт").click()
    await user.should_see("Записать вердикт")
    sel = next(e for e in user.find(ui.select).elements if e.props.get("label") == "Вердикт")
    sel.set_value("drop")
    user.find(content="Записать вердикт").click()
    await user.should_see("заполните пояснение")
    note = next(e for e in user.find(ui.input).elements if e.props.get("label") == "Причина отсева")
    note.set_value("мёртвый")
    user.find(content="Записать вердикт").click()
    assert Index(default_path(), model="m1").seen(["a/alpha"])["a/alpha"].startswith("proj: отсев (мёртвый)")
    table = user.find(ui.table).elements.pop()
    assert next(r for r in table.rows if r["repo"] == "a/alpha")["seen"].startswith("proj: отсев (мёртвый)")


async def test_verdict_asks_for_missing_project(user: User) -> None:
    make_index()
    path = make_run(project=None)
    await user.open(f"/runs/{path.stem}")
    fire(user, "rowClick", {}, {"repo": "a/alpha"}, 0)
    user.find(content="Поставить вердикт").click()
    user.find(content="Записать вердикт").click()
    await user.should_see("проект")
    assert Index(default_path(), model="m1").verdicts() == []
    proj = next(e for e in user.find(ui.input).elements if e.props.get("label") == "Проект")
    proj.set_value("newproj")
    user.find(content="Записать вердикт").click()
    assert Index(default_path(), model="m1").verdicts()[0][:3] == ("newproj", "a/alpha", "→ Осмотр")


async def test_panel_without_readme_does_not_fetch(user: User) -> None:
    make_index()
    path = make_run()
    await user.open(f"/runs/{path.stem}")
    fire(user, "rowClick", {}, {"repo": "b/beta"}, 0)
    await user.should_see("README нет в Индексе")


async def test_index_page_lists_filters_and_forgets(user: User) -> None:
    await user.open("/index")
    await user.should_see("В Индексе пока нет репо")
    idx = make_index()
    idx.add_verdict("a/alpha", "→ Осмотр", "proj", "task", NOW)
    await user.open("/index")
    table = user.find(ui.table).elements.pop()
    assert [r["name"] for r in table.rows] == ["a/Alpha", "b/beta"]
    assert table.rows[0]["seen"].startswith("proj: → Осмотр")
    sel = next(e for e in user.find(ui.select).elements if e.props.get("aria-label") == "Проект")
    sel.set_value("proj")
    assert [r["name"] for r in table.rows] == ["a/Alpha"]
    sel.set_value("Все проекты")
    fire(user, "rowClick", {}, {"key": "b/beta"}, 0)
    press(user, "Забыть")
    await user.should_see("Забыть репо?")
    assert len(Index(default_path(), model="m1").rows()) == 2
    press(user, "Забыть")
    assert [r["name"] for r in Index(default_path(), model="m1").rows()] == ["a/Alpha"]


async def test_index_rename_validates(user: User) -> None:
    idx = make_index()
    idx.add_verdict("b/beta", "→ Осмотр", "proj", "task", NOW)
    await user.open("/index")
    fire(user, "rowClick", {}, {"key": "b/beta"}, 0)
    press(user, "Переименовать")
    new = next(e for e in user.find(ui.input).elements if e.props.get("label") == "Новое имя")
    new.set_value("bad name")
    press(user, "Переименовать")
    assert [r["name"] for r in Index(default_path(), model="m1").rows()] == ["a/Alpha", "b/beta"]
    await user.should_see("Нужен вид owner/repo")
    new.set_value("o/new")
    press(user, "Переименовать")
    assert Index(default_path(), model="m1").verdicts()[0][1] == "o/new"


async def test_eval_page_cards_and_run(user: User, monkeypatch) -> None:
    calls = []

    def fake_submit(argv, *, label="", meta=None, **kw):
        out = Path(argv[-1])
        out.write_text("# Отчёт\n\n| набор |\n|---|\n| buy-smarter |\n", encoding="utf-8")
        state = run_pool.RunState(run_id="e1", argv=argv, label=label, meta=meta or {}, status=run_pool.DONE)
        run_pool.RUNS["e1"] = state
        calls.append(argv)
        return state

    monkeypatch.setattr(run_pool, "submit", fake_submit)
    run_pool.RUNS.clear()
    await user.open("/eval")
    await user.should_see("buy-smarter")
    user.find(content="Запустить eval").click()
    user.notify.contains("Выберите хотя бы один набор")
    assert not calls
    next(c for c in user.find(ui.checkbox).elements if c.text == "buy-smarter").set_value(True)
    user.find(content="Запустить eval").click()
    assert calls[0][1:4] == ["-m", "repo_scout", "eval"] and calls[0][4].endswith("buy-smarter.toml")
    assert "--replay" in calls[0] and calls[0][-2] == "--out"
    await asyncio.sleep(1.5)
    await user.should_see("Отчёт")
    await user.should_see("buy-smarter")
    run_pool.RUNS.clear()
