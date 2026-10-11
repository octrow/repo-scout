import json

import pytest

from repo_scout import cli, github, llm

GOOD = {"task": "Find live speech transcription tools.", "queries": ["whisper live", "asr topic:asr language:python"],
        "lang": "python", "must": ["whisper"], "exclude": ["^$x"]}


def reply(content: str, tokens: int = 10) -> dict:
    return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": tokens}}


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_API_KEY", "secret-key")
    yield
    github.configure(None, None)


def fake_post(monkeypatch, *contents: str) -> list:
    sent = []
    it = iter(contents)
    monkeypatch.setattr(llm, "_post", lambda messages: sent.append(messages) or reply(next(it)))
    return sent


def test_available_follows_key(monkeypatch):
    assert llm.available()
    monkeypatch.delenv("OMNIROUTE_API_KEY")
    assert not llm.available()


def test_env_file_used_but_real_env_wins(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# c\n\nOMNIROUTE_API_KEY="from-file"\nOMNIROUTE_MODEL=\'m1\'\nexport OMNIROUTE_BASE_URL=http://x/v1\n')
    monkeypatch.setattr(llm, "ENV_FILE", env)
    assert llm._setting(llm.KEY_VAR) == "secret-key"
    assert llm._setting(llm.MODEL_VAR) == "m1" and llm.model() == "m1"
    monkeypatch.delenv("OMNIROUTE_API_KEY")
    assert llm._setting(llm.KEY_VAR) == "from-file"
    assert llm._setting(llm.URL_VAR) == "http://x/v1"


def test_defaults(monkeypatch):
    assert llm.model() == "free-stack" and llm._setting(llm.URL_VAR, llm.DEFAULT_URL) == "http://127.0.0.1:20128/v1"


def test_draft_parses_fenced_json(monkeypatch):
    fake_post(monkeypatch, "Вот:\n```json\n" + json.dumps(GOOD) + "\n```")
    d = llm.draft("живая расшифровка речи")
    assert d == llm.Draft(GOOD["task"], tuple(GOOD["queries"]), "python", ("whisper",), ("^$x",))
    assert llm.last_stats["tokens"] == 10


def test_invalid_then_retry_includes_error(monkeypatch):
    bad = {**GOOD, "queries": ["x" * 300]}
    sent = fake_post(monkeypatch, json.dumps(bad), json.dumps(GOOD))
    assert llm.draft("need").queries == tuple(GOOD["queries"])
    assert len(sent) == 2 and "Invalid" in sent[1][-1]["content"] and "256" in sent[1][-1]["content"]


def test_twice_invalid_raises_without_key(monkeypatch):
    fake_post(monkeypatch, "not json", "still not")
    with pytest.raises(llm.LLMError) as e:
        llm.draft("need")
    assert "secret-key" not in str(e.value)


@pytest.mark.parametrize("patch", [
    {"task": 5}, {"task": "x" * 601}, {"queries": []}, {"queries": "a"}, {"queries": [str(i) for i in range(11)]},
    {"must": ["("]}, {"lang": 3}, {"queries": ["a OR b OR c OR d OR e OR f OR g"]}])
def test_parse_rejects(patch):
    with pytest.raises(ValueError):
        llm.parse_draft(json.dumps({**GOOD, **patch}))


def test_no_key_error_names_variables(monkeypatch):
    monkeypatch.delenv("OMNIROUTE_API_KEY")
    with pytest.raises(llm.LLMError, match="OMNIROUTE_API_KEY"):
        llm._post([])


def test_http_error_hides_key(monkeypatch):
    import urllib.error

    def boom(*a, **k):
        raise urllib.error.HTTPError("u", 401, "no", {}, None)
    monkeypatch.setattr(llm._OPENER, "open", boom)
    with pytest.raises(llm.LLMError) as e:
        llm._post([])
    assert "401" in str(e.value) and "secret-key" not in str(e.value)


def test_record_then_replay(monkeypatch, tmp_path):
    fake_post(monkeypatch, json.dumps(GOOD))
    github.configure("record", tmp_path)
    first = llm.draft("need")
    assert len(list((tmp_path / "llm").glob("*.json.gz"))) == 1
    monkeypatch.setattr(llm, "_post", lambda m: pytest.fail("network in replay"))
    monkeypatch.delenv("OMNIROUTE_API_KEY")
    github.configure("replay", tmp_path)
    assert llm.draft("need") == first and llm.last_stats["tokens"] == 10


def test_replay_without_snapshot(tmp_path):
    github.configure("replay", tmp_path)
    with pytest.raises(llm.LLMError, match="снапшота"):
        llm.draft("need")


def test_cli_draft_prints_one_line(monkeypatch, capsys):
    fake_post(monkeypatch, json.dumps(GOOD))
    monkeypatch.setattr("sys.argv", ["repo-scout", "draft", "расшифровка речи"])
    cli.main()
    line = capsys.readouterr().out.strip()
    assert "\n" not in line
    a = cli.parse_command(line)
    assert a.task == GOOD["task"] and a.queries == GOOD["queries"] and a.need == "расшифровка речи"
    assert a.lang == "python" and a.must == ["whisper"]


def test_cli_draft_without_key(monkeypatch):
    monkeypatch.delenv("OMNIROUTE_API_KEY")
    monkeypatch.setattr("sys.argv", ["repo-scout", "draft", "x"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert "OMNIROUTE_API_KEY" in str(e.value)


def test_need_roundtrips_through_command():
    p = cli.search_params(cli.parse_command('repo-scout --task t --need "расшифровка речи" -- q'))
    assert p["need"] == "расшифровка речи"
    assert cli.parse_command("repo-scout " + " ".join(__import__("shlex").quote(t) for t in cli.to_argv(p))).need == p["need"]


@pytest.mark.parametrize("lang", ["Python or Go", "a" * 31, "py thon"])
def test_parse_rejects_bad_lang(lang):
    with pytest.raises(ValueError):
        llm.parse_draft(json.dumps({**GOOD, "lang": lang}))


@pytest.mark.parametrize("lang", ["none", "Any", "NULL", "N/A", "", " "])
def test_lang_placeholders_mean_none(lang):
    assert llm.parse_draft(json.dumps({**GOOD, "lang": lang})).lang is None


@pytest.mark.parametrize("lang", ["C++", "C#", "Python", "Objective-C", "F#"])
def test_lang_accepts_names(lang):
    assert llm.parse_draft(json.dumps({**GOOD, "lang": lang})).lang == lang


@pytest.mark.parametrize("rx", [r"(\w+\s?)+parser", r"(a*)*", r"((a+)b)+", r"(a{1,3}){2,}"])
def test_parse_rejects_redos(rx):
    with pytest.raises(ValueError, match="ReDoS"):
        llm.parse_draft(json.dumps({**GOOD, "must": [rx]}))
    with pytest.raises(ValueError, match="ReDoS"):
        llm.parse_draft(json.dumps({**GOOD, "exclude": [rx]}))


@pytest.mark.parametrize("rx", ["kaspi|ozon", r"\bmcp\b", r"(foo|bar)+", r"(ab)+c", r"[+*]+x", r"\w+(?:x)"])
def test_parse_accepts_safe_regexes(rx):
    assert llm.parse_draft(json.dumps({**GOOD, "must": [rx]})).must == (rx,)


def test_record_does_not_cache_failed_reply(monkeypatch, tmp_path):
    fake_post(monkeypatch, "not json", "still not")
    github.configure("record", tmp_path)
    with pytest.raises(llm.LLMError):
        llm.draft("need")
    assert not list((tmp_path / "llm").glob("*.json.gz"))
    fake_post(monkeypatch, json.dumps(GOOD))
    assert llm.draft("need").task == GOOD["task"]


def test_record_persists_retry_chain_after_success(monkeypatch, tmp_path):
    fake_post(monkeypatch, "not json", json.dumps(GOOD))
    github.configure("record", tmp_path)
    first = llm.draft("need")
    assert len(list((tmp_path / "llm").glob("*.json.gz"))) == 2
    monkeypatch.setattr(llm, "_post", lambda m: pytest.fail("network in replay"))
    github.configure("replay", tmp_path)
    assert llm.draft("need") == first


@pytest.mark.parametrize("body", [[1, 2], "str", 5])
def test_non_dict_body_is_llm_error(monkeypatch, body):
    import io
    monkeypatch.setattr(llm._OPENER, "open", lambda *a, **k: io.BytesIO(json.dumps(body).encode()))
    with pytest.raises(llm.LLMError) as e:
        llm._post([])
    assert "secret-key" not in str(e.value)


@pytest.mark.parametrize("exc", ["IncompleteRead", "BadStatusLine"])
def test_http_exception_is_llm_error(monkeypatch, exc):
    import http.client

    def boom(*a, **k):
        raise getattr(http.client, exc)(b"x") if exc == "IncompleteRead" else http.client.BadStatusLine("x")
    monkeypatch.setattr(llm._OPENER, "open", boom)
    with pytest.raises(llm.LLMError) as e:
        llm._post([])
    assert "secret-key" not in str(e.value)


@pytest.mark.parametrize("usage", [{"total_tokens": "abc"}, {"total_tokens": [1]}, "oops", 7, {"total_tokens": None}])
def test_bad_usage_counts_as_zero(monkeypatch, usage):
    r = reply(json.dumps(GOOD))
    r["usage"] = usage
    monkeypatch.setattr(llm, "_post", lambda m: r)
    assert llm.draft("need").task == GOOD["task"] and llm.last_stats["tokens"] == 0


def test_redirect_is_not_followed():
    import urllib.request
    req = urllib.request.Request("http://a/x", headers={"Authorization": "Bearer k"})
    assert llm._NoRedirect().redirect_request(req, None, 302, "Found", {}, "http://evil/") is None
