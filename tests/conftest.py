import pytest

from repo_scout import llm

pytest_plugins = ["nicegui.testing.user_plugin"]


@pytest.fixture(autouse=True)
def isolated_index(tmp_path, monkeypatch):
    """Тесты никогда не трогают пользовательский Индекс."""
    monkeypatch.setenv("REPO_SCOUT_INDEX", str(tmp_path / "user-index.db"))


@pytest.fixture(autouse=True)
def isolated_log(tmp_path, monkeypatch):
    monkeypatch.setenv("REPO_SCOUT_LOG", str(tmp_path / "run.log"))


@pytest.fixture(autouse=True)
def isolated_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("REPO_SCOUT_RUNS", str(tmp_path / "runs"))


@pytest.fixture(autouse=True)
def isolated_llm(tmp_path, monkeypatch):
    """Тесты не читают настоящий .env и переменные OMNIROUTE_*."""
    for var in ("OMNIROUTE_API_KEY", "OMNIROUTE_MODEL", "OMNIROUTE_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(llm, "ENV_FILE", tmp_path / "no-such.env")
