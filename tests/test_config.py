"""`repo-scout config`: optional advanced-mode settings, filled interactively."""
import os
import stat

from repo_scout import config, llm, systemone


def _answers(*replies):
    it = iter(replies)
    return lambda prompt: next(it)


def test_update_env_keeps_other_lines_and_removes_cleared(tmp_path):
    path = tmp_path / "sub" / ".env"
    path.parent.mkdir()
    path.write_text("# mine\nOTHER_KEY=x\nLLM_API_KEY=old\nLLM_MODEL=m\n")
    config.update_env(path, {"LLM_API_KEY": "new", "LLM_MODEL": "", "REPO_SCOUT_GUI_DRAFT": "1"})
    assert path.read_text() == "# mine\nOTHER_KEY=x\nLLM_API_KEY=new\nREPO_SCOUT_GUI_DRAFT=1\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_empty_keys_skip_both_sections():
    values = config.ask_values({}, _answers(), _answers("", ""))
    assert values[llm.KEY_VAR] == "" and values[systemone.KEY_VAR] == ""
    assert llm.MODEL_VAR not in values


def test_enter_keeps_current_and_defaults_are_not_written():
    current = {llm.KEY_VAR: "secret-1234", llm.MODEL_VAR: "custom", systemone.KEY_VAR: "ts-key"}
    values = config.ask_values(current, _answers("", "", "1"), _answers("", ""))
    assert values[llm.KEY_VAR] == "secret-1234" and values[llm.URL_VAR] == "" and values[llm.MODEL_VAR] == "custom"
    assert values[llm.GUI_VAR] == "1" and values[systemone.KEY_VAR] == "ts-key"


def test_older_alias_is_read_then_replaced():
    values = config.ask_values({"OMNIROUTE_API_KEY": "old-key"}, _answers("", "", ""), _answers("", "-"))
    assert values[llm.KEY_VAR] == "old-key" and values["OMNIROUTE_API_KEY"] == ""


def test_main_writes_user_env_and_both_modes_read_it(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", _answers("", "", ""))
    monkeypatch.setattr(config.getpass, "getpass", _answers("typed-key", "ts-key"))
    config.main([])
    assert llm.available() and llm.model() == llm.DEFAULT_MODEL
    assert systemone.available()
    assert "OmniRoute" in capsys.readouterr().out


def test_update_env_drops_duplicate_keys(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=1\nB=x\nA=2\nC=3\nA=4\n")
    config.update_env(path, {"A": "new", "C": ""})
    assert path.read_text() == "A=new\nB=x\n"


def test_update_env_never_world_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "chmod", lambda *a: None)  # mode must be right without the later chmod
    old = os.umask(0)
    try:
        config.update_env(tmp_path / ".env", {"A": "1"})
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600
