"""GitHub GraphQL через `gh api graphql` с ретраями при rate limit."""
import gzip
import hashlib
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

MAX_RETRIES = 3
TRANSIENT = (502, 503, 504)
README_MAX_CHARS = 6_000  # хватает для регэкспов и эмбеддинга; держит снапшоты небольшими

NODE_FIELDS = """nameWithOwner url description stargazerCount forkCount pushedAt createdAt isArchived isFork isTemplate
repositoryTopics(first:20){nodes{topic{name}}}
parent{nameWithOwner} primaryLanguage{name}
defaultBranchRef{target{... on Commit{history{totalCount}}}}"""
SEARCH_GQL = ("query($q:String!,$n:Int!){rateLimit{cost remaining resetAt}\n"
              "search(query:$q,type:REPOSITORY,first:$n){nodes{... on Repository{\n" + NODE_FIELDS + "}}}}")

last_rate_limit: dict | None = None
calls: Counter = Counter()  # логические вызовы: search, details (пачки по DETAILS_CHUNK, и из снапшотов тоже)
_mode: str | None = None  # "record" | "replay" | None
_dir: Path | None = None


class GitHubError(Exception):
    pass


def _parse(stdout: str) -> dict | None:
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _attempt(query: str, variables: dict) -> tuple[dict | None, str | None]:
    """Один вызов gh: (данные, None) при успехе, (None, None) если нужен ретрай, иначе GitHubError."""
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
        print(f"предупреждение GraphQL: {msgs}", file=sys.stderr)
        return data, None
    if out.returncode:
        if "429" in err or "rate limit" in err.lower() or any(f"HTTP {c}" in err for c in TRANSIENT):
            return None, err
        raise GitHubError(f"gh завершился с ошибкой: {err or out.stdout.strip()}")
    if data is None:
        return None, "ответ без JSON"
    if errors:
        raise GitHubError(f"GraphQL: {errors[0].get('message', errors)}")
    return data, None


def configure(mode: str | None, directory: Path | str | None) -> None:
    """Включить запись/воспроизведение снапшотов ответов GitHub (None = сеть как обычно)."""
    global _mode, _dir
    _mode, _dir = mode, Path(directory) if directory else None
    if mode == "record":
        _dir.mkdir(parents=True, exist_ok=True)
        meta = _dir / "meta.json"
        if not meta.exists():  # повторная запись дописывает недостающее, дата снимка остаётся
            meta.write_text(json.dumps({"recorded_at": datetime.now(UTC).isoformat()}))


def recorded_at() -> datetime:
    path = _dir / "meta.json"
    if not path.exists():
        raise GitHubError(f"нет снапшота {path}: сначала --record")
    return datetime.fromisoformat(json.loads(path.read_text())["recorded_at"])


def _key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _snapshot_path(query: str, variables: dict) -> Path:
    return _dir / f"{_key(json.dumps({'query': query, 'variables': variables}, sort_keys=True))}.json.gz"


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as g:
        g.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode())


def _read(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _cap_text(node):
    """Обрезать тексты README (поле text) до README_MAX_CHARS."""
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
            raise GitHubError(f"нет снапшота {path.name} для запроса {variables} (--record)")
    data = _cap_text(_graphql_live(query, variables))
    if _mode == "record":
        _write(path, data)
    return data


def _graphql_live(query: str, variables: dict) -> dict:
    reason = None
    for attempt in range(MAX_RETRIES + 1):
        data, reason = _attempt(query, variables)
        if data is not None:
            return data
        if attempt < MAX_RETRIES:
            time.sleep(min(2**attempt * 5, 60))
    raise GitHubError(f"лимит GitHub, {MAX_RETRIES} повтора не помогли: {reason}")


def search(query: str, limit: int) -> list[dict]:
    global last_rate_limit
    calls["search"] += 1
    data = graphql(SEARCH_GQL, {"q": query, "n": limit})["data"]
    last_rate_limit = data.get("rateLimit")
    return [n for n in data["search"]["nodes"] if n]


README_NAMES = ["README.md", "readme.md", "README.rst", "README", "Readme.md"]
DETAILS_CHUNK = 10  # 25 алиасов с README и историей дают HTTP 502 (таймаут GitHub)
_NAME = re.compile(r"[\w.-]+/[\w.-]+")


def _alias(i: int, name: str) -> str:
    owner, repo = name.split("/")
    readmes = " ".join(f'm{k}: object(expression: "HEAD:{n}") {{ ... on Blob {{ text }} }}'
                       for k, n in enumerate(README_NAMES))
    return (f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(repo)}) {{ {readmes} "
            "defaultBranchRef{target{... on Commit{history(first:20){nodes{committedDate message: messageHeadline additions "
            "deletions author{name user{login}}}}}}}}")


def _fetch_details(chunk: list[str]) -> dict[str, dict | None]:
    q = "query{rateLimit{cost remaining resetAt} " + " ".join(_alias(i, n) for i, n in enumerate(chunk)) + "}"
    data = _cap_text(_graphql_live(q, {}))["data"]
    out: dict[str, dict | None] = {}
    for i, name in enumerate(chunk):
        repo = data.get(f"r{i}")
        if not repo:
            out[name] = None
            continue
        texts = (repo.get(f"m{k}") for k in range(len(README_NAMES)))
        target = (repo.get("defaultBranchRef") or {}).get("target") or {}
        out[name] = {"readme": next((t["text"] for t in texts if t), None),
                     "commits": (target.get("history") or {}).get("nodes") or []}
    return out


def details(names: list[str]) -> dict[str, dict]:
    """README и последние 20 коммитов. Снапшот по репо (details/<хэш имени>.json.gz), пачки по DETAILS_CHUNK
    только для недостающих. {name: {"readme": str|None, "commits": list}}; удалённые репо не попадают в ответ."""
    out: dict[str, dict] = {}
    missing = []
    calls["details"] += -(-len([n for n in names if _NAME.fullmatch(n)]) // DETAILS_CHUNK)
    for n in (n for n in names if _NAME.fullmatch(n)):
        path = _dir / "details" / f"{_key(n.lower())}.json.gz" if _mode else None
        if path and path.exists():
            if (d := _read(path)) is not None:
                out[n] = d
        elif _mode == "replay":
            raise GitHubError(f"нет снапшота деталей {n} (--record)")
        else:
            missing.append(n)
    for start in range(0, len(missing), DETAILS_CHUNK):
        for name, d in _fetch_details(missing[start:start + DETAILS_CHUNK]).items():
            if _mode == "record":
                _write(_dir / "details" / f"{_key(name.lower())}.json.gz", d)
            if d is not None:
                out[name] = d
    return out


def _alias_full(i: int, name: str) -> str:
    """Метаданные как в поиске + README + коммиты одним алиасом (commits под алиасом recent)."""
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
    """Свежие метаданные + README + коммиты по именам (для строк из Индекса): {name: {"node", "details"}}.
    Снапшот по репо (refresh/<хэш имени>.json.gz); удалённые репо не попадают в ответ."""
    out: dict[str, dict] = {}
    missing = []
    calls["details"] += -(-len([n for n in names if _NAME.fullmatch(n)]) // DETAILS_CHUNK)
    for n in (n for n in names if _NAME.fullmatch(n)):
        path = _dir / "refresh" / f"{_key(n.lower())}.json.gz" if _mode else None
        if path and path.exists():
            if (d := _read(path)) is not None:
                out[n] = d
        elif _mode == "replay":
            raise GitHubError(f"нет снапшота обновления {n} (--record)")
        else:
            missing.append(n)
    for start in range(0, len(missing), DETAILS_CHUNK):
        chunk = missing[start:start + DETAILS_CHUNK]
        q = "query{rateLimit{cost remaining resetAt} " + " ".join(_alias_full(i, n) for i, n in enumerate(chunk)) + "}"
        data = _cap_text(_graphql_live(q, {}))["data"]
        for i, name in enumerate(chunk):
            d = _split_full(data[f"r{i}"]) if data.get(f"r{i}") else None
            if _mode == "record":
                _write(_dir / "refresh" / f"{_key(name.lower())}.json.gz", d)
            if d is not None:
                out[name] = d
    return out
