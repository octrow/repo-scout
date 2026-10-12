"""Index (ADR-0001): stdlib sqlite3, float32 BLOB vectors, cosine search via numpy; Verdicts."""
import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from repo_scout import semantic

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos(name TEXT PRIMARY KEY, display_name TEXT, meta TEXT, readme TEXT,
                                 fetched_at TEXT, vec BLOB, model TEXT);
CREATE TABLE IF NOT EXISTS verdicts(name TEXT, project TEXT, task TEXT, verdict TEXT, date TEXT);
"""


def default_path() -> Path:
    return Path(os.environ.get("REPO_SCOUT_INDEX") or Path.home() / ".local/share/repo-scout/index.db")


VERDICT = re.compile(r"→ (?:Inspect|Study \(.+\)|\u041e\u0441\u043c\u043e\u0442\u0440|\u0420\u0430\u0437\u0431\u043e\u0440 \(.+\))|(?:drop|doubt|\u043e\u0442\u0441\u0435\u0432|\u0441\u043f\u043e\u0440\u043d\u043e) \(.+\)")


def validate_verdict(repo: str, verdict: str, project: str, task: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", repo, re.ASCII) or repo.split("/")[1] in (".", ".."):
        raise ValueError(f"repo {repo!r}: owner/repo format required")
    if not VERDICT.fullmatch(verdict) or "\n" in verdict:
        raise ValueError(
            f"verdict {verdict!r}: '→ Inspect', '→ Study (goal)', 'drop (reason)', or 'doubt (what to clarify)'"
        )
    for label, value in (("project", project), ("task", task)):
        if not value.strip() or "\n" in value or "\r" in value:
            raise ValueError(f"{label} {value!r}: non-empty string without newlines required")


class Index:
    def __init__(self, path: Path | str, model: str | None = None):
        self.model = model or semantic.MODEL
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self._reembed()

    def _reembed(self) -> None:
        """Model migration: recompute vectors from saved READMEs and metadata without API calls."""
        stale = self.db.execute("SELECT name, meta, readme FROM repos WHERE model != ?", (self.model,)).fetchall()
        if not stale:
            return
        texts = [semantic.candidate_text(json.loads(m), r) for _, m, r in stale]
        with self.db:
            for (name, _, _), v in zip(stale, semantic.embed_docs(texts)):
                self.db.execute("UPDATE repos SET vec = ?, model = ? WHERE name = ?",
                                (np.asarray(v, dtype=np.float32).tobytes(), self.model, name))

    def upsert(self, row: dict, readme: str | None, vec: np.ndarray, now: datetime | None = None) -> None:
        meta = {k: row[k] for k in ("repo", "url", "desc", "topics", "stars", "lang")}
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO repos VALUES(?,?,?,?,?,?,?)",
                (row["repo"].lower(), row["repo"], json.dumps(meta, ensure_ascii=False), readme or "",
                 (now or datetime.now(UTC)).isoformat(), np.asarray(vec, dtype=np.float32).tobytes(), self.model))

    def top(self, task: str, n: int) -> list[str]:
        """Top-n repo names by closeness to task; linear scan across all vectors."""
        rows = self.db.execute("SELECT display_name, vec FROM repos").fetchall()
        if not rows:
            return []
        mat = np.stack([np.frombuffer(v, dtype=np.float32) for _, v in rows])
        scores = semantic.closeness(semantic.embed_task(task), mat)
        return [rows[i][0] for i in np.argsort(-scores)[:n]]

    def add_verdict(self, repo: str, verdict: str, project: str, task: str, now: datetime | None = None) -> None:
        validate_verdict(repo, verdict, project, task)
        with self.db:
            self.db.execute("INSERT INTO verdicts VALUES(?,?,?,?,?)",
                            (repo.lower(), project, task, verdict, (now or datetime.now(UTC)).date().isoformat()))

    def rows(self) -> list[dict]:
        """Index repos without vectors: key, name, meta, fetched_at, has_readme; case-insensitive name order."""
        q = "SELECT name, display_name, meta, fetched_at, readme != '' FROM repos ORDER BY display_name COLLATE NOCASE"
        return [{"key": k, "name": n, "meta": json.loads(m), "fetched_at": f, "has_readme": bool(r)}
                for k, n, m, f, r in self.db.execute(q)]

    def readme(self, name: str) -> str | None:
        row = self.db.execute("SELECT readme FROM repos WHERE name = ?", (name.lower(),)).fetchone()
        return row[0] or None if row else None

    def seen(self, names: list[str]) -> dict[str, str]:
        """'project: verdict (date)' — latest verdict per project, newest first; lower-case key."""
        out: dict[str, list[str]] = {}
        for name in names:
            q = ("SELECT project, verdict, date FROM verdicts WHERE name = ? ORDER BY date DESC, rowid DESC")
            seen_projects: set[str] = set()
            for project, verdict, date in self.db.execute(q, (name.lower(),)):
                if project not in seen_projects:
                    seen_projects.add(project)
                    out.setdefault(name.lower(), []).append(f"{project}: {verdict} ({date})")
        return {k: "; ".join(v) for k, v in out.items()}

    def forget(self, name: str) -> None:
        """Repo deleted on GitHub: remove from search (verdicts remain)."""
        with self.db:
            self.db.execute("DELETE FROM repos WHERE name = ?", (name.lower(),))

    def rename(self, old: str, new: str) -> None:
        """Repo renamed: old entry removed, verdicts migrate to new name."""
        with self.db:
            self.db.execute("DELETE FROM repos WHERE name = ?", (old.lower(),))
            self.db.execute("UPDATE verdicts SET name = ? WHERE name = ?", (new.lower(), old.lower()))

    def verdicts(self, project: str | None = None) -> list[tuple]:
        q = "SELECT project, name, verdict, task, date FROM verdicts"
        args: tuple = ()
        if project:
            q, args = q + " WHERE project = ?", (project,)
        return self.db.execute(q + " ORDER BY project, date, rowid", args).fetchall()
