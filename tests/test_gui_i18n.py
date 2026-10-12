"""GUI language switch: English by default, Russian on REPO_SCOUT_LANG=ru, every t("...") has a translation."""
import ast
from pathlib import Path

import pytest
from nicegui.testing import User

from repo_scout import llm
from repo_scout.gui import eval_page, i18n, index_page, run_view, runs_logic, runs_page, search_page, shell

GUI = Path(i18n.__file__).parent


def _t_literals() -> set[str]:
    out = set()
    for path in GUI.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                out.add(node.args[0].value)
    return out


def _constant_labels() -> set[str]:
    """Labels kept in module constants and translated at render time."""
    cols = [*run_view.COLUMNS, *runs_page.COLUMNS, *index_page.COLUMNS]
    return ({c["label"] for c in cols if c["label"] not in ("", "★")} | {m for m, _ in run_view.METRICS if m != "★"}
            | set(search_page.NUMBER_LABELS.values()) | set(search_page.FLAG_LABELS.values())
            | set(eval_page.FLAG_LABELS.values()) | set(shell.PAGES.values())
            | set(runs_logic.NOTE_LABELS.values()) | {"Drop", "Doubt", search_page.COMMAND_HINT, search_page.LLM_FAILED,
                                                       runs_logic.SOURCES_ALL, runs_logic.FLAGS_ALL, runs_logic.ALL,
                                                       index_page.ALL_PROJECTS})


def test_every_gui_string_has_a_russian_translation():
    missing = (_t_literals() | _constant_labels()) - set(i18n.RU)
    assert not missing, sorted(missing)


def test_translations_are_plain():
    for en, ru in i18n.RU.items():
        assert ru.strip(), en
        assert "—" not in ru and "–" not in ru, en
        assert en.count("{") == ru.count("{"), en  # same placeholders


def test_english_by_default_russian_on_setting(monkeypatch):
    assert i18n.current() == "en" and i18n.t("Search") == "Search"
    monkeypatch.setenv("REPO_SCOUT_LANG", "ru")
    assert i18n.t("Search") == "Поиск"
    assert i18n.t("not in the dictionary") == "not in the dictionary"
    monkeypatch.setenv("REPO_SCOUT_LANG", "fr")
    assert i18n.current() == "en"


def test_set_lang_saves_the_choice(monkeypatch):
    monkeypatch.setenv("REPO_SCOUT_LANG", "en")  # restored after the test; set_lang writes os.environ
    i18n.set_lang("ru")
    assert "REPO_SCOUT_LANG=ru" in llm.user_env_path().read_text()
    monkeypatch.delenv("REPO_SCOUT_LANG")
    assert i18n.current() == "ru"  # read back from the settings file
    i18n.set_lang("en")
    assert "REPO_SCOUT_LANG" not in llm.user_env_path().read_text()


@pytest.mark.nicegui_main_file(str(Path(__file__).parent / "gui_main.py"))
async def test_runs_page_in_russian(user: User, monkeypatch) -> None:
    monkeypatch.setenv("REPO_SCOUT_LANG", "ru")
    await user.open("/runs")
    await user.should_see("Прогоны")
    await user.should_see("Прогонов пока нет. Запустите поиск на странице Поиск.")


def test_kit_texts_follow_the_switch(monkeypatch):
    from repo_scout.gui import i18n
    from repo_scout.gui.kit import texts
    monkeypatch.setenv("REPO_SCOUT_LANG", "ru")
    i18n.sync_kit()
    assert texts.tr("rows_per_page") == "Строк на странице:"
    monkeypatch.setenv("REPO_SCOUT_LANG", "en")
    i18n.sync_kit()
    assert texts.tr("rows_per_page") == "Rows per page:"
