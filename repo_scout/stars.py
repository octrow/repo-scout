"""'burst★' flag: star history (REST stargazers/history) and bursts via MAD.

The share of stars in bursts is a measurement, not an accusation: bought stars and viral launches look the same in history.
The burst algorithm is ported from real-stars `src/shared/mad.ts:72-179` and `src/shared/constants.ts:13-19`
(MIT; itself a port of StarGuard, Apache-2.0). License texts: THIRD_PARTY_NOTICES.md.
"""
import json
import subprocess
import time
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import NamedTuple

from repo_scout import github
from repo_scout.github import GitHubError
from repo_scout.log import log

API_VERSION = "2026-03-10"
PER_PAGE = 30  # REST maximum
MAX_PAGES = 20  # 20 pages ≈ 11 years; older repos have truncated history
MIN_STARS = 50  # StarScout MIN_STARS: skip checking if below
MIN_TOTAL = 30  # real-stars MIN_STAR_COUNT: no verdict below this
WINDOW = 28  # real-stars WINDOW_SIZE
MAD_THRESHOLD = 3.0 * 1.4826  # real-stars MAD_THRESHOLD
GROWTH_PERCENT = 300  # real-stars MIN_STARS_GROWTH_PERCENT: fallback for MAD == 0 or short window
HIGH_DENSITY = 10  # stars/day; short viral history without baseline has no bursts
EARLY_STARS = 1000  # "early": first ~1000★ where buying typically occurs
FORK_DAYS = 3
SHARE_THRESHOLD = 0.7  # tuned against eval/fake-stars (eval/BASELINE.md, Phase 7)
MIN_BURST = 5


class History(NamedTuple):
    start: date
    counts: list[int]  # by day, from oldest to newest
    complete: bool  # reached creation week of repository


def _rest(path: str) -> list | None:
    """History page; None on 404/422 (repo missing, too many stars). Retries like GraphQL."""
    cmd = ["gh", "api", path, "-H", f"X-GitHub-Api-Version: {API_VERSION}"]
    for attempt in range(github.MAX_RETRIES + 1):
        github.calls["stars"] += 1
        out = subprocess.run(cmd, check=False, capture_output=True, text=True)
        err = out.stderr
        if not out.returncode:
            return json.loads(out.stdout)
        if "HTTP 404" in err or "HTTP 422" in err:
            return None
        limited = "HTTP 429" in err or ("HTTP 403" in err and "rate limit" in err.lower())
        if not (limited or any(f"HTTP {c}" in err for c in github.TRANSIENT)):
            raise GitHubError(f"gh failed: {err.strip()}")
        if attempt < github.MAX_RETRIES:
            wait = min(2**attempt * 5, 60)
            log.info("star history: %s — retry %d in %d s", err.strip()[:80], attempt + 1, wait)
            time.sleep(wait)
    raise GitHubError(f"star history {path}: GitHub did not respond")


def _weeks(name: str) -> tuple[list[dict], bool] | None:
    weeks: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        got = _rest(f"repos/{name}/stargazers/history?per_page={PER_PAGE}&page={page}")
        if got is None:
            if page == 1:
                return None
            return weeks, False
        weeks += got
        if len(got) < PER_PAGE:
            return weeks, True
    return weeks, False


def _daily(weeks: list[dict], now: datetime, complete: bool) -> History:
    first = min(w["week"] for w in weeks)
    counts = [0] * ((max(w["week"] for w in weeks) - first) // 86400 + 7)
    for w in weeks:
        base = (w["week"] - first) // 86400
        counts[base:base + 7] = w["days"]
    start = datetime.fromtimestamp(first, UTC).date()
    keep = (now.date() - start).days + 1  # drop days of current week after 'now'
    return History(start, counts[:max(keep, 0)], complete)


def history(name: str, now: datetime) -> History | None:
    """Daily stars for repo. Snapshot at stars/<sha16(lower name)>.json.gz; None if GitHub cannot provide history."""
    path = github._dir / "stars" / f"{github._key(name.lower())}.json.gz" if github._mode else None
    if path and path.exists():
        snap = github._read(path)
    elif github._mode == "replay":
        raise GitHubError(f"missing star history snapshot for {name} (--record)")
    else:
        log.info("star history: %s", name)
        found = _weeks(name)
        snap = {"weeks": found[0], "complete": found[1]} if found else None
        if snap is None:
            log.warning("warning: star history for %s unavailable (404/422)", name)
        if path and github._mode == "record":
            github._write(path, snap)
    return _daily(snap["weeks"], now, snap["complete"]) if snap and snap["weeks"] else None


def bursts(counts: list[int], min_count: int = MIN_BURST, complete: bool = True) -> list[bool]:
    """Burst day per real-stars `mad.ts:72-179`: 28-day window, count > median + 3·1.4826·MAD."""
    n = len(counts)
    if not complete and n < 2 * WINDOW and sum(counts) / max(n, 1) > HIGH_DENSITY:
        return [False] * n  # truncated history: single viral spike without baseline
    flags, before = [], 0
    for i, today in enumerate(counts):
        med = mad = 0.0
        if i >= WINDOW:
            win = counts[i - WINDOW:i]
            med = median(win)
            mad = median(abs(v - med) for v in win)
        if before >= MIN_TOTAL and mad > 0.001 and i >= WINDOW:
            hit = today > med + MAD_THRESHOLD * mad and today > med + 1
        else:  # fallback for small repos and MAD == 0
            hit = today > 0 and ((today / max(1, before) * 100 > GROWTH_PERCENT and today > 5)
                                 or today > max(5, med * 2))
        flags.append(hit and today >= min_count)
        before += today
    return flags


def share(h: History, min_count: int = MIN_BURST) -> float | None:
    """Share of stars in bursts among first min(1000, total)★. None: <30★ or incomplete history."""
    total = sum(h.counts)
    if total < MIN_TOTAL or not h.complete:
        return None
    target, run, end = min(EARLY_STARS, total), 0, len(h.counts)
    for i, c in enumerate(h.counts):
        run += c
        if run >= target:
            end = i + 1
            break
    flags = bursts(h.counts, min_count, h.complete)[:end]
    stars_in = sum(h.counts[:end])
    return sum(c for c, f in zip(h.counts, flags) if f) / stars_in if stars_in else None


def flag(h: History | None, threshold: float = SHARE_THRESHOLD, min_count: int = MIN_BURST) -> str | None:
    """'burst★ N% early': share of first ~1000★ occurring on burst days, if >= threshold."""
    value = share(h, min_count) if h else None
    return f"burst★ {value:.0%} early" if value is not None and value >= threshold else None


def fork_dates(name: str) -> list[datetime]:
    """Creation dates of last 100 forks (GraphQL, 1 call)."""
    owner, repo = name.split("/")
    q = ("query($o:String!,$n:String!){repository(owner:$o,name:$n){forks(first:100,orderBy:{field:CREATED_AT,direction:DESC})"
         "{nodes{createdAt}}}}")
    found = github.graphql(q, {"o": owner, "n": repo})["data"]["repository"]  # null: renamed, deleted, DMCA
    return [datetime.fromisoformat(n["createdAt"]) for n in (found or {}).get("forks", {}).get("nodes") or [] if n]


def burst_forks(h: History, forks: list[datetime], min_count: int = MIN_BURST) -> tuple[int, int]:
    """(stars in bursts, forks in ±3 days) only for bursts within the span of the last 100 forks."""
    if not forks:
        return 0, 0
    oldest = min(forks).date() + timedelta(days=FORK_DAYS)
    days = [h.start + timedelta(days=i) for i, f in enumerate(bursts(h.counts, min_count, h.complete)) if f]
    covered = [d for d in days if d >= oldest]
    stars = sum(h.counts[(d - h.start).days] for d in covered)
    near = sum(any(abs((f.date() - d).days) <= FORK_DAYS for d in covered) for f in forks)
    return stars, near
