"""Builds labels.csv from StarScout (Apache-2.0) data and '→ Study' from eval/*.toml. Run: python3 build_labels.py
Requires authenticated gh. Liveness and star counts in GraphQL batches; fixed random seed."""

import csv
import json
import random
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "external_examples/StarScout/data/250101"
WANT, CHUNK, MIN_STARS, MIN_P, SEED = 100, 30, 50, 0.5, 0
NAME = re.compile(r"[\w.-]+/[\w.-]+")


def positives() -> list[str]:
    out = set()
    for f, col in (
        ("fake_stars_low_activity_repos", "p_stars_low_activity"),
        ("fake_stars_clustered_repos", "p_stars_clustered"),
    ):
        for r in csv.DictReader(open(DATA / f"{f}.csv")):
            if float(r[col]) >= MIN_P and int(r["n_stars"]) >= MIN_STARS and NAME.fullmatch(r["repo_name"]):
                out.add(r["repo_name"])
    return sorted(out)


def stars_of(names: list[str]) -> dict[str, int]:
    """{name: stargazerCount} for live repos."""
    q = (
        "query{"
        + " ".join(
            f"r{i}:repository(owner:{json.dumps(n.split('/')[0])},name:{json.dumps(n.split('/')[1])}){{nameWithOwner stargazerCount}}"
            for i, n in enumerate(names)
        )
        + "}"
    )
    out = subprocess.run(["gh", "api", "graphql", "-f", f"query={q}"], capture_output=True, text=True)
    data = (json.loads(out.stdout).get("data") or {}) if out.stdout else {}
    return {r["nameWithOwner"]: r["stargazerCount"] for r in data.values() if r}


def pick(pool: list[str], want: int, taken: set[str]) -> list[str]:
    random.Random(SEED).shuffle(pool)
    got: list[str] = []
    for i in range(0, len(pool), CHUNK):
        if len(got) >= want:
            break
        got += [n for n, s in stars_of(pool[i : i + CHUNK]).items() if s >= MIN_STARS and n.lower() not in taken][
            : want - len(got)
        ]
    return got


def study_repos() -> list[tuple[str, str]]:
    """(repo, eval file name) for every '→ Study' entry in eval/*.toml (legacy Russian wording too)."""
    return [
        (e["repo"], t.name)
        for t in sorted((ROOT / "eval").glob("*.toml"))
        for e in tomllib.loads(t.read_text())["expected"]
        if (e["verdict"].startswith("→ Study") or e["verdict"].startswith("→ \u0420\u0430\u0437\u0431\u043e\u0440"))
        and NAME.fullmatch(e["repo"])
    ]


def eval_negatives(toml: list[tuple[str, str]]) -> tuple[list[tuple[str, int, str]], set[str]]:
    """Label-0 rows for live eval repos with enough stars, first occurrence only; and their lower-case names."""
    alive = {}
    for i in range(0, len(toml), CHUNK):
        alive |= stars_of([n for n, _ in toml[i : i + CHUNK]])
    rows, seen = [], set()
    for n, t in toml:
        if alive.get(n, 0) >= MIN_STARS and n.lower() not in seen:
            seen.add(n.lower())
            rows.append((n, 0, f"eval/{t}"))
    return rows, seen


def write_labels(rows: list[tuple[str, int, str]]) -> None:
    with open(Path(__file__).parent / "labels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["repo", "label", "source"])
        w.writerows(rows)


def main() -> None:
    pos = pick(positives(), WANT, set())
    rows = [(n, 1, "starscout") for n in pos]
    negatives, seen = eval_negatives(study_repos())
    rows += negatives
    sample = [r["repo"] for r in csv.DictReader(open(DATA / "sample_repo_ids.csv")) if NAME.fullmatch(r["repo"])]
    rows += [(n, 0, "starscout-sample") for n in pick(sample, WANT - len(seen), seen | {p.lower() for p in pos})]
    write_labels(rows)
    print(len(pos), "positives;", len(rows) - len(pos), "negatives")


main()
