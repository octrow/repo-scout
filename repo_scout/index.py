"""Индекс (ADR-0001): stdlib sqlite3, векторы float32 BLOB, перебор косинуса в numpy; Вердикты."""
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


VERDICT = re.compile(r"→ Осмотр|→ Разбор \(.+\)|отсев \(.+\)|спорно \(.+\)")


def validate_verdict(repo: str, verdict: str, project: str, task: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", repo, re.ASCII) or repo.split("/")[1] in (".", ".."):
        raise ValueError(f"репо {repo!r}: нужен вид owner/repo")
    if not VERDICT.fullmatch(verdict) or "\n" in verdict:
        raise ValueError(f"вердикт {verdict!r}: «→ Осмотр», «→ Разбор (цель)», «отсев (причина)» или «спорно (что уточнить)»")
    for label, value in (("проект", project), ("задача", task)):
        if not value.strip() or "\n" in value or "\r" in value:
            raise ValueError(f"{label} {value!r}: нужна непустая строка без переводов строки")


class Index:
    def __init__(self, path: Path | str, model: str | None = None):
        self.model = model or semantic.MODEL
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self._reembed()

    def _reembed(self) -> None:
        """Смена модели: вектора из сохранённых README и метаданных, без API."""
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
        """Топ-n имён по Близости к задаче; перебор по всем векторам.
        ponytail: brute force; sqlite-vec when index >~200k or search >~200 ms (ADR-0001)"""
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

    def seen(self, names: list[str]) -> dict[str, str]:
        """«проект: вердикт (дата)» — последний вердикт по каждому проекту, свежие первыми; ключ — имя в нижнем регистре."""
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
        """Репо удалено на GitHub: убрать из поиска (Вердикты остаются)."""
        with self.db:
            self.db.execute("DELETE FROM repos WHERE name = ?", (name.lower(),))

    def rename(self, old: str, new: str) -> None:
        """Репо переименовано: старая запись уходит, Вердикты переезжают на новое имя."""
        with self.db:
            self.db.execute("DELETE FROM repos WHERE name = ?", (old.lower(),))
            self.db.execute("UPDATE verdicts SET name = ? WHERE name = ?", (new.lower(), old.lower()))

    def verdicts(self, project: str | None = None) -> list[tuple]:
        q = "SELECT project, name, verdict, task, date FROM verdicts"
        args: tuple = ()
        if project:
            q, args = q + " WHERE project = ?", (project,)
        return self.db.execute(q + " ORDER BY project, date, rowid", args).fetchall()
