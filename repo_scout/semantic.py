"""Closeness: fastembed embeddings (BAAI/bge-small-en-v1.5) and README cleaning."""
import os
import re
from pathlib import Path

import numpy as np

MODEL = "BAAI/bge-small-en-v1.5"
MIN_CLOSENESS = 0.64  # max threshold without losing '→ Study' (0.66) minus 0.02 margin, see eval/BASELINE.md (Phase 4)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MAX_CHARS = 2000  # ~512 tokens ≈ 2000 chars without tokenizer
EMBED_BATCH = 32  # fastembed default 256: same speed, ~1.5x memory and arena growth on long runs
_model = None


def cache_dir() -> str:
    """fastembed defaults to the temp dir, which reboots and cleaners wipe; keep the model next to our data."""
    return os.environ.get("FASTEMBED_CACHE_PATH") or str(Path.home() / ".cache/repo-scout/fastembed")
_doc_cache: dict[str, np.ndarray] = {}  # ponytail: per-process, unbounded; eval variants embed the same READMEs


def _get():
    global _model
    if _model is None:
        from fastembed import TextEmbedding  # lazy import: model loading is heavy
        _model = TextEmbedding(MODEL, cache_dir=cache_dir())
    return _model


def _norm(vecs) -> np.ndarray:
    a = np.asarray(list(vecs), dtype=np.float32).reshape(-1, 384)
    return a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)


def embed_task(text: str) -> np.ndarray:
    return _norm(_get().query_embed(QUERY_PREFIX + text))[0]


def embed_docs(texts: list[str]) -> np.ndarray:
    todo = list(dict.fromkeys(t for t in texts if t not in _doc_cache))
    if todo:
        _doc_cache.update(zip(todo, _norm(_get().passage_embed(todo, batch_size=EMBED_BATCH))))
    return np.stack([_doc_cache[t] for t in texts]) if texts else np.empty((0, 384), dtype=np.float32)


def closeness(task_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """Cosine similarity; vectors are normalized so dot product equals cosine."""
    return doc_vecs @ task_vec


FENCE = re.compile(r"^\s*(```|~~~)")
BADGE = re.compile(r"^\s*(\[!\[[^\]]{0,300}\]\([^)]{0,500}\)\]\([^)]{0,500}\)\s*)+$")
IMAGE = re.compile(r"!\[[^\]]{0,300}\]\([^)]{0,500}\)")
COMMENT = re.compile(r"<!--.{0,2000}?-->", re.DOTALL)
# only known HTML tags to avoid breaking prose like `<T>`; tags can span multiple lines
TAG = re.compile(r"</?(?:h[1-6]|p|div|span|a|strong|em|b|i|u|s|center|sub|sup|small|picture|source|img|br|hr|table"
                 r"|thead|tbody|tr|td|th|ul|ol|li|blockquote|details|summary|kbd|figure|figcaption|font)(?:\s[^>]{0,500})?/?>",
                 re.IGNORECASE)
LINK = re.compile(r"\[([^\]]{0,300})\]\([^)]{0,500}\)")


def _prose(lines: list[str]) -> str:
    text = COMMENT.sub("", "\n".join(line for line in lines if not BADGE.match(line)))
    return TAG.sub("", LINK.sub(r"\1", IMAGE.sub("", text)))


def clean_readme(md: str) -> str:
    """Remove badges, images, HTML markup and link URLs (link text kept); preserve code fences."""
    md = md[:MAX_CHARS * 10]  # truncate input before cleaning so hostile READMEs do not hang
    out, prose, in_fence = [], [], False
    for line in md.replace("\r\n", "\n").split("\n"):
        if FENCE.match(line):
            if not in_fence:
                out.append(_prose(prose))
                prose = []
            in_fence = not in_fence
            out.append(line)
        elif in_fence:
            out.append(line)
        else:
            prose.append(line)
    out.append(_prose(prose))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def candidate_text(row: dict, readme: str | None) -> str:
    head = f"{row['repo'].split('/')[-1]}\n{row['desc']}\n{' '.join(row['topics'])}"
    return f"{head}\n{clean_readme(readme or '')}"[:MAX_CHARS]
