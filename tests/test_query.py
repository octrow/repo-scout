import pytest

from repo_scout.cli import build_query, validate_query

IN = "in:name,description,topics,readme"


def test_defaults_appended():
    q = build_query("whisper", months=6, since="2026-04-14", lang=None)
    assert q == f"whisper {IN} mirror:false pushed:>=2026-04-14"


def test_existing_qualifiers_kept():
    q = build_query("x in:readme mirror:true pushed:>2020-01-01 language:go", months=6, since="s", lang="python")
    assert q == "x in:readme mirror:true pushed:>2020-01-01 language:go"


def test_lang_and_no_months():
    q = build_query("x", months=0, since="s", lang="python")
    assert q == f"x {IN} mirror:false language:python"


def test_validate_ok():
    validate_query("a b language:python topic:x")


def test_validate_text_too_long():
    with pytest.raises(ValueError, match="256"):
        validate_query("w" * 257 + " language:python")


def test_validate_qualifiers_not_counted_in_text():
    validate_query("w " + "pushed:>=2026-01-01 " * 30)


def test_validate_too_many_operators():
    with pytest.raises(ValueError, match="5"):
        validate_query("a AND b OR c NOT d AND e OR f NOT g")


def test_presence_is_by_token():
    q = build_query("plugin:x builtin: foo", months=0, since="s", lang=None)
    assert IN in q
    q = build_query("foo -language:rust", months=0, since="s", lang="go")
    assert q.endswith("language:go")


def test_quoted_qualifier_value_is_not_text():
    validate_query('language:"objective c" ' + "w" * 250)


def test_operators_in_quotes_not_counted():
    validate_query('"a AND b OR c NOT d AND e OR f NOT g"')


def test_url_is_text():
    with pytest.raises(ValueError, match="256"):
        validate_query("https://" + "w" * 260)
