**[English](README.md)** | **Русский**

# Золотые наборы (eval)
Формат `eval/<набор>.toml`: `name`, `source` (откуда Вердикты), `analysis_date`, `task` (Описание задачи, англ.), `queries` (3-6 Запросов), `lang`/`must`/`exclude` (Жёсткие условия), далее `[[expected]]` с `repo`, `verdict`, `note`.
Вердикт: «→ Осмотр», «→ Разбор (цель)», «отсев (причина)», «спорно (что уточнить)». Описание задачи и Запросы восстановлены агентом, это черновик.
| набор | ожидаемых | из них «→ Разбор» | источник | что пользователю проверить |
|---|---|---|---|---|
| linux-coding | 20 | 8 | docs/research/opensource-analogs.md | task; запросы выдуманы (оригинальных нет) |
| buy-smarter | 10 | 9 | PLAN.md «Источники», INIT_DATA.md | task; 5 клонов без разбора; olx-parser как отсев |
| buy-smarter-vision | 11 | 5 | docs/llm-vision/...research.md | отдельный набор (не клоны); «Keep/Core» принят за Разбор, «Future/Optional» за спорно |
| persona-crm | 6 | 6 | INIT_DATA.md, CLAUDE.md | monica/nametag/friends/whatsapp-crm: клоны без разбора |
| tiktok-lazy-follower | 5 | 5 | INIT_DATA.md | все клоны без разбора; итог проекта идёт на yt-dlp |
| get_cool_event | 5 | 3 | CLAUDE.md, docs/PRODJECT.md | gallery-dl и insta-dl: «спорно» по Alternatives |
| finance-insights | 5 | 5 | клоны | все клоны без разбора |
| repo-scout | 6 | 4 | docs/analogs/README.md | task |
Поля `must` заполнены только в buy-smarter и tiktok-lazy-follower (грубое по названию площадки); проверить.
