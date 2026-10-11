"""Флаг «всплеск★»: история звёзд (REST stargazers/history) и всплески по MAD.

Доля звёзд во всплесках — измерение, не обвинение: куплены или вирусный запуск, по истории не отличить.
Алгоритм всплесков портирован из real-stars `src/shared/mad.ts:72-179` и `src/shared/constants.ts:13-19`
(MIT; он сам порт StarGuard, Apache-2.0). Тексты лицензий: THIRD_PARTY_NOTICES.md.
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
PER_PAGE = 30  # максимум REST
MAX_PAGES = 20  # ponytail: 20 страниц ≈ 11 лет; у старше «ранние» не считаем (история обрезана)
MIN_STARS = 50  # StarScout MIN_STARS: меньше — не проверяем
MIN_TOTAL = 30  # real-stars MIN_STAR_COUNT: меньше — без вердикта
WINDOW = 28  # real-stars WINDOW_SIZE
MAD_THRESHOLD = 3.0 * 1.4826  # real-stars MAD_THRESHOLD
GROWTH_PERCENT = 300  # real-stars MIN_STARS_GROWTH_PERCENT: запасной путь при MAD == 0 или коротком окне
HIGH_DENSITY = 10  # звёзд/день; real-stars mad.ts:93: короткая вирусная история без базы — всплесков нет
EARLY_STARS = 1000  # «ранние»: до первых ~1000★ (там покупают)
FORK_DAYS = 3
SHARE_THRESHOLD = 0.7  # подбирается по eval/fake-stars (eval/BASELINE.md, Фаза 7)
MIN_BURST = 5


class History(NamedTuple):
    start: date
    counts: list[int]  # по дням, от старого к новому
    complete: bool  # дошли до недели создания репо


def _rest(path: str) -> list | None:
    """Страница истории; None — 404/422 (нет репо, слишком много звёзд). Ретраи как у GraphQL."""
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
            raise GitHubError(f"gh завершился с ошибкой: {err.strip()}")
        if attempt < github.MAX_RETRIES:
            wait = min(2**attempt * 5, 60)
            log.info("история звёзд: %s — повтор %d через %d с", err.strip()[:80], attempt + 1, wait)
            time.sleep(wait)
    raise GitHubError(f"история звёзд {path}: GitHub не ответил")


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
    keep = (now.date() - start).days + 1  # дни текущей недели после «сегодня» отбрасываем
    return History(start, counts[:max(keep, 0)], complete)


def history(name: str, now: datetime) -> History | None:
    """Ежедневные звёзды репо. Снапшот stars/<sha16(lower name)>.json.gz; None — GitHub историю не отдаёт."""
    path = github._dir / "stars" / f"{github._key(name.lower())}.json.gz" if github._mode else None
    if path and path.exists():
        snap = github._read(path)
    elif github._mode == "replay":
        raise GitHubError(f"нет снапшота истории звёзд {name} (--record)")
    else:
        log.info("история звёзд: %s", name)
        found = _weeks(name)
        snap = {"weeks": found[0], "complete": found[1]} if found else None
        if snap is None:
            log.warning("предупреждение: история звёзд %s недоступна (404/422)", name)
        if path and github._mode == "record":
            github._write(path, snap)
    return _daily(snap["weeks"], now, snap["complete"]) if snap and snap["weeks"] else None


def bursts(counts: list[int], min_count: int = MIN_BURST, complete: bool = True) -> list[bool]:
    """День-всплеск по real-stars `mad.ts:72-179`: окно 28 дней, count > median + 3·1.4826·MAD."""
    n = len(counts)
    if not complete and n < 2 * WINDOW and sum(counts) / max(n, 1) > HIGH_DENSITY:
        return [False] * n  # mad.ts:93-95: обрезанная история — один вирусный всплеск, базы нет (у полной истории не применяем)
    flags, before = [], 0
    for i, today in enumerate(counts):
        med = mad = 0.0
        if i >= WINDOW:
            win = counts[i - WINDOW:i]
            med = median(win)
            mad = median(abs(v - med) for v in win)
        if before >= MIN_TOTAL and mad > 0.001 and i >= WINDOW:
            hit = today > med + MAD_THRESHOLD * mad and today > med + 1
        else:  # mad.ts:139-146: запасной путь для малых репо и MAD == 0
            hit = today > 0 and ((today / max(1, before) * 100 > GROWTH_PERCENT and today > 5)
                                 or today > max(5, med * 2))
        flags.append(hit and today >= min_count)
        before += today
    return flags


def share(h: History, min_count: int = MIN_BURST) -> float | None:
    """Доля звёзд во всплесках среди первых min(1000, всего)★. None: <30★ или история обрезана.
    ponytail: окно «последние 90 дней» не считаем: на eval оно не проверено."""
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
    """«всплеск★ N% ранних»: доля первых ~1000★, пришедших в дни-всплески, если она ≥ порога."""
    value = share(h, min_count) if h else None
    return f"всплеск★ {value:.0%} ранних" if value is not None and value >= threshold else None


def fork_dates(name: str) -> list[datetime]:
    """Даты создания последних 100 форков (GraphQL, 1 вызов). ponytail: старше 100-го форка всплески не проверить."""
    owner, repo = name.split("/")
    q = ("query($o:String!,$n:String!){repository(owner:$o,name:$n){forks(first:100,orderBy:{field:CREATED_AT,direction:DESC})"
         "{nodes{createdAt}}}}")
    nodes = github.graphql(q, {"o": owner, "n": repo})["data"]["repository"]["forks"]["nodes"]
    return [datetime.fromisoformat(n["createdAt"]) for n in nodes]


def burst_forks(h: History, forks: list[datetime], min_count: int = MIN_BURST) -> tuple[int, int]:
    """(звёзд во всплесках, форков в ±3 дня от них) только для всплесков, лежащих в охвате 100 последних форков."""
    if not forks:
        return 0, 0
    oldest = min(forks).date() + timedelta(days=FORK_DAYS)
    days = [h.start + timedelta(days=i) for i, f in enumerate(bursts(h.counts, min_count, h.complete)) if f]
    covered = [d for d in days if d >= oldest]
    stars = sum(h.counts[(d - h.start).days] for d in covered)
    near = sum(any(abs((f.date() - d).days) <= FORK_DAYS for d in covered) for f in forks)
    return stars, near
