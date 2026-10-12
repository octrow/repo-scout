[English](search-advices.md) | **Русский**

# Поиск на GitHub

## Источники и ссылки
- https://sourcegraph.com/search
- https://medium.com/@mohamedaziz.mhadhbi/github-search-tips-how-to-search-issues-repos-and-more-effectively-on-github-240ddd896f2e
- https://github.com/github/docs/blob/main/content/search-github/getting-started-with-searching-on-github/about-searching-on-github.md
- https://www.freecodecamp.org/news/how-to-use-github-search-like-a-pro/
- https://docs.github.com/en/get-started/exploring-projects-on-github/discovering-projects-on-github
- https://github.com/search?type=code
- https://docs.github.com/en/search-github/getting-started-with-searching-on-github/about-searching-on-github
- https://github.com/Dimillian/HyperGit
- https://tzx.notion.site/What-I-Learned-Building-a-Free-Semantic-Search-Tool-for-GitHub-and-Why-I-Failed-1a09b742c7918033b318f3a5d7dc9751
- https://github.com/manticoresoftware/manticore-github-issue-search

## Выводы (2026-10-11)

- **SemHub** (статья tzx, https://semhub.dev/) — семантический поиск по **issues**, не по репо. OpenAI embeddings 1536→256 (Matryoshka), pgvector на Supabase ($200/мес), Cloudflare Workers. Провал — спрос и дистрибуция, не технология. Уроки для нас: простой перебор вместо ANN на малом объёме, длинный текст резать до лимита модели, жить внутри уже используемого инструмента (у нас — CLI + скилл).
- **Синтаксис поиска** (docs.github.com): без `in:` README не ищется → `in:name,description,topics,readme`. Лимиты: 1000 результатов на запрос, ~4000 просматриваемых совпадений, 256 символов текста (без квалификаторов), ≤5 AND/OR/NOT, `NOT` только для слов (для квалификаторов `-qualifier:`). `pushed:` — push в любую ветку. Полезное: `mirror:false`, `template:`, `archived:`, `license:`, `topics:>n`, `fork:true|only` (форки по умолчанию исключены!), `sort:stars-desc` внутри строки GraphQL. Search API: 30 запросов/мин.
- **Sourcegraph**: `/.api/search/stream` без токена, `type:repo <слова>` возвращает репо со звёздами и topics; поиск по коду с `select:repo` на sourcegraph.com дал 0 — как канал ненадёжен. Кандидат в бэклог каналов.
- **HyperGit** — поиск по своим репо; **manticore-github-issue-search** — по issues. Каналами для поиска репо не являются.
- **keyhacks / keyhunter / gist win3zz** — проверка утёкших API-ключей, к repo-scout не относятся.
