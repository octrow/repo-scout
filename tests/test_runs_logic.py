import pytest
from datetime import datetime
from pathlib import Path

from repo_scout import runs
from repo_scout.gui import eval_logic as el
from repo_scout.gui import runs_logic as rl
from repo_scout.gui.index_page import check_repo


def row(repo: str, **kw) -> dict:
    base = {"repo": repo, "url": f"https://github.com/{repo}", "stars": 5, "forks": 1, "commits": 3, "pushed_days": 9,
            "created": "2026-01-01", "lang": "Python", "desc": f"about {repo}", "score": 4, "fresh": 1, "pop": 2,
            "flags": [], "stop": None, "closeness": 0.5, "source": "query", "seen": ""}
    return {**base, **kw}


ROWS = [row("a/low", closeness=0.4), row("b/top", closeness=0.9, flags=["new"]),
        row("c/dead", stop="dead", source="index", lang="Go"), row("d/none", closeness=None)]


def test_resolve_run_only_inside_runs_dir(tmp_path):
    path = runs.save({"task": "t"}, [], [], datetime(2026, 1, 1))
    assert rl.resolve_run(path.stem) == path
    outside = tmp_path / "secret.json"
    outside.write_text("{}")
    for bad in ("", "..", f"../{outside.stem}", str(outside), "a/b", "a\\b", "nope", "x\x00"):
        assert rl.resolve_run(bad) is None


def test_sorted_rows_by_closeness_then_score():
    rows = [row("a/x", closeness=0.4), row("b/y", closeness=0.9), row("c/z", closeness=None),
            row("d/w", closeness=0.4, score=9)]
    assert [r["repo"] for r in rl.sorted_rows(rows)] == ["b/y", "d/w", "a/x", "c/z"]


def test_filter_rows_hides_stopped_by_default():
    assert [r["repo"] for r in rl.filter_rows(ROWS)] == ["a/low", "b/top", "d/none"]
    assert len(rl.filter_rows(ROWS, show_stopped=True)) == 4


def test_filter_rows_text_source_flag():
    assert [r["repo"] for r in rl.filter_rows(ROWS, text="TOP")] == ["b/top"]
    assert [r["repo"] for r in rl.filter_rows(ROWS, source="index", show_stopped=True)] == ["c/dead"]
    assert [r["repo"] for r in rl.filter_rows(ROWS, flag="new")] == ["b/top"]
    assert [r["repo"] for r in rl.filter_rows(ROWS, text="go", show_stopped=True)] == ["c/dead"]


def test_options_and_table_row():
    assert rl.source_options(ROWS) == [rl.SOURCES_ALL, "query", "index"]
    assert rl.flag_options(ROWS) == [rl.FLAGS_ALL, "new"]
    t = rl.table_row(ROWS[2])
    assert t["flags"] == "dropped: dead" and t["seen"] == "—" and t["close"] == "0.50"
    assert rl.table_row(ROWS[3])["close"] == "—" and rl.table_row(ROWS[1])["flags"] == "new"


@pytest.mark.parametrize(("kind", "note", "expected"), [
    ("watch", "", "→ Inspect"), ("dig", " API port ", "→ Study (API port)"),
    ("drop", "dead", "drop (dead)"), ("doubt", "license", "doubt (license)")])
def test_compose_verdict(kind, note, expected):
    from repo_scout.index import validate_verdict
    text = rl.compose_verdict(kind, note)
    assert text == expected
    validate_verdict("o/r", text, "p", "t")


def test_compose_verdict_needs_note():
    with pytest.raises(ValueError, match="explanation"):
        rl.compose_verdict("drop", "  ")


def test_check_repo():
    assert check_repo("o/r.x") is None
    assert all(check_repo(v) for v in ("", "o", "o/..", "a b/c"))


def test_eval_argv_defaults_to_replay():
    o = el.EvalOptions(sets=[Path("eval/a.toml")], detail=True, top=3)
    argv = el.eval_argv(o, Path("/out.md"))
    assert argv[1:4] == ["-m", "repo_scout", "eval"]
    assert argv[4:] == ["eval/a.toml", "--replay", "--detail", "--top", "3", "--out", "/out.md"]
    assert "--record" in el.eval_argv(el.EvalOptions(sets=[Path("a")], record=True), Path("o"))


def test_eval_argv_fake_stars_and_export():
    argv = el.eval_argv(el.EvalOptions(sets=[Path("a")], fake_stars=True, all_grid=True), Path("o"))
    assert "a" not in argv and "--fake-stars" in argv and "--all-grid" in argv
    assert "--all-grid" not in el.eval_argv(el.EvalOptions(sets=[Path("a")], all_grid=True), Path("o"))
    assert el.export_argv("p", Path("o"))[4:] == ["--export-verdicts", "--project", "p", "--out", "o"]
    assert el.export_argv(None, Path("o"))[-2:] == ["--out", "o"]


def test_eval_errors_and_list_sets(tmp_path):
    assert el.eval_errors(el.EvalOptions()) and not el.eval_errors(el.EvalOptions(fake_stars=True))
    (tmp_path / "a.toml").write_text('name = "a"\ntask = "T"\nanalysis_date = "2026-02-03"\n[[expected]]\nrepo="o/r"\n')
    (tmp_path / "bad.toml").write_text("= nope")
    (tmp_path / "snapshots" / "b").mkdir(parents=True)
    (tmp_path / "b.toml").write_text('name = "b"\ntask = "T2"\n')
    sets = el.list_sets(tmp_path)
    assert [(s.name, s.n_expected, s.snapshot[:4]) for s in sets] == [("a", 1, "2026"), ("b", 0, str(datetime.now().year))]
    assert el.list_sets(tmp_path / "missing") == []


def test_rows_missing_keys_do_not_crash():
    sparse = [{"repo": "a/b"}]
    assert rl.sorted_rows(sparse) and rl.filter_rows(sparse, text="a", flag="x") == []
    assert rl.filter_rows(sparse) == sparse and rl.source_options(sparse) and rl.flag_options(sparse)
    assert rl.table_row(sparse[0])["flags"] == "—"


def test_legacy_russian_values_shown_in_english():
    old = row("a/old", source="второй круг", flags=["новый", "всплеск★ 100% ранних"],
              stop="шум (awesome: имя, описание, topics)")
    r = rl.sorted_rows([old, row("b/dead", stop="мёртвый (200 дн)"), row("c/toy", stop="игрушка (3 комм, 0★)")])
    assert r[0]["source"] == "round 2" and r[0]["flags"] == ["new", "burst★ 100% early"]
    assert r[0]["stop"] == "noise (awesome: name, description, topics)"
    assert [x["stop"] for x in r[1:]] == ["dead (200d)", "toy (3 commits, 0★)"]
    assert rl.sorted_rows([row("d/ok", stop="не по теме (0.41)")])[0]["stop"] == "off-topic (0.41)"


def test_readme_images_point_to_github_and_desc_shortcodes_render():
    md = '![a](./img/a.png) <img src="logo.svg"> ![b](https://x.io/b.png) <img src="/c.png"> ![d](data:image/png;base64,x)'
    out = rl.absolute_images(md, "o/r")
    raw = "https://raw.githubusercontent.com/o/r/HEAD/"
    assert out == (f'![a]({raw}img/a.png) <img src="{raw}logo.svg"> ![b](https://x.io/b.png) '
                   f'<img src="{raw}c.png"> ![d](data:image/png;base64,x)')
    assert rl.plain_desc("fast :rocket: at 10:30:00") == "fast 🚀 at 10:30:00"
