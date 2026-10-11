"""Близость: эмбеддинги fastembed (BAAI/bge-small-en-v1.5) и очистка README."""
import re

import numpy as np

MODEL = "BAAI/bge-small-en-v1.5"
MIN_CLOSENESS = 0.64  # макс. порог без потери «→ Разбор» (0.66) минус запас 0.02, см. eval/BASELINE.md (Фаза 4)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MAX_CHARS = 2000  # ponytail: ~512 токенов ≈ 2000 знаков, без токенайзера
_model = None


def _get():
    global _model
    if _model is None:
        from fastembed import TextEmbedding  # лениво: импорт и загрузка модели тяжёлые
        _model = TextEmbedding(MODEL)
    return _model


def _norm(vecs) -> np.ndarray:
    a = np.asarray(list(vecs), dtype=np.float32).reshape(-1, 384)
    return a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)


def embed_task(text: str) -> np.ndarray:
    return _norm(_get().query_embed(QUERY_PREFIX + text))[0]


def embed_docs(texts: list[str]) -> np.ndarray:
    return _norm(_get().passage_embed(texts))


def closeness(task_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """Косинус; векторы нормализованы, значит скалярное произведение."""
    return doc_vecs @ task_vec


FENCE = re.compile(r"^\s*(```|~~~)")
BADGE = re.compile(r"^\s*(\[!\[[^\]]{0,300}\]\([^)]{0,500}\)\]\([^)]{0,500}\)\s*)+$")
IMAGE = re.compile(r"!\[[^\]]{0,300}\]\([^)]{0,500}\)")
COMMENT = re.compile(r"<!--.{0,2000}?-->", re.DOTALL)
# ponytail: только известные HTML-теги, чтобы не ломать прозу вроде `<T>`; тег может занимать несколько строк
TAG = re.compile(r"</?(?:h[1-6]|p|div|span|a|strong|em|b|i|u|s|center|sub|sup|small|picture|source|img|br|hr|table"
                 r"|thead|tbody|tr|td|th|ul|ol|li|blockquote|details|summary|kbd|figure|figcaption|font)(?:\s[^>]{0,500})?/?>",
                 re.IGNORECASE)
LINK = re.compile(r"\[([^\]]{0,300})\]\([^)]{0,500}\)")


def _prose(lines: list[str]) -> str:
    text = COMMENT.sub("", "\n".join(line for line in lines if not BADGE.match(line)))
    return TAG.sub("", LINK.sub(r"\1", IMAGE.sub("", text)))


def clean_readme(md: str) -> str:
    """Без бейджей, картинок, HTML-разметки и URL ссылок (текст ссылки остаётся); код в ``` не трогаем."""
    md = md[:MAX_CHARS * 10]  # ponytail: режем вход до чистки, чтобы враждебный README не тормозил
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
