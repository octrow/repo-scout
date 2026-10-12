"""`repo-scout config`: optional settings file, filled interactively."""
import stat

from repo_scout import config, llm


def _answers(*replies):
    it = iter(replies)
    return lambda prompt: next(it)


def test_update_env_keeps_other_lines_and_removes_cleared(tmp_path):
    path = tmp_path / "sub" / ".env"
    path.parent.mkdir()
    path.write_text("# mine\nOTHER_KEY=x\nOMNIROUTE_API_KEY=old\nOMNIROUTE_MODEL=m\n")
    config.update_env(path, {"OMNIROUTE_API_KEY": "new", "OMNIROUTE_MODEL": "", "REPO_SCOUT_GUI_DRAFT": "1"})
    assert path.read_text() == "# mine\nOTHER_KEY=x\nOMNIROUTE_API_KEY=new\nREPO_SCOUT_GUI_DRAFT=1\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_empty_key_skips_the_rest():
    values = config.ask_values({}, _answers(), _answers(""))
    assert values == {llm.KEY_VAR: ""}


def test_enter_keeps_current_and_defaults_are_not_written():
    current = {llm.KEY_VAR: "secret-1234", llm.MODEL_VAR: "custom"}
    values = config.ask_values(current, _answers("", "", "1"), _answers(""))
    assert values == {llm.KEY_VAR: "secret-1234", llm.URL_VAR: "", llm.MODEL_VAR: "custom", llm.GUI_VAR: "1"}


def test_dash_clears_key():
    assert config.ask_values({llm.KEY_VAR: "k"}, _answers(), _answers("-")) == {llm.KEY_VAR: ""}


def test_main_writes_user_env_and_llm_reads_it(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", _answers("", "", ""))
    monkeypatch.setattr(config.getpass, "getpass", _answers("typed-key"))
    config.main([])
    assert llm.available() and llm.model() == llm.DEFAULT_MODEL
    assert "LLM draft is on" in capsys.readouterr().out
