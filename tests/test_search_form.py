from datetime import datetime
from pathlib import Path

from repo_scout import cli, runs
from repo_scout.gui import search_form as sf


def _state(**kw) -> dict:
    return {**sf.default_state(), "task": "Find a thing", "queries": "whisper live\ntopic:asr", **kw}


def test_default_state_matches_cli_defaults() -> None:
    s = sf.default_state()
    assert s["months"] == 6 and s["limit"] == 50 and s["task"] == "" and s["queries"] == ""


def test_state_params_roundtrip_through_cli() -> None:
    state = _state(lang="python", must="foo\nbar", months=3, no_round2=True, project="p")
    params = sf.state_to_params(state)
    again = cli.search_params(cli.parse_command(sf.command_text(state)))
    assert again == params
    assert sf.params_to_state(params) == state


def test_command_text_needs_task_and_queries() -> None:
    assert sf.command_text(sf.default_state()) is None
    assert sf.command_text(_state()).startswith("repo-scout ")


def test_run_argv_uses_module_and_out(tmp_path: Path) -> None:
    argv = sf.run_argv(_state(), tmp_path / "r.json")
    a = cli._parser().parse_args(argv[3:])
    assert argv[1:3] == ["-m", "repo_scout"] and a.out == str(tmp_path / "r.json")
    assert a.queries == sf.state_to_params(_state())["queries"]


def test_out_path_in_runs_dir() -> None:
    p = sf.out_path("Find A Thing", datetime(2026, 1, 2, 3, 4, 5))
    assert p.parent == runs.runs_dir() and p.name == "20260102-030405-find-a-thing.json"


def test_form_errors() -> None:
    assert sf.form_errors(sf.default_state()) == ["Add a task description", "Add at least one query"]
    assert sf.form_errors(_state(must="(")) and "--must" in sf.form_errors(_state(must="("))[0]
    assert sf.form_errors(_state()) == []


def test_check_queries_reports_operator_overflow() -> None:
    assert sf.check_queries(" OR ".join("abcdefghij")) is not None
    assert sf.check_queries("fine query") is None


def test_agent_prompt_has_task_and_one_line_rule() -> None:
    p = sf.agent_prompt("  my task ")
    assert "my task" in p and "ONE line" in p and "stars:" in p


def test_drafts_from_runs_and_eval(tmp_path: Path) -> None:
    params = cli.search_params(cli._parser().parse_args(["--task", "T1", "--project", "pp", "q1", "q2"]))
    runs.save(params, [], [], datetime(2026, 1, 1))
    (tmp_path / "ev.toml").write_text('name="ev"\ntask="E task"\nqueries=["a","b"]\nlang="go"\nmust=["x"]\nexclude=[]\n')
    (runs.runs_dir() / "broken.json").write_text("{")
    drafts = sf.list_drafts(tmp_path)
    assert [d.key.split(":")[0] for d in drafts] == ["run", "eval"]
    run_state, eval_state = (sf.load_draft(d) for d in drafts)
    assert run_state["task"] == "T1" and run_state["queries"] == "q1\nq2" and run_state["project"] == "pp"
    assert eval_state["lang"] == "go" and eval_state["must"] == "x" and eval_state["project"] == "ev"


def test_project_suggestions_merge_without_duplicates(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("")
    assert sf.project_suggestions(["beta", "gamma"], tmp_path) == ["beta", "gamma", "alpha"]
    assert sf.project_suggestions(["x"], tmp_path / "missing") == ["x"]
