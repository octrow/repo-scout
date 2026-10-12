"""Fit (advanced mode): a TypeSafe System One model (Jev) judges whether each top candidate is a usable base for the task.

Standard library only. One request per run with one yes/no question per candidate (speculative fan-out).
Fit is a column: it never drops or reorders rows; without a key `available()` = False and nothing is sent.
The key is never printed: errors mention the variable name only.
"""
import http.client
import json
import urllib.error
import urllib.request

from repo_scout import llm
from repo_scout.log import log

KEY_VAR, MODEL_VAR, URL_VAR = "TYPESAFE_API_KEY", "TYPESAFE_MODEL", "TYPESAFE_BASE_URL"
DEFAULT_MODEL, DEFAULT_URL = "jev-latest", "https://api.typesafe.ai/v1/systemone"
KEYS_URL = "https://console.typesafe.ai/keys"
FIT_K = 20  # top kept rows judged per run: one request, ~5k input tokens
MAX_TEXT = 1000  # chars of name/description/topics/README per candidate
TIMEOUT_S = 60
QUESTION = ("Could `repo` serve as the base for the `task` in the state, so the user builds on it "
            "instead of writing their own? Judge from its description and README.")


class SystemOneError(Exception):
    pass


def available() -> bool:
    return bool(llm.setting(KEY_VAR))


def model() -> str:
    return llm.setting(MODEL_VAR, DEFAULT_MODEL)


def _post(body: dict) -> dict:
    req = urllib.request.Request(llm.setting(URL_VAR, DEFAULT_URL), data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {llm.setting(KEY_VAR)}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemOneError(f"HTTP error {e.code}; check {KEY_VAR}") from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, ValueError) as e:
        raise SystemOneError(f"unavailable: {type(e).__name__}") from None
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise SystemOneError("unexpected response format")
    return data


def fit(task: str, texts: dict[str, str]) -> dict[str, float]:
    """repo -> probability that it is a usable base for the task; malformed answers are skipped."""
    ids = {f"r{i}": repo for i, repo in enumerate(texts)}
    questions = {qid: {"type": "noul", "instructions": {"repo": texts[repo][:MAX_TEXT], "question": QUESTION}}
                 for qid, repo in ids.items()}
    answers = _post({"model": model(), "state": {"task": task}, "questions": questions})["answers"]
    out = {}
    for qid, repo in ids.items():
        value = (answers.get(qid) or {}).get("noul") if isinstance(answers.get(qid), dict) else None
        if isinstance(value, int | float) and 0 <= value <= 1:
            out[repo] = float(value)
    return out


def add_fit(rows: list[dict], task: str | None, texts: dict[str, str], k: int) -> None:
    """'fit' for the top-k kept rows; any failure is a warning, the search result stays as it is."""
    top = [r for r in rows if not r["stop"] and r["repo"] in texts][:k]
    if not (task and top and available()):
        return
    log.info("fit: asking %s about %d candidates", model(), len(top))
    try:
        scores = fit(task, {r["repo"]: texts[r["repo"]] for r in top})
    except SystemOneError as e:
        log.warning("warning: fit column skipped: %s", e)
        return
    for r in top:
        if r["repo"] in scores:
            r["fit"] = round(scores[r["repo"]], 2)
