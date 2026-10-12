"""Search form logic without UI: form state <-> CLI parameters, drafts, prompt text."""
import shlex
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .. import cli, llm, runs
from ..cli import _parser, compile_all, search_params, to_argv, validate_query
from ..command import self_argv

RUN_PREFIX, EVAL_PREFIX = "run:", "eval:"
EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"
DEV_DIR = Path.home() / "dev"
NUMBER_KEYS = ("months", "new_days", "limit", "min_closeness", "from_index", "round2_k", "stars_k")
FLAG_KEYS = ("no_round2", "no_stars_check")

AGENT_PROMPT = """Task (to find ready-made solutions on GitHub):
{task}

Suggest 3-6 query variants for repo-scout:
1. Task description in English, 1-3 sentences, what is needed: goes to --task, used to calculate Closeness.
2. Queries: synonyms, English terms, `language:`, `topic:`, `in:readme`. Do not use `stars:`: low stars count is no reason to drop.
Hard filters if needed: --lang, --must REGEX (required words), --exclude REGEX (forbidden words).

Reply with ONE line of format `repo-scout --task "..." "query 1" "query 2" ...` without explanations."""


@dataclass(frozen=True)
class Draft:
    key: str  # "run:<filename without .json>" or "eval:<name>"
    label: str
    path: Path


def default_state() -> dict:
    """Empty form: defaults taken from CLI parser."""
    ns = _parser().parse_args(["--task", "x", "q"])
    return params_to_state({**search_params(ns), "task": "", "queries": []})


def params_to_state(params: dict) -> dict:
    """Search parameters -> form field values (lists joined into newline-separated strings)."""
    base = search_params(_parser().parse_args(["--task", "x", "q"]))
    p = {**base, **{k: v for k, v in params.items() if k in base}}
    state = {k: p[k] for k in (*NUMBER_KEYS, *FLAG_KEYS, "task")}
    state.update(queries="\n".join(p["queries"]), must="\n".join(p["must"]),
                 exclude="\n".join(p["exclude"]), lang=p["lang"] or "", project=p["project"] or "", need=p["need"] or "")
    return state


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def state_to_params(state: dict) -> dict:
    """Form fields -> search parameters (as in `cli.search_params`)."""
    params = search_params(_parser().parse_args(["--task", "x", "q"]))
    for k in (*NUMBER_KEYS, *FLAG_KEYS):
        if state.get(k) is not None:
            params[k] = type(params[k])(state[k])
    params.update(task=(state.get("task") or "").strip(), queries=_lines(state.get("queries", "")),
                  must=_lines(state.get("must", "")), exclude=_lines(state.get("exclude", "")),
                  lang=(state.get("lang") or "").strip() or None,
                  project=(state.get("project") or "").strip() or None,
                  need=(state.get("need") or "").strip() or None)
    return params


def command_text(state: dict) -> str | None:
    """`repo-scout …` string for preview; None while task or queries are missing."""
    params = state_to_params(state)
    if not params["task"] or not params["queries"]:
        return None
    return shlex.join(["repo-scout", *to_argv(params)])


def run_argv(state: dict, out: Path) -> list[str]:
    """Subprocess argv: this repo-scout (see self_argv), Run path known in advance."""
    return [*self_argv(), *to_argv(state_to_params(state), ["--out", str(out)])]


def out_path(task: str, now: datetime) -> Path:
    return runs.free_path(runs.runs_dir() / f"{now.strftime('%Y%m%d-%H%M%S')}-{runs.slug(task)}.json")


def check_queries(text: str) -> str | None:
    """Error of first invalid query or None."""
    for q in _lines(text):
        try:
            validate_query(q)
        except ValueError as e:
            return str(e)
    return None


def check_regexes(flag: str, text: str) -> str | None:
    try:
        compile_all(flag, _lines(text))
    except ValueError as e:
        return str(e)
    return None


def form_errors(state: dict) -> list[str]:
    """All issues preventing a search run."""
    errors = []
    if not (state.get("task") or "").strip():
        errors.append("Task description is required")
    if not _lines(state.get("queries", "")):
        errors.append("Add at least one query")
    errors += [e for e in (check_queries(state.get("queries", "")),
                           check_regexes("--must", state.get("must", "")),
                           check_regexes("--exclude", state.get("exclude", ""))) if e]
    return errors


def draft_to_state(d: llm.Draft, need: str) -> dict:
    """LLM draft -> form fields (search is not launched; other fields untouched)."""
    state = params_to_state(cli.draft_params(d, need))
    return {k: state[k] for k in ("task", "queries", "must", "exclude", "lang", "need")}


def agent_prompt(task: str) -> str:
    return AGENT_PROMPT.format(task=task.strip() or "(describe the task)")


def eval_to_state(path: Path) -> dict:
    """Dataset eval/*.toml -> form."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return params_to_state({"task": data.get("task", ""), "queries": data.get("queries", []),
                            "lang": data.get("lang") or None, "must": data.get("must", []),
                            "exclude": data.get("exclude", []), "project": data.get("name")})


def run_to_state(path: Path) -> dict:
    return params_to_state(runs.load(path)["params"])


def list_drafts(eval_dir: Path = EVAL_DIR) -> list[Draft]:
    """Past Runs (newest first, corrupt skipped) and eval datasets."""
    out = [Draft(f"{RUN_PREFIX}{s.path.stem}", f"Run: {(s.created_at or '')[:10]} {s.task}", s.path)
           for s in runs.list_runs() if not s.error]
    for p in sorted(eval_dir.glob("*.toml")):
        try:
            tomllib.loads(p.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        out.append(Draft(f"{EVAL_PREFIX}{p.stem}", f"Eval: {p.stem}", p))
    return out


def load_draft(draft: Draft) -> dict:
    return run_to_state(draft.path) if draft.key.startswith(RUN_PREFIX) else eval_to_state(draft.path)


def project_suggestions(verdict_projects: list[str], dev_dir: Path = DEV_DIR) -> list[str]:
    """Projects from Index verdicts and folder names in ~/dev, deduplicated."""
    dirs = sorted(p.name for p in dev_dir.iterdir() if p.is_dir() and not p.name.startswith(".")) \
        if dev_dir.is_dir() else []
    return list(dict.fromkeys([*verdict_projects, *dirs]))
