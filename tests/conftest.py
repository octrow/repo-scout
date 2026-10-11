import pytest


@pytest.fixture(autouse=True)
def isolated_index(tmp_path, monkeypatch):
    """Тесты никогда не трогают пользовательский Индекс."""
    monkeypatch.setenv("REPO_SCOUT_INDEX", str(tmp_path / "user-index.db"))


@pytest.fixture(autouse=True)
def isolated_log(tmp_path, monkeypatch):
    monkeypatch.setenv("REPO_SCOUT_LOG", str(tmp_path / "run.log"))
