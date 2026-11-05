# Навыки с рынка: что добавить (2026-11-05)

Источник: `~/dev/jobs/data/corpus_roadmap.md` (11.5k вакансий, 2026-11-05) против [system-design](system-design.md) и [logic-map](logic-map.md). Берём только то, что нужно самому проекту; чего проект не требует — в «Отвергнуто». Сводка по всем репо: `~/dev/docs/skills-roadmap-report-2026-11-05.md`.

## Предложения

- [ ] **[mcp, agentic]** MCP-сервер `search`, `verdicts`, `index lookup` поверх CLI/Index: репо — инструмент для агентов, MCP — родной транспорт; JSON-контракт run уже есть. Усилие S/M.
- [ ] **[evals, ci/cd]** Job в GitHub Actions: replay `eval/snapshots` без сети и сравнение с `eval/BASELINE.md`, падение при регрессии ранжирования. Снапшоты и baseline уже есть. Усилие S.

## Отвергнуто

- pgvector: 7273 репо, 11 МБ векторов; `sqlite-vec` — только при ~100k в Index.
- Docker: локальный CLI.
