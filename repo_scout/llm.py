"""Черновик LLM: по Потребности модель предлагает Описание задачи, Запросы и Жёсткие условия.

Только stdlib. Модель вызывается до поиска и не влияет на выдачу; без ключа `available()` = False.
Ответ модели недоверенный: JSON, типы, лимиты, `validate_query`, `compile_all`.
Ключ нигде не печатается и не попадает в сообщения: ошибки называют только имена переменных.
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
KEY_VAR, MODEL_VAR, URL_VAR = "OMNIROUTE_API_KEY", "OMNIROUTE_MODEL", "OMNIROUTE_BASE_URL"
DEFAULT_MODEL, DEFAULT_URL = "free-stack", "http://127.0.0.1:20128/v1"
TIMEOUT_S = 90  # free-stack отвечает ~8 с, но маршрутизируется по разным моделям
MAX_QUERIES, MAX_QUERY_CHARS, MAX_TASK_CHARS, MAX_REGEXES = 10, 256, 600, 10
MAX_NEED_CHARS = 2_000
NO_KEY = f"нет ключа LLM: задайте {KEY_VAR} (и при необходимости {MODEL_VAR}, {URL_VAR}) в окружении или в .env"

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

last_stats: dict = {}  # токены и секунды последнего draft() (из снапшота при replay)


class LLMError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Редирект = ошибка: заголовок Authorization не должен уйти на чужой адрес."""

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


def _env_file() -> dict[str, str]:
    """KEY=VALUE из .env (комментарии и пустые строки игнорируются, кавычки снимаются)."""
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
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


def _setting(name: str, default: str = "") -> str:
    """Реальное окружение главнее .env."""
    return (os.environ.get(name) or _env_file().get(name) or default).strip()


def available() -> bool:
    return bool(_setting(KEY_VAR))


def model() -> str:
    return _setting(MODEL_VAR, DEFAULT_MODEL)


def _post(messages: list[dict]) -> dict:
    """POST {base}/chat/completions; в ошибках только статус, без ключа и тела запроса."""
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
        raise LLMError(f"LLM ответила ошибкой HTTP {e.code}; проверьте {KEY_VAR} и {MODEL_VAR}") from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        raise LLMError(f"LLM недоступна ({_setting(URL_VAR, DEFAULT_URL)}): нет ответа за {TIMEOUT_S} с") from None
    except ValueError:
        raise LLMError("LLM вернула не JSON") from None
    if not isinstance(data, dict):
        raise LLMError("LLM вернула ответ неожиданной формы")
    return data


def _tokens(response: dict) -> int:
    """total_tokens из usage; кривой usage не роняет Черновик."""
    try:
        return int((response.get("usage") or {}).get("total_tokens") or 0)
    except (AttributeError, TypeError, ValueError, OverflowError):
        log.warning("Черновик LLM: usage неожиданной формы, токены считаем нулём")
        return 0


def _snapshot_path(messages: list[dict]) -> Path | None:
    mode, directory = github.snapshot()
    if not mode:
        return None
    text = json.dumps({"model": model(), "messages": messages}, ensure_ascii=False, sort_keys=True)
    return directory / "llm" / f"{hashlib.sha256(text.encode()).hexdigest()[:16]}.json.gz"


def _chat(messages: list[dict], pending: list | None = None) -> str:
    """Текст ответа модели. В record новые ответы не пишутся сразу, а ставятся в `pending`:
    их сохранит draft() только после успешной проверки."""
    mode, _ = github.snapshot()
    path = _snapshot_path(messages)
    if path and path.exists():
        rec = github._read(path)
    elif mode == "replay":
        raise LLMError(f"нет снапшота ответа LLM {path.name} (--record)")
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
        tokens = _tokens(response)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise LLMError("LLM вернула ответ неожиданной формы") from None
    last_stats["tokens"] = last_stats.get("tokens", 0) + tokens
    last_stats["seconds"] = round(last_stats.get("seconds", 0) + seconds, 2)
    return text


def _json_object(text: str) -> dict:
    """JSON из текста, в том числе из блока ```json или с лишней болтовнёй вокруг."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    for chunk in ([fenced.group(1)] if fenced else []) + [text, text[text.find("{"):text.rfind("}") + 1]]:
        try:
            data = json.loads(chunk)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    raise ValueError("ответ не содержит JSON-объект")


def _strings(data: dict, key: str, limit: int, chars: int) -> tuple[str, ...]:
    value = data.get(key) or []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"поле {key} должно быть списком строк")
    items = tuple(dict.fromkeys(v.strip() for v in value if v.strip()))
    if len(items) > limit:
        raise ValueError(f"поле {key}: {len(items)} элементов, максимум {limit}")
    if long := next((v for v in items if len(v) > chars), None):
        raise ValueError(f"поле {key}: элемент длиннее {chars} символов: {long[:40]!r}")
    return items


LANG_RE = re.compile(r"[A-Za-z0-9+#.\-]{1,30}")
NO_LANG = {"", "none", "any", "null", "n/a"}


def _lang(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("поле lang должно быть строкой или null")
    value = value.strip()
    if value.lower() in NO_LANG:
        return None
    if not LANG_RE.fullmatch(value):
        raise ValueError(f"поле lang должно быть одним названием языка, получено {value[:40]!r}")
    return value


def _quantified(pattern: str, i: int) -> bool:
    return i < len(pattern) and pattern[i] in "+*{"


def reject_nested_quantifiers(field: str, patterns: tuple[str, ...]) -> None:
    """Группа с квантификатором внутри и квантификатором снаружи, например `(\\w+\\s?)+`: ReDoS."""
    for pat in patterns:
        stack, in_class, i = [False], False, 0  # stack: есть ли квантификатор внутри открытой группы
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
                    raise ValueError(f"поле {field}: вложенные квантификаторы в {pat[:40]!r} (риск ReDoS)")
                stack[-1] = stack[-1] or inner or _quantified(pat, i + 1)
            elif c in "+*{":
                stack[-1] = True
            i += 1


def parse_draft(text: str) -> Draft:
    """Проверенный Черновик из ответа модели; нарушение — ValueError с причиной."""
    from repo_scout.cli import validate_query  # поздний импорт: cli вызывает llm лениво

    data = _json_object(text)
    task = data.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("поле task должно быть непустой строкой")
    if len(task.strip()) > MAX_TASK_CHARS:
        raise ValueError(f"поле task длиннее {MAX_TASK_CHARS} символов")
    queries = _strings(data, "queries", MAX_QUERIES, MAX_QUERY_CHARS)
    if not queries:
        raise ValueError("поле queries пусто")
    for q in queries:
        validate_query(q)
    must, exclude = (_strings(data, k, MAX_REGEXES, MAX_QUERY_CHARS) for k in ("must", "exclude"))
    compile_all("must", list(must)), compile_all("exclude", list(exclude))
    reject_nested_quantifiers("must", must), reject_nested_quantifiers("exclude", exclude)
    return Draft(task.strip(), queries, _lang(data.get("lang")), must, exclude)


def draft(need: str) -> Draft:
    """Черновик по Потребности. Невалидный ответ: один повтор с текстом ошибки, потом LLMError."""
    need = need.strip()
    if not need:
        raise LLMError("опишите, что ищем")
    last_stats.clear()
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Need:\n{need[:MAX_NEED_CHARS]}"}]
    pending: list = []  # снапшоты record: пишем только после успешной проверки
    for attempt in (1, 2):
        reply = _chat(messages, pending)
        try:
            result = parse_draft(reply)
            for path, rec in pending:
                github._write(path, rec)
            return result
        except ValueError as e:
            log.info("Черновик LLM: ответ не прошёл проверку (попытка %d): %s", attempt, e)
            if attempt == 2:
                raise LLMError(f"LLM дважды вернула непригодный ответ: {e}") from e
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"Invalid: {e}. Reply with the corrected JSON object only."}]
    raise AssertionError("unreachable")
