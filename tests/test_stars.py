import json
import random
import re
import subprocess
from datetime import UTC, datetime
from typing import Any

import pytest

from repo_scout import github, stars
from repo_scout.github import GitHubError
from repo_scout.stars import MIN_BURST, History, burst_forks, bursts, flag, share

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
    text = flag(h, 0.5)
    assert text is not None and re.fullmatch(r"burst★ \d+% early", text)
    assert flag(h, 0.99) is None and flag(None) is None


def test_history_daily_counts_and_snapshot_roundtrip(monkeypatch, tmp_path):
    end = WEEK0 + 604800 * 3
    data = weeks_json([[1] * 7, [2] * 7, [3, 3, 3, 3, 3, 3, 3]], end)
    calls = fake_gh(monkeypatch, {1: json.dumps(data)})
    github.configure("record", tmp_path)
    now = datetime.fromtimestamp(end + 86400 * 2, UTC)
    h = stars.history("A/b", now)
    assert h is not None
    assert h.complete and h.counts == [1] * 7 + [2] * 7 + [3] * 3  # days after today dropped
    assert len(calls) == 1 and "X-GitHub-Api-Version: 2026-03-10" in calls[0]
    assert (tmp_path / "stars").is_dir()
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("network in replay"))
    github.configure("replay", tmp_path)
    assert stars.history("a/B", now) == h  # case-insensitive key


def test_history_pages_until_short_page_and_max_pages(monkeypatch):
    full = json.dumps(weeks_json([[1] * 7] * 30, WEEK0 + 604800 * 100))
    calls = fake_gh(monkeypatch, {1: full, 2: full, 3: "[]"})
    found = stars._weeks("a/b")
    assert found is not None and found[1] is True and len(calls) == 3
    monkeypatch.setattr(stars, "MAX_PAGES", 2)
    calls.clear()
    found = stars._weeks("a/b")
    assert found is not None and found[1] is False and len(calls) == 2


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
    rows: list[dict[str, Any]] = [
        {"repo": n, "stars": s, "stop": st, "flags": []}
        for n, s, st in [("a/a", 10, None), ("b/b", 500, "x"), ("c/c", 500, None), ("d/d", 500, None)]
    ]
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


def _burst_days(counts, min_count=MIN_BURST, complete=True):
    return [i for i, f in enumerate(bursts(counts, min_count, complete)) if f]


def test_bursts_pinned_on_mixed_series():
    rng = random.Random(7)
    noisy = [rng.choice([0, 0, 1, 2, 3, 5, 8, 40]) for _ in range(120)]
    tail = [42, 43, 51, 53, 61, 68, 69, 73, 77, 82, 86, 94, 97, 114]
    assert _burst_days(noisy, 1) == [2, 11, 12, 16, 21, 27, 30, 39, 40, *tail]
    assert _burst_days(noisy, 5, False) == [2, 11, 12, 16, 21, 27, 39, 40, *tail]
    assert _burst_days(noisy, 10) == [39, *tail]
    assert _burst_days([0, 0, 6, 0, 1, 7, 0, 0, 12, 1] * 4, 5) == [2, 5, 8, 12, 15, 18, 22, 25, 28, 32, 35, 38]
    assert _burst_days([2] * 40 + [9, 2, 2, 30] + [2] * 10) == [40, 43]
    assert _burst_days([0, 1, 0, 0, 4, 0, 1, 6, 0, 0, 2, 9, 0, 3], 1) == [7, 11]
    assert bursts([]) == []


def fake_gh_seq(monkeypatch, replies: list[tuple[int, str]]):
    """Each call pops the next (returncode, stdout-or-stderr); sleeps are recorded, not slept."""
    calls, sleeps = [], []

    def run(cmd, **kw):
        calls.append(cmd)
        code, text = replies.pop(0)
        return subprocess.CompletedProcess(cmd, code, "" if code else text, text if code else "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(stars.time, "sleep", sleeps.append)
    return calls, sleeps


@pytest.mark.parametrize(
    "err", ["gh: Bad Gateway (HTTP 502)", "gh: (HTTP 429)", "gh: API Rate Limit exceeded (HTTP 403)"]
)
def test_rest_retries_transient_and_rate_limit(monkeypatch, err):
    before = github.calls["stars"]
    calls, sleeps = fake_gh_seq(monkeypatch, [(1, err), (1, err), (0, "[1]")])
    assert stars._rest("p") == [1]
    assert len(calls) == 3 and sleeps == [5, 10] and github.calls["stars"] - before == 3


def test_rest_gives_up_after_max_retries(monkeypatch):
    calls, sleeps = fake_gh_seq(monkeypatch, [(1, "gh: (HTTP 503)")] * (github.MAX_RETRIES + 1))
    with pytest.raises(GitHubError, match="star history p: GitHub did not respond"):
        stars._rest("p")
    assert len(calls) == github.MAX_RETRIES + 1 and sleeps == [5, 10, 20]


def test_rest_404_and_hard_error_do_not_retry(monkeypatch):
    calls, sleeps = fake_gh_seq(monkeypatch, [(1, "gh: Not Found (HTTP 404)")])
    assert stars._rest("p") is None and len(calls) == 1 and sleeps == []
    fake_gh_seq(monkeypatch, [(1, "  gh: Forbidden (HTTP 403)\n")])
    with pytest.raises(GitHubError, match=r"^gh failed: gh: Forbidden \(HTTP 403\)$"):
        stars._rest("p")


def test_weeks_404_on_later_page_keeps_earlier_pages(monkeypatch):
    full = json.dumps(weeks_json([[1] * 7] * 30, WEEK0 + 604800 * 100))
    fake_gh(monkeypatch, {1: full, 2: (1, "gh: (HTTP 422)")})
    found = stars._weeks("a/b")
    assert found is not None
    got, complete = found
    assert len(got) == 30 and complete is False
    fake_gh(monkeypatch, {1: (1, "gh: (HTTP 404)")})
    assert stars._weeks("a/b") is None


def test_history_records_unavailable_and_replays_none(monkeypatch, tmp_path):
    fake_gh(monkeypatch, {1: (1, "gh: (HTTP 404)")})
    github.configure("record", tmp_path)
    assert stars.history("a/b", NOW) is None
    snap = tmp_path / "stars" / f"{github._key('a/b')}.json.gz"
    assert github._read(snap) is None
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("network in replay"))
    github.configure("replay", tmp_path)
    assert stars.history("a/b", NOW) is None


def test_history_empty_weeks_is_none_and_live_mode_writes_nothing(monkeypatch, tmp_path):
    fake_gh(monkeypatch, {1: "[]"})
    assert stars.history("a/b", NOW) is None
    github.configure("record", tmp_path)
    assert stars.history("a/b", NOW) is None
    assert github._read(tmp_path / "stars" / f"{github._key('a/b')}.json.gz") == {"weeks": [], "complete": True}


def test_fork_dates_of_missing_repo_or_null_fork_is_empty(monkeypatch):
    monkeypatch.setattr(github, "graphql", lambda q, v: {"data": {"repository": None}})
    assert stars.fork_dates("a/b") == []
    monkeypatch.setattr(
        github,
        "graphql",
        lambda q, v: {"data": {"repository": {"forks": {"nodes": [None, {"createdAt": "2026-01-01T00:00:00Z"}]}}}},
    )
    assert stars.fork_dates("a/b") == [datetime(2026, 1, 1, tzinfo=UTC)]
