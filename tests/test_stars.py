import json
import re
import subprocess
from datetime import UTC, datetime

import pytest

from repo_scout import github, stars
from repo_scout.github import GitHubError
from repo_scout.stars import History, burst_forks, bursts, flag, share

NOW = datetime(2026, 10, 11, tzinfo=UTC)  # Sunday
WEEK0 = 1_790_000_000 - 1_790_000_000 % 604800  # week start


@pytest.fixture(autouse=True)
def reset():
    yield
    github.configure(None, None)


def weeks_json(days_by_week: list[list[int]], end: int) -> list[dict]:
    """Weeks from newest to oldest; last week starts at `end`."""
    return [{"week": end - 604800 * i, "total": sum(d), "days": d} for i, d in enumerate(reversed(days_by_week))]


def fake_gh(monkeypatch, pages: dict[int, str | tuple[int, str]]):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        page = int(cmd[2].rsplit("page=", 1)[1])
        r = pages.get(page, "[]")
        if isinstance(r, tuple):
            return subprocess.CompletedProcess(cmd, 1, "", r[1])
        return subprocess.CompletedProcess(cmd, 0, r, "")
    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_bursts_flat_has_none():
    assert not any(bursts([3] * 100))


def test_bursts_spike_after_baseline():
    counts = [2, 3] * 30 + [60] + [2, 3] * 5
    flags = bursts(counts)
    assert flags[60] and sum(flags) == 1


def test_bursts_zero_mad_fallback_and_min_count():
    counts = [1] * 60 + [8] + [1] * 3  # MAD == 0 fallback path
    assert bursts(counts)[60]
    assert not bursts(counts, min_count=9)[60]


def test_bursts_high_density_guard_only_for_truncated_history():
    assert not any(bursts([100] * 10, complete=False))
    assert bursts([1] * 10 + [500] + [2] * 33)[10]  # complete history: guard does not apply


def test_share_no_verdict_below_30_stars_or_truncated():
    assert share(History(NOW.date(), [1] * 20, True)) is None
    assert share(History(NOW.date(), [2, 3] * 30 + [60], False)) is None


def test_share_early_window_is_first_1000_stars():
    counts = [2, 3] * 30 + [60] + [2, 3] * 5
    assert share(History(NOW.date(), counts, True)) == pytest.approx(60 / sum(counts))
    long = [2, 3] * 30 + [900] + [2, 3] * 5 + [5000]
    assert share(History(NOW.date(), long, True)) == pytest.approx(900 / 1050)


def test_flag_text_and_threshold():
    h = History(NOW.date(), [2, 3] * 30 + [200] + [2, 3] * 5, True)
    assert re.fullmatch(r"burst★ \d+% early", flag(h, 0.5))
    assert flag(h, 0.99) is None and flag(None) is None


def test_history_daily_counts_and_snapshot_roundtrip(monkeypatch, tmp_path):
    end = WEEK0 + 604800 * 3
    data = weeks_json([[1] * 7, [2] * 7, [3, 3, 3, 3, 3, 3, 3]], end)
    calls = fake_gh(monkeypatch, {1: json.dumps(data)})
    github.configure("record", tmp_path)
    now = datetime.fromtimestamp(end + 86400 * 2, UTC)
    h = stars.history("A/b", now)
    assert h.complete and h.counts == [1] * 7 + [2] * 7 + [3] * 3  # days after today dropped
    assert len(calls) == 1 and "X-GitHub-Api-Version: 2026-03-10" in calls[0]
    assert (tmp_path / "stars").is_dir()
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("network in replay"))
    github.configure("replay", tmp_path)
    assert stars.history("a/B", now) == h  # case-insensitive key


def test_history_pages_until_short_page_and_max_pages(monkeypatch):
    full = json.dumps(weeks_json([[1] * 7] * 30, WEEK0 + 604800 * 100))
    calls = fake_gh(monkeypatch, {1: full, 2: full, 3: "[]"})
    assert stars._weeks("a/b")[1] is True and len(calls) == 3
    monkeypatch.setattr(stars, "MAX_PAGES", 2)
    calls.clear()
    assert stars._weeks("a/b")[1] is False and len(calls) == 2


def test_history_404_and_error(monkeypatch):
    fake_gh(monkeypatch, {1: (1, "gh: Validation Failed (HTTP 422)")})
    assert stars.history("a/b", NOW) is None
    fake_gh(monkeypatch, {1: (1, "gh: Forbidden (HTTP 403)")})
    with pytest.raises(GitHubError):
        stars.history("a/b", NOW)
    fake_gh(monkeypatch, {1: (1, "gh: boom (HTTP 400)")})
    with pytest.raises(GitHubError):
        stars.history("a/b", NOW)


def test_history_replay_missing(tmp_path):
    (tmp_path / "meta.json").write_text('{"recorded_at": "2026-10-11T00:00:00+00:00"}')
    github.configure("replay", tmp_path)
    with pytest.raises(GitHubError, match="snapshot"):
        stars.history("a/b", NOW)


def test_burst_forks_counts_forks_near_covered_bursts():
    h = History(datetime(2026, 1, 1, tzinfo=UTC).date(), [2, 3] * 30 + [60] + [2, 3] * 5, True)
    day = datetime(2026, 3, 3, 12, tzinfo=UTC)
    forks = [day, datetime(2026, 3, 6, 12, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)]
    assert burst_forks(h, [], 5) == (0, 0)
    stars_in, near = burst_forks(h, forks, 5)
    assert stars_in == 60 and near == 1


def test_add_stars_flag_top_k_only_with_min_stars(monkeypatch):
    from repo_scout.cli import add_stars_flag
    h = History(NOW.date(), [2, 3] * 30 + [900] + [2, 3] * 5, True)
    asked = []
    monkeypatch.setattr(stars, "history", lambda name, now: asked.append(name) or h)
    rows = [{"repo": n, "stars": s, "stop": st, "flags": []}
            for n, s, st in [("a/a", 10, None), ("b/b", 500, "x"), ("c/c", 500, None), ("d/d", 500, None)]]
    add_stars_flag(rows, 1, NOW)
    assert asked == ["c/c"] and rows[2]["flags"][0].startswith("burst★") and not rows[3]["flags"]


def test_add_stars_flag_survives_github_error(monkeypatch):
    from repo_scout.cli import add_stars_flag

    def boom(name, now):
        raise GitHubError("x")
    monkeypatch.setattr(stars, "history", boom)
    rows = [{"repo": "a/a", "stars": 500, "stop": None, "flags": []}]
    add_stars_flag(rows, 5, NOW)
    assert rows[0]["flags"] == []
