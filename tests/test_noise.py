from repo_scout.noise import is_template, noise_stop


def node(name="o/proj", desc="", topics=(), template=False):
    return {"nameWithOwner": name, "description": desc, "isTemplate": template,
            "repositoryTopics": {"nodes": [{"topic": {"name": t}} for t in topics]}}


def test_one_signal_passes():
    assert noise_stop(node("o/awesome-thing", "a real tool")) is None


def test_two_signals_stop_with_sources():
    stop = noise_stop(node("o/awesome-llm", "A curated list of tools", ["tools"]))
    assert stop == "noise (awesome: name, description)"


def test_topics_count_as_signal():
    assert noise_stop(node("o/my-demo", "x", ["demo"])) == "noise (demo: name, topics)"


def test_homework_and_spam():
    assert noise_stop(node("o/os-homework", "university assignment")).startswith("noise (homework")
    assert noise_stop(node("o/keygen-pro", "guaranteed passive income")).startswith("noise (spam")


def test_poc_is_a_word_not_substring():
    assert noise_stop(node("o/pocketbase-demo", "pocket database")) is None


def test_template_is_flag_and_still_noise_if_noisy():
    n = node("o/awesome-boilerplates", "A curated list of boilerplates", ["awesome-list"])
    assert is_template(n) and noise_stop(n).startswith("noise (awesome")
    assert is_template(node(template=True))
    assert not is_template(node("o/tool", "does things"))
    assert noise_stop(node("o/starter-app", "a starter kit")) is None


def test_real_projects_are_not_noise():
    assert noise_stop(node("OpenAPITools/openapi-generator", "Generate API clients from OpenAPI",
                           ["generator", "openapi"])) is None
    assert noise_stop(node("o/deep-learning-kit", "Of course, a fast toolkit", ["learning", "list"])) is None
    assert noise_stop(node("o/free-tool", "free to use", ["free-money-no"])) is None
