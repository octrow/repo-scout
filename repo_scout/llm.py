"""LLM draft: model suggests Task description, Queries, and Hard conditions from user's Need.

Standard library only. Called before search and does not affect ranking; without key `available()` = False.
Model output is untrusted: JSON validation, type checks, bounds, `validate_query`, `compile_all`.
The key is never printed or included in messages: errors mention variable names only.
"""
import hashlib
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from repo_scout import github
from repo_scout.conditions import compile_all
from repo_scout.log import log

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
# any OpenAI-compatible /chat/completions endpoint; the defaults point at a local OmniRoute (free models)
KEY_VAR, MODEL_VAR, URL_VAR = "LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"
ALIASES = {KEY_VAR: "OMNIROUTE_API_KEY", MODEL_VAR: "OMNIROUTE_MODEL", URL_VAR: "OMNIROUTE_BASE_URL"}  # older names
DEFAULT_MODEL, DEFAULT_URL = "free-stack", "http://127.0.0.1:20128/v1"
TIMEOUT_S = 90  # free-stack responds in ~8s, but routes across different models
MAX_QUERIES, MAX_QUERY_CHARS, MAX_TASK_CHARS, MAX_REGEXES = 10, 256, 600, 10
MAX_NEED_CHARS = 2_000
NO_KEY = f"LLM draft needs a key. Run: repo-scout config (or set {KEY_VAR}, and {URL_VAR} and {MODEL_VAR} if needed)"

SYSTEM_PROMPT = """You turn a user's need (any language) into a draft for a GitHub repository search.
Reply with ONE JSON object and nothing else:
{"task": str, "queries": [str], "lang": str|null, "must": [str], "exclude": [str]}
Rules:
- task: English, 1-3 sentences, what the user needs to find (this text is used for semantic similarity).
- queries: 4-8 GitHub search queries: synonyms and English terms, `language:` and `topic:` qualifiers,
  `in:readme` where useful. Never use `stars:` (few stars is not a reason to drop a repo). Each query is short.
- lang: programming language the user requires, else null.
- must / exclude: optional Python regexes (case-insensitive) searched in README, topics and description:
  must = words every result needs, exclude = words that rule a result out. Empty lists if unsure."""

last_stats: dict = {}  # tokens and seconds of last draft() (from snapshot in replay)


class LLMError(Exception):
    pass


def _why(e: Exception) -> str:
    """Reason without response body or headers: timeout != connection refused."""
    reason = getattr(e, "reason", e)
    if isinstance(reason, TimeoutError):
        return f"no response within {TIMEOUT_S}s"
    if isinstance(reason, ConnectionRefusedError):
        return "connection refused — server not running?"
    return f"no connection ({type(reason).__name__})"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are treated as errors to prevent Authorization leakage."""

    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


@dataclass(frozen=True)
class Draft:
    task: str
    queries: tuple[str, ...]
    lang: str | None = None
    must: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


def user_env_path() -> Path:
    """Settings file of an installed repo-scout (`repo-scout config` writes it); ENV_FILE is the dev checkout's."""
    return Path(os.environ.get("REPO_SCOUT_ENV") or Path.home() / ".config/repo-scout/.env")


def parse_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE from a .env file (comments and blank lines ignored, quotes stripped)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    out = {}
    for line in lines:
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def _env_file() -> dict[str, str]:
    """User settings, overridden by the dev checkout's .env."""
    return {**parse_env(user_env_path()), **parse_env(ENV_FILE)}


def setting(name: str, default: str = "") -> str:
    """Real environment takes precedence over .env; an older alias name counts after the new one."""
    names = [name, *([ALIASES[name]] if name in ALIASES else [])]
    file = _env_file()
    return next((v for v in [*(os.environ.get(n) for n in names), *(file.get(n) for n in names)] if v), default).strip()


_setting = setting


def available() -> bool:
    return bool(_setting(KEY_VAR))


GUI_VAR = "REPO_SCOUT_GUI_DRAFT"  # eval gate failed (Draft found 24 vs agent 28, eval/BASELINE.md Phase 9): opt-in


def gui_enabled() -> bool:
    """GUI button only on explicit opt-in; `repo-scout draft` needs just the key."""
    return available() and _setting(GUI_VAR) in ("1", "true", "yes")


def model() -> str:
    return _setting(MODEL_VAR, DEFAULT_MODEL)


def _post(messages: list[dict]) -> dict:
    """POST {base}/chat/completions; errors show status only, no key or payload."""
    key = _setting(KEY_VAR)
    if not key:
        raise LLMError(NO_KEY)
    body = json.dumps({"model": model(), "messages": messages}).encode()
    req = urllib.request.Request(_setting(URL_VAR, DEFAULT_URL).rstrip("/") + "/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with _OPENER.open(req, timeout=TIMEOUT_S) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        raise LLMError(f"The LLM returned HTTP error {e.code}. Check {KEY_VAR} and {MODEL_VAR}") from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
        raise LLMError(f"The LLM at {_setting(URL_VAR, DEFAULT_URL)} is not reachable: {_why(e)}") from None
    except ValueError:
        raise LLMError("The LLM reply is not JSON") from None
    if not isinstance(data, dict):
        raise LLMError("The LLM reply has an unexpected format")
    return data


def _tokens(response: dict) -> int:
    """Extract total_tokens from usage; malformed usage does not fail draft."""
    try:
        return int((response.get("usage") or {}).get("total_tokens") or 0)
    except (AttributeError, TypeError, ValueError, OverflowError):
        log.warning("LLM draft: unexpected usage format, treating tokens as 0")
        return 0


def _snapshot_path(messages: list[dict]) -> Path | None:
    mode, directory = github.snapshot()
    if not mode:
        return None
    text = json.dumps({"model": model(), "messages": messages}, ensure_ascii=False, sort_keys=True)
    return directory / "llm" / f"{hashlib.sha256(text.encode()).hexdigest()[:16]}.json.gz"


def _chat(messages: list[dict], pending: list | None = None) -> str:
    """Model response text. In record mode, responses are queued in `pending` and written after validation."""
    mode, _ = github.snapshot()
    path = _snapshot_path(messages)
    if path and path.exists():
        rec = github._read(path)
    elif mode == "replay":
        raise LLMError(f"No LLM reply snapshot {path.name}. Record it with --record")
    else:
        started = time.monotonic()
        rec = {"response": _post(messages), "seconds": round(time.monotonic() - started, 2)}
        if mode == "record":
            if pending is None:
                github._write(path, rec)
            else:
                pending.append((path, rec))
    try:
        response, seconds = rec["response"], float(rec["seconds"])
        text = response["choices"][0]["message"]["content"] or ""
        if not isinstance(text, str):
            raise TypeError
        tokens = _tokens(response)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise LLMError("The LLM reply has an unexpected format") from None
    last_stats["tokens"] = last_stats.get("tokens", 0) + tokens
    last_stats["seconds"] = round(last_stats.get("seconds", 0) + seconds, 2)
    return text


def _json_object(text: str) -> dict:
    """Extract JSON object from text, including markdown fences or surrounding chatter."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    decoder = json.JSONDecoder()
    for chunk in ([fenced.group(1)] if fenced else []) + [text]:
        for i in (m.start() for m in re.finditer(r"\{", chunk)):
            try:
                data, _ = decoder.raw_decode(chunk, i)
            except ValueError:
                continue
            if isinstance(data, dict):
                return data
    raise ValueError("response does not contain a JSON object")


def _strings(data: dict, key: str, limit: int, chars: int) -> tuple[str, ...]:
    value = data.get(key) or []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"field {key} must be a list of strings")
    items = tuple(dict.fromkeys(v.strip() for v in value if v.strip()))
    if len(items) > limit:
        raise ValueError(f"field {key}: {len(items)} items, maximum {limit}")
    if long := next((v for v in items if len(v) > chars), None):
        raise ValueError(f"field {key}: item longer than {chars} characters: {long[:40]!r}")
    return items


LANG_RE = re.compile(r"[A-Za-z0-9+#.\-]{1,30}")
NO_LANG = {"", "none", "any", "null", "n/a"}


def _lang(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("field lang must be a string or null")
    value = value.strip()
    if value.lower() in NO_LANG:
        return None
    if not LANG_RE.fullmatch(value):
        raise ValueError(f"field lang must be a single language name, got {value[:40]!r}")
    return value


def _quantified(pattern: str, i: int) -> bool:
    return i < len(pattern) and pattern[i] in "+*{"


def reject_nested_quantifiers(field: str, patterns: tuple[str, ...]) -> None:
    """Reject patterns with nested quantifiers (e.g. `(\\w+\\s?)+`) to avoid ReDoS."""
    for pat in patterns:
        stack, in_class, i = [False], False, 0  # stack: track quantifier inside open group
        while i < len(pat):
            c = pat[i]
            if c == "\\":
                i += 1
            elif in_class:
                in_class = c != "]"
            elif c == "[":
                in_class = True
            elif c == "(":
                stack.append(False)
            elif c == ")" and len(stack) > 1:
                inner = stack.pop()
                if inner and _quantified(pat, i + 1):
                    raise ValueError(f"field {field}: nested quantifiers in {pat[:40]!r} (ReDoS risk)")
                stack[-1] = stack[-1] or inner or _quantified(pat, i + 1)
            elif c in "+*{":
                stack[-1] = True
            i += 1


def parse_draft(text: str) -> Draft:
    """Validate draft from model response; raises ValueError on violation."""
    from repo_scout.cli import validate_query  # lazy import: cli calls llm lazily

    data = _json_object(text)
    task = data.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("field task must be a non-empty string")
    if len(task.strip()) > MAX_TASK_CHARS:
        raise ValueError(f"field task longer than {MAX_TASK_CHARS} characters")
    queries = _strings(data, "queries", MAX_QUERIES, MAX_QUERY_CHARS)
    if not queries:
        raise ValueError("field queries is empty")
    for q in queries:
        validate_query(q)
    must, exclude = (_strings(data, k, MAX_REGEXES, MAX_QUERY_CHARS) for k in ("must", "exclude"))
    compile_all("must", list(must)), compile_all("exclude", list(exclude))
    reject_nested_quantifiers("must", must), reject_nested_quantifiers("exclude", exclude)
    return Draft(task.strip(), queries, _lang(data.get("lang")), must, exclude)


def draft(need: str) -> Draft:
    """Generate draft from need. Retries once with error explanation before raising LLMError."""
    need = need.strip()
    if not need:
        raise LLMError("Describe what you are looking for")
    last_stats.clear()
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Need:\n{need[:MAX_NEED_CHARS]}"}]
    pending: list = []  # queued snapshots: written only after successful validation
    for attempt in (1, 2):
        reply = _chat(messages, pending)
        try:
            result = parse_draft(reply)
            for path, rec in pending:
                github._write(path, rec)
            return result
        except ValueError as e:
            log.info("LLM draft: response validation failed (attempt %d): %s", attempt, e)
            if attempt == 2:
                raise LLMError(f"The LLM gave an invalid reply twice: {e}") from e
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"Invalid: {e}. Reply with the corrected JSON object only."}]
    raise AssertionError("unreachable")
