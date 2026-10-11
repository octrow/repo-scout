import pytest


@pytest.fixture(autouse=True)
def isolated_index(tmp_path, monkeypatch):
    """Тесты никогда не трогают пользовательский Индекс."""
    monkeypatch.setenv("REPO_SCOUT_INDEX", str(tmp_path / "user-index.db"))
