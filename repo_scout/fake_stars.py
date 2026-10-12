"""`repo-scout eval --fake-stars`: precision/recall/FPR of the 'burst★' flag on eval/fake-stars/labels.csv."""
import csv
import random
from pathlib import Path

from repo_scout import github, stars
from repo_scout.log import log

DIR = Path(__file__).resolve().parents[1] / "eval" / "fake-stars"
THRESHOLDS = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
MIN_BURSTS = [5, 10, 20]
MIN_RECALL = 0.5
SEED = 0
TOP_K = 10
MAX_FPR = 0.15  # gate: higher on test means flag only via --stars-check


def load(path: Path = DIR / "labels.csv") -> list[tuple[str, int]]:
    return [(r["repo"], int(r["label"])) for r in csv.DictReader(open(path))]


def collect(labels: list[tuple[str, int]], now, forks: bool) -> dict[str, stars.History]:
    """History (and forks) of each repo; snapshots written under --record. Skip repos without history."""
    out = {}
    for i, (name, _) in enumerate(labels, 1):
        log.info("fake-stars %d/%d: %s", i, len(labels), name)
        if h := stars.history(name, now):
            out[name] = h
            if forks:
                stars.fork_dates(name)
    return out


def split(labels: list[tuple[str, int]]) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """Stratified 50/50 split (seed 0): (tune, test)."""
    tune, test = [], []
    for y in (0, 1):
        part = sorted(x for x in labels if x[1] == y)
        random.Random(SEED).shuffle(part)
        tune += part[:len(part) // 2]
        test += part[len(part) // 2:]
    return tune, test


def score(labels: list[tuple[str, int]], hist: dict[str, stars.History], thr: float, mb: int) -> dict:
    """Confusion matrix of flag; repos without history count as unflagged."""
    def hit(n):
        return n in hist and (v := stars.share(hist[n], mb)) is not None and v >= thr
    tp = sum(y and hit(n) for n, y in labels)
    fp = sum((not y) and hit(n) for n, y in labels)
    pos = sum(y for _, y in labels)
    neg = len(labels) - pos
    return {"thr": thr, "min_burst": mb, "tp": tp, "fp": fp, "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / pos, "fpr": fp / neg}


def grid(labels: list[tuple[str, int]], hist: dict[str, stars.History]) -> list[dict]:
    return [score(labels, hist, t, mb) for mb in MIN_BURSTS for t in THRESHOLDS]


def best(rows: list[dict]) -> dict:
    """Minimum FPR with recall >= MIN_RECALL (then higher recall); else maximum recall."""
    ok = [r for r in rows if r["recall"] >= MIN_RECALL]
    return min(ok, key=lambda r: (r["fpr"], -r["recall"])) if ok else max(rows, key=lambda r: r["recall"])


def fork_report(labels, hist, mb: int) -> str:
    """Forks in ±3 days of bursts per 100 burst stars (within span of last 100 forks), mean per class."""
    acc: dict[int, list[float]] = {0: [], 1: []}
    for n, y in labels:
        if n in hist and (res := stars.burst_forks(hist[n], stars.fork_dates(n), mb)) and res[0]:
            acc[y].append(100 * res[1] / res[0])
    def mean(v):
        return f"{sum(v) / len(v):.1f}" if v else "—"
    return (f"forks per 100 burst stars (bursts within span of last 100 forks only): "
            f"positives {mean(acc[1])} (n={len(acc[1])}), negatives {mean(acc[0])} (n={len(acc[0])})")


def table(rows: list[dict]) -> str:
    lines = ["| threshold | min stars/day | TP | FP | precision | recall | FPR |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {r['thr']} | {r['min_burst']} | {r['tp']} | {r['fp']} | {r['precision']:.2f} "
              f"| {r['recall']:.2f} | {r['fpr']:.2f} |" for r in rows]
    return "\n".join(lines)


def run(mode: str, show_all: bool = False) -> str:
    github.configure(mode, DIR / "snapshots")
    github.calls.clear()
    now, labels = github.recorded_at(), load()
    hist = collect(labels, now, forks=True)
    tune, test = split(labels)
    rows = grid(tune, hist)
    top = best(rows)
    res = score(test, hist, top["thr"], top["min_burst"])
    out = [f"repos with history: {len(hist)} of {len(labels)}; tune {len(tune)}, test {len(test)}; REST calls: {github.calls['stars']}",
           "", "tune (grid):", table(rows if show_all else [r for r in rows if r["thr"] in (0.4, 0.6, 0.8)]), "",
           f"chosen on tune (min FPR at recall >= {MIN_RECALL}): threshold {top['thr']}, min {top['min_burst']}", "",
           "test: " + table([res]).split("\n", 2)[2],
           f"false flags in top-{TOP_K}: ≈{TOP_K * res['fpr']:.1f}; at least one in run: {1 - (1 - res['fpr']) ** TOP_K:.0%}",
           f"gate (FPR on test <= {MAX_FPR}): {'PASSED' if res['fpr'] <= MAX_FPR else 'FAILED, flag only via --stars-check'}",
           "", fork_report(labels, hist, top["min_burst"]), "", "false positives on test: repo, share"]
    out += [f"- {n}: {stars.share(hist[n], top['min_burst']):.0%}" for n, y in test
            if not y and n in hist and (stars.share(hist[n], top["min_burst"]) or 0) >= top["thr"]]
    return "\n".join(out)
