[English](README.md) | **Русский**

# Аналоги repo-scout — Разбор 2026-10-11

Цель Разбора: какие каналы, сигналы и ранжирование без LLM можно перенести в scout.
Клоны: `external_examples/` (в `.gitignore`). Пути ниже — относительно него.
Ни один аналог не использует эмбеддинги/BM25/векторы — Близость делаем сами.

## Сводка
- repohunt — триаж: → Разбор (ранжирование мульти-запросов) · TS, ~600 строк, без LLM · берём: ранжирование, чистка README, `in:name,description,readme`
- github-hidden-gems — триаж: → Разбор (фильтр шума) · Python, ~12k · берём: двухсигнальный фильтр шума, активность без бот-коммитов, качество по дереву файлов
- github-discovery — триаж: отсев (мёртвый, 107 дн / 59 комм), но константы ценные · Python, ~29k, тяжёлый стек · берём формулы, не модули
- git-crawler — триаж: → Разбор (скоринг) · C#/Angular · берём: rateLimit в том же GraphQL, contributors через Link rel=last, колокол по звёздам
- SimRepo — отсев (нет кода построения similar_repos, GPL-3.0) · брать нечего

## Что брать (по убыванию пользы)
1. Фильтр шума (tutorial/template/demo/spam/awesome): отказ только при ≥2 независимых сигналах — `github-hidden-gems/src/hidden_gems/filtering/rules.py:200-576`. S
2. Ранжирование мульти-запросов: число совпавших Запросов → лучшая позиция best-match → pushed_at; звёзды — тай-брейк — `repohunt/src/rank.ts`. S
3. `in:name,description,readme`, без `sort` (позиция best-match = бесплатный сигнал) — `repohunt/src/github.ts:220-244`. S
4. `rateLimit{cost remaining resetAt}` в том же GraphQL-запросе — `git-crawler/Features/Crawling/DiscoverRepositories/GitHubDiscoveryClient.cs:100-162`. S
5. Чистка README: без бейджей/картинок/layout-HTML, код не трогать, обрезка ~2000 символов по границе абзаца — `repohunt/src/readme.ts:1-83`. S
6. Свежесть без бот/typo/bump-коммитов — `github-hidden-gems/src/hidden_gems/light_analysis/activity.py:26-177`. S–M
7. Качество по дереву файлов (tests, CI, src/, manifest, длина README) — `github-hidden-gems/src/hidden_gems/light_analysis/classification.py:139-204`. M
8. Поддержка: bus factor по авторам последних 30 коммитов, каденс, closed/open issues — `github-discovery/src/github_discovery/screening/maintenance.py:25-190`. M
9. Каналы: `topic:awesome-{word}` + ссылки из README (`github-discovery/.../curated_channel.py:37,408-520`); один шаг по владельцу и ссылкам README (`github-hidden-gems/.../relationships/explorer.py:26-175`). M
10. Rate limit: 403 = лимит только при remaining==0/Retry-After; ограниченная параллельность с частичными результатами — `repohunt/src/github.ts:150-160,273-296`. S

## DeepGit (zamalali/DeepGit) — Разбор 2026-10-11
триаж: шаг 1 · баллы 2 (свеж 1, поп 1) · флаги: — · вердикт: → Разбор (векторный слой) · Python, MIT

Устройство: LLM-1 (интент → запросы/topics/must-have) → GraphQL-поиск → upsert в LanceDB → +15 векторных совпадений из индекса → prescore без LLM → топ-8 → LLM-2 (ранжирование).
- Векторный слой `src/deepgit/retrieval/semantic.py:57-250` (269 строк, почти copy-as-is): fastembed `BAAI/bge-small-en-v1.5` (384, ONNX CPU), текст `name\ndesc\ntopics[:12]\nREADME[:1400]` (без чистки бейджей!), запрос через `query_embed()`. LanceDB `merge_insert` по name_with_owner. Минусы: косинус выбрасывается, порога нет, нет fetched_at/TTL — метрики в индексе стареют навсегда.
- GraphQL-поиск с README (7 алиасов `object(expression:"HEAD:README.md")`) и корневым деревом за один запрос — `src/deepgit/github/graphql.py:20-81,94-155`. Дорого на страницу → first 15–25.
- Retry: 403/429 → min(2^n·5, 60) с; «200 без JSON» = secondary limit — `graphql.py:177-209`. Семафора и проверки remaining нет.
- prescore `signals.py:86-99`: 0.4·relevance(доля терминов интента) + 0.2·maintenance(1−log1p(дни)/log1p(1095)) + 0.1·health(tests .40, .github .25, license .20, manifest .15) + 0.3·popularity(log1p★/log1p 10k). Стоп-правил нет.
- Запросы: `topic:<slug> sort:stars-desc` (`pipeline.py:77-91`), детерминированный fallback из терминов интента и соседних пар + `language:` (`pipeline.py:61-74,234-244`).
- Замена LLM-1 без LLM: агент в скилле (наше решение) + topics второго круга; язык — словарь. LLM-2: Близость как ключ + порог + prescore + правило-«риски».
