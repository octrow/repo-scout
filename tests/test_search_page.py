import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from repo_scout import cli, runs
from repo_scout.gui.kit import run_pool

pytestmark = pytest.mark.nicegui_main_file(str(Path(__file__).parent / "gui_main.py"))


def _values(user: User) -> dict:
    return {e.props.get("label"): e.value for e in user.find(ui.input).elements}


async def test_page_opens_with_nav_and_empty_form(user: User) -> None:
    await user.open("/")
    await user.should_see("Поиск")
    for nav in ("Прогоны", "Индекс", "Eval"):
        await user.should_see(nav)
    await user.should_see("Заполните задачу и запросы")


async def test_form_fills_from_draft(user: User) -> None:
    params = cli.search_params(cli._parser().parse_args(["--task", "Draft task", "--lang", "go", "qa", "qb"]))
    path = runs.save(params, [], [], datetime(2026, 1, 1))
    await user.open(f"/?draft=run:{path.stem}")
    v = _values(user)
    assert v["Задача (англ.)"] == "Draft task" and v["Запросы"] == "qa\nqb" and v["Язык"] == "go"
    await user.should_see("--lang=go")


async def test_draft_by_path_is_ignored(user: User) -> None:
    params = cli.search_params(cli._parser().parse_args(["--task", "Secret task", "qa"]))
    path = runs.save(params, [], [], datetime(2026, 1, 1))
    for draft in (f"run:{path}", "run:../x", f"run:{path.stem}/.."):
        await user.open(f"/?draft={draft}")
        assert _values(user)["Задача (англ.)"] == ""


async def test_paste_command_fills_fields(user: User) -> None:
    await user.open("/")
    user.find(content="Вставить команду").click()
    area = next(e for e in user.find(ui.input).elements if e.props.get("label") == "Команда")
    area.value = 'repo-scout --task "Pasted task" --months=2 "q one" "q two"'
    user.find(content="Применить").click()
    v = _values(user)
    assert v["Задача (англ.)"] == "Pasted task" and v["Запросы"] == "q one\nq two"
    await user.should_see("--months=2")


async def test_paste_invalid_command_shows_error_in_dialog(user: User) -> None:
    await user.open("/")
    user.find(content="Вставить команду").click()
    area = next(e for e in user.find(ui.input).elements if e.props.get("label") == "Команда")
    area.value = "repo-scout --nope"
    user.find(content="Применить").click()
    await user.should_see("the following arguments")


async def test_invalid_regex_shows_error(user: User) -> None:
    await user.open("/")
    must = next(e for e in user.find(ui.input).elements if e.props.get("label") == "Обязательные слова")
    must.value = "("
    assert must.validate() is False
    await user.should_see("--must")


async def test_run_calls_submit_with_argv_and_notifies_on_done(user: User, monkeypatch) -> None:
    calls = []

    def fake_submit(argv, *, label="", meta=None, **kw):
        state = run_pool.RunState(run_id="r1", argv=argv, label=label, meta=meta or {}, status=run_pool.DONE)
        run_pool.RUNS["r1"] = state
        calls.append(state)
        return state

    monkeypatch.setattr(run_pool, "submit", fake_submit)
    run_pool.RUNS.clear()
    await user.open("/")
    by_label = {e.props.get("label"): e for e in user.find(ui.input).elements}
    by_label["Задача (англ.)"].value = "Real task"
    by_label["Запросы"].value = "alpha\nbeta"
    user.find(content="Запустить").click()
    assert len(calls) == 1
    argv, out = calls[0].argv, calls[0].meta["out"]
    a = cli._parser().parse_args(argv[3:])
    assert argv[1:3] == ["-m", "repo_scout"] and a.out == out
    assert a.queries == ["alpha", "beta"] and Path(out).parent == runs.runs_dir()
    user.notify.contains("Поиск запущен")
    await asyncio.sleep(1.5)  # таймер страницы замечает завершение
    user.notify.contains(f"/runs/{Path(out).stem}")
    await user.should_see("Real task")
    run_pool.RUNS.clear()


async def test_run_with_empty_form_does_not_submit(user: User, monkeypatch) -> None:
    monkeypatch.setattr(run_pool, "submit", lambda *a, **k: pytest.fail("submit"))
    await user.open("/")
    user.find(content="Запустить").click()
    user.notify.contains("Опишите задачу")


async def test_need_field_hidden_without_key(user: User) -> None:
    await user.open("/")
    await user.should_not_see("Черновик из LLM")


async def test_llm_draft_fills_form_without_search(user: User, monkeypatch) -> None:
    from repo_scout import llm
    monkeypatch.setenv("OMNIROUTE_API_KEY", "k")
    monkeypatch.setattr(run_pool, "submit", lambda *a, **k: pytest.fail("submit"))
    monkeypatch.setattr(llm, "draft", lambda need: llm.Draft("Drafted task", ("qa", "qb"), "go", ("m",), ("e",)))
    await user.open("/")
    by_label = {e.props.get("label"): e for e in user.find(ui.input).elements}
    by_label["Что ищем (любым языком)"].value = "найти штуку"
    user.find(content="Черновик из LLM").click()
    await asyncio.sleep(0.5)
    v = _values(user)
    assert v["Задача (англ.)"] == "Drafted task" and v["Запросы"] == "qa\nqb" and v["Язык"] == "go"
    await user.should_see("--need")


async def test_llm_draft_error_notifies_without_internals(user: User, monkeypatch) -> None:
    from repo_scout import llm

    def boom(need):
        raise llm.LLMError("LLM недоступна")
    monkeypatch.setenv("OMNIROUTE_API_KEY", "k")
    monkeypatch.setattr(llm, "draft", boom)
    await user.open("/")
    by_label = {e.props.get("label"): e for e in user.find(ui.input).elements}
    by_label["Что ищем (любым языком)"].value = "x"
    button = user.find(content="Черновик из LLM")
    button.click()
    await asyncio.sleep(0.5)
    user.notify.contains("Подробности в логе")
    assert not any("LLM недоступна" in str(m) for m in user.notify.messages)
    assert all(b.enabled for b in button.elements)
