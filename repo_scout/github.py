"""GitHub GraphQL via `gh api graphql` with rate limit retries."""
import gzip
import hashlib
import json
import re
import subprocess
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from repo_scout.log import log

MAX_RETRIES = 3
EVAL_SINGLE_RETRIES = 1  # when recording eval, don't wait 35s for single failing repo: skip is recorded in snapshot
TRANSIENT = (502, 503, 504)
README_MAX_CHARS = 6_000  # sufficient for regexes and embeddings; keeps snapshot sizes bounded

NODE_FIELDS = """nameWithOwner url description stargazerCount forkCount pushedAt createdAt isArchived isFork isTemplate
repositoryTopics(first:20){nodes{topic{name}}}
parent{nameWithOwner} primaryLanguage{name}
defaultBranchRef{target{... on Commit{history{totalCount}}}}"""
SEARCH_GQL = ("query($q:String!,$n:Int!){rateLimit{cost remaining resetAt}\n"
              "search(query:$q,type:REPOSITORY,first:$n){nodes{... on Repository{\n" + NODE_FIELDS + "}}}}")

last_rate_limit: dict | None = None
spent = 0  # GraphQL cost points consumed by live requests in this process
_spent_lock = threading.Lock()
_rechecked: set[str] = set()
last_failed: set[str] = set()  # repos GitHub failed to return in details/refresh (distinct from deleted repos)
calls: Counter = Counter()  # logical calls: search, details (batches of DETAILS_CHUNK, also counted in replay)
_mode: str | None = None  # "record" | "replay" | None
_dir: Path | None = None
_details_dir: Path | None = None  # shared details directory (llm-eval); None = _dir/"details"


class GitHubError(Exception):
    pass


def _parse(stdout: str) -> dict | None:
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _attempt(query: str, variables: dict) -> tuple[dict | None, str | None]:
    """Single gh invocation: (data, None) on success, (None, reason) on retryable error, else raises GitHubError."""
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        cmd += ["-F" if isinstance(v, int) else "-f", f"{k}={v}"]
    out = subprocess.run(cmd, check=False, capture_output=True, text=True)
    err = out.stderr.strip()
    data = _parse(out.stdout)
    errors = (data or {}).get("errors") or []
    if any(e.get("type") == "RATE_LIMITED" for e in errors):
        return None, "RATE_LIMITED"
    if data and data.get("data") is not None and errors:
        msgs = "; ".join(str(e.get("message", e)) for e in errors)
        log.warning("GraphQL warning: %s", msgs)
        return data, None
    if out.returncode:
        if "429" in err or "rate limit" in err.lower() or any(f"HTTP {c}" in err for c in TRANSIENT):
            return None, err
        raise GitHubError(f"gh failed: {err or out.stdout.strip()}")
    if data is None:
        return None, "response without JSON"
    if data.get("data") is None and not errors:
        return None, "response without data"
    if errors:
        raise GitHubError(f"GraphQL: {errors[0].get('message', errors)}")
    return data, None


def configure(mode: str | None, directory: Path | str | None, details_dir: Path | str | None = None) -> None:
    """Configure recording or replaying GitHub response snapshots (None = standard live network).
    details_dir: repository details depend on repo, not query, so llm-eval shares them across sets."""
    global _mode, _dir, _details_dir
    _mode, _dir = mode, Path(directory) if directory else None
    _details_dir = Path(details_dir) if details_dir else None
    if mode == "record":
        _dir.mkdir(parents=True, exist_ok=True)
        meta = _dir / "meta.json"
        if not meta.exists():  # append recording preserves original snapshot timestamp
            meta.write_text(json.dumps({"recorded_at": datetime.now(UTC).isoformat()}))


def snapshot() -> tuple[str | None, Path | None]:
    """Current snapshot mode and directory (for llm: model responses are stored in llm/ sibling dir)."""
    return _mode, _dir


def recorded_at() -> datetime:
    path = _dir / "meta.json"
    if not path.exists():
        raise GitHubError(f"missing snapshot {path}: run --record first")
    return datetime.fromisoformat(json.loads(path.read_text())["recorded_at"])


def _key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _snapshot_path(query: str, variables: dict) -> Path:
    return _dir / f"{_key(json.dumps({'query': query, 'variables': variables}, sort_keys=True))}.json.gz"


def _cache_dir(kind: str) -> Path:
    return _details_dir if kind == "details" and _details_dir else _dir / kind


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as g:
        g.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode())


def _read(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _cap_text(node):
    """Truncate README texts (text field) to README_MAX_CHARS."""
    if isinstance(node, dict):
        return {k: v[:README_MAX_CHARS] if k == "text" and isinstance(v, str) else _cap_text(v)
                for k, v in node.items()}
    return [_cap_text(v) for v in node] if isinstance(node, list) else node


def graphql(query: str, variables: dict) -> dict:
    if _mode:
        path = _snapshot_path(query, variables)
        if path.exists():
            return _read(path)
        if _mode == "replay":
            raise GitHubError(f"missing snapshot {path.name} for query {variables} (--record)")
    data = _cap_text(_graphql_live(query, variables))
    if _mode == "record":
        _write(path, data)
    return data


def _note_cost(data: dict) -> None:
    global spent, last_rate_limit
    rl = (data.get("data") or {}).get("rateLimit")
    if isinstance(rl, dict):
        with _spent_lock:
            spent += rl.get("cost") or 0
            last_rate_limit = rl


def log_usage() -> None:
    """Log GitHub GraphQL quota used in this process; replay and cached runs remain silent."""
    if spent and last_rate_limit:
        log.info("GitHub: spent %d GraphQL points, %s remaining, resets %s", spent,
                 last_rate_limit.get("remaining"), last_rate_limit.get("resetAt"))


def _graphql_live(query: str, variables: dict, retries: int = MAX_RETRIES) -> dict:
    reason = None
    for attempt in range(retries + 1):
        data, reason = _attempt(query, variables)
        if data is not None:
            _note_cost(data)
            return data
        if attempt < retries:
            wait = min(2**attempt * 5, 60)
            log.info("GitHub: %s — retry %d/%d in %d s", reason, attempt + 1, retries, wait)
            time.sleep(wait)
    raise GitHubError(f"GitHub did not respond after {retries} retries: {reason}")


def _batch(chunk: list[str], alias) -> dict[str, dict | None]:
    """{name: node | None (deleted)}. If batch fails (e.g. 502 timeout), split in half without retries.
    Single failing repo is retried; on persistent failure, it is skipped with a warning and tracked in last_failed."""
    q = "query{rateLimit{cost remaining resetAt} " + " ".join(alias(i, n) for i, n in enumerate(chunk)) + "}"
    try:
        resp = _cap_text(_graphql_live(q, {}, retries=(EVAL_SINGLE_RETRIES if _mode == "record" and _details_dir else MAX_RETRIES) if len(chunk) == 1 else 0))
    except GitHubError as e:
        if len(chunk) > 1:
            log.info("batch of %d failed (%s), splitting in half", len(chunk), e)
        if len(chunk) == 1:
            log.warning("warning: %s skipped: %s", chunk[0], e)
            last_failed.add(chunk[0])
            return {}
        mid = len(chunk) // 2
        return _batch(chunk[:mid], alias) | _batch(chunk[mid:], alias)
    data = resp.get("data") or {}
    # an alias that errored for any reason but NOT_FOUND is a failure, not a deleted repo
    failed = {e["path"][0] for e in resp.get("errors") or [] if e.get("path") and e.get("type") != "NOT_FOUND"}
    out = {}
    for i, name in enumerate(chunk):
        if f"r{i}" in failed and not data.get(f"r{i}"):
            log.warning("warning: %s skipped: GraphQL error", name)
            last_failed.add(name)
        else:
            out[name] = data.get(f"r{i}")
    return out


def search(query: str, limit: int) -> list[dict]:
    calls["search"] += 1
    data = graphql(SEARCH_GQL, {"q": query, "n": limit})["data"]
    return [n for n in data["search"]["nodes"] if n]


README_NAMES = ["README.md", "readme.md", "README.rst", "README", "Readme.md"]
DETAILS_WORKERS = 3  # parallel batches; higher risks secondary rate limits
DETAILS_CHUNK = 10  # 25 aliases with README and commit history hit HTTP 502 timeout
_NAME = re.compile(r"[\w.-]+/[\w.-]+")


def _alias(i: int, name: str) -> str:
    owner, repo = name.split("/")
    readmes = " ".join(f'm{k}: object(expression: "HEAD:{n}") {{ ... on Blob {{ text }} }}'
                       for k, n in enumerate(README_NAMES))
    return (f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(repo)}) {{ {readmes} "
            "defaultBranchRef{target{... on Commit{history(first:20){nodes{committedDate message: messageHeadline additions "
            "deletions author{name user{login}}}}}}}}")


def _fetch_details(chunk: list[str]) -> dict[str, dict | None]:
    out: dict[str, dict | None] = {}
    for name, repo in _batch(chunk, _alias).items():
        if not repo:
            out[name] = None
            continue
        texts = (repo.get(f"m{k}") for k in range(len(README_NAMES)))
        target = (repo.get("defaultBranchRef") or {}).get("target") or {}
        out[name] = {"readme": next((t["text"] for t in texts if t), None),
                     "commits": (target.get("history") or {}).get("nodes") or []}
    return out


def details(names: list[str]) -> dict[str, dict]:
    """README and latest 20 commits. Snapshot per repo (details/<hash>.json.gz), batches of DETAILS_CHUNK
    for missing entries only. {name: {"readme": str|None, "commits": list}}; deleted repos excluded."""
    out: dict[str, dict] = {}
    missing = []
    calls["details"] += -(-len([n for n in names if _NAME.fullmatch(n)]) // DETAILS_CHUNK)
    for n in (n for n in names if _NAME.fullmatch(n)):
        path = _cache_dir("details") / f"{_key(n.lower())}.json.gz" if _mode else None
        if path and path.exists() and not ((d := _read(path)) is None and _recheck(n)):
            if d is not None:
                out[n] = d
        elif _mode == "replay":
            raise GitHubError(f"missing details snapshot for {n} (--record)")
        else:
            missing.append(n)
    chunks = [missing[i:i + DETAILS_CHUNK] for i in range(0, len(missing), DETAILS_CHUNK)]
    with ThreadPoolExecutor(DETAILS_WORKERS) as pool:
        for k, (chunk, got) in enumerate(zip(chunks, pool.map(_fetch_details, chunks)), 1):
            log.info("details %d/%d", min(k * DETAILS_CHUNK, len(missing)), len(missing))
            _store_details(chunk, got, out)
    return out


def _store_details(chunk: list[str], got: dict[str, dict | None], out: dict[str, dict]) -> None:
    for name, d in got.items():
        if _mode == "record":
            _write(_cache_dir("details") / f"{_key(name.lower())}.json.gz", d)
        if d is not None:
            out[name] = d
    _record_skipped(chunk, got, "details")


def _recheck(name: str) -> bool:
    """record: recheck None marker (deleted/skipped) in shared cache once per process to prevent 502 permanent cache."""
    if _mode != "record" or not _details_dir or name in _rechecked:
        return False
    _rechecked.add(name)
    return True


def _record_skipped(chunk: list[str], got: dict, kind: str) -> None:
    """Record skipped repo in snapshot as None so replay produces identical behavior."""
    if _mode != "record":
        return
    for name in chunk:
        if name not in got and name in last_failed:
            _write(_cache_dir(kind) / f"{_key(name.lower())}.json.gz", None)


def _alias_full(i: int, name: str) -> str:
    """Search metadata + README + commits in a single alias (commits under recent alias)."""
    owner, repo = name.split("/")
    readmes = " ".join(f'm{k}: object(expression: "HEAD:{n}") {{ ... on Blob {{ text }} }}'
                       for k, n in enumerate(README_NAMES))
    return (f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(repo)}) {{ {NODE_FIELDS} {readmes} "
            "recent: defaultBranchRef{target{... on Commit{history(first:20){nodes{committedDate message: messageHeadline "
            "additions deletions author{name user{login}}}}}}}}")


def _split_full(repo: dict) -> dict:
    texts = (repo.get(f"m{k}") for k in range(len(README_NAMES)))
    target = (repo.get("recent") or {}).get("target") or {}
    node = {k: v for k, v in repo.items() if k != "recent" and not re.fullmatch(r"m\d+", k)}
    return {"node": node, "details": {"readme": next((t["text"] for t in texts if t), None),
                                      "commits": (target.get("history") or {}).get("nodes") or []}}


def refresh(names: list[str]) -> dict[str, dict]:
    """Fresh metadata + README + commits by name (for Index candidates): {name: {"node", "details"}}.
    Snapshot per repo (refresh/<hash>.json.gz); deleted repos excluded."""
    out: dict[str, dict] = {}
    missing = []
    calls["details"] += -(-len([n for n in names if _NAME.fullmatch(n)]) // DETAILS_CHUNK)
    for n in (n for n in names if _NAME.fullmatch(n)):
        path = _dir / "refresh" / f"{_key(n.lower())}.json.gz" if _mode else None
        if path and path.exists() and not ((d := _read(path)) is None and _recheck(n)):
            if d is not None:
                out[n] = d
        elif _mode == "replay":
            raise GitHubError(f"missing refresh snapshot for {n} (--record)")
        else:
            missing.append(n)
    for start in range(0, len(missing), DETAILS_CHUNK):
        log.info("refresh from Index: %d–%d of %d", start + 1, min(start + DETAILS_CHUNK, len(missing)), len(missing))
        chunk = missing[start:start + DETAILS_CHUNK]
        got = _batch(chunk, _alias_full)
        for name, repo in got.items():
            d = _split_full(repo) if repo else None
            if _mode == "record":
                _write(_dir / "refresh" / f"{_key(name.lower())}.json.gz", d)
            if d is not None:
                out[name] = d
        _record_skipped(chunk, got, "refresh")
    return out
