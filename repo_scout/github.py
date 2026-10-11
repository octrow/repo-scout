"""GitHub GraphQL через `gh api graphql` с ретраями при rate limit."""
import json
import subprocess
import sys
import time

MAX_RETRIES = 3

SEARCH_GQL = """query($q:String!,$n:Int!){rateLimit{cost remaining resetAt}
search(query:$q,type:REPOSITORY,first:$n){nodes{... on Repository{
nameWithOwner url description stargazerCount forkCount pushedAt createdAt isArchived isFork
parent{nameWithOwner} primaryLanguage{name}
defaultBranchRef{target{... on Commit{history{totalCount}}}}}}}}"""

last_rate_limit: dict | None = None


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
        if "429" in err or "rate limit" in err.lower():
            return None, err
        raise GitHubError(f"gh завершился с ошибкой: {err or out.stdout.strip()}")
    if data is None:
        return None, "ответ без JSON"
    if errors:
        raise GitHubError(f"GraphQL: {errors[0].get('message', errors)}")
    return data, None


def graphql(query: str, variables: dict) -> dict:
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
    data = graphql(SEARCH_GQL, {"q": query, "n": limit})["data"]
    last_rate_limit = data.get("rateLimit")
    return [n for n in data["search"]["nodes"] if n]
