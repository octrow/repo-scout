**English** | **[Русский](0001-index-sqlite-blob-numpy.ru.md)**

# 0001. Index: stdlib sqlite3 + BLOB vectors + numpy scan

Date: 2026-10-11 · Status: accepted

## Context
The index is populated only with candidates that we downloaded anyway (passed stop rules, have a README). Expected scale — thousands, at most tens of thousands of repositories. Embeddings — fastembed (`bge-small`, 384 float32), numpy is pulled in alongside it.

## Decision
A single table in standard library `sqlite3`: metadata, `fetched_at`, vector as BLOB. Search is an exact numpy cosine scan over all entries. 20,000 × 384 × 4 B ≈ 30 MB; scanning takes milliseconds.

## Rejected Alternatives (for future reference)
- **fastembed + LanceDB** (as in DeepGit, `external_examples/DeepGit/src/deepgit/retrieval/semantic.py`). Out-of-the-box `merge_insert`, scales up to millions. Drawback: pyarrow (~100+ MB), columnar DB for a few thousand rows.
- **fastembed + sqlite-vec.** True ANN search, same single sqlite file, lightweight extension. Drawback: redundant native dependency while linear numpy scan suffices.

## When to Revisit
- Index > ~200k repositories or search latency > ~200 ms → sqlite-vec (only the search function needs to change).
- If a full-blown bulk-crawled index is introduced (GH Archive / cron job) → LanceDB or sqlite-vec.
