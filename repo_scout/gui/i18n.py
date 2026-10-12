"""GUI language: English (default) or Russian. `t("English text")` returns the text in the current language.

The language is a setting like the others (`REPO_SCOUT_LANG`: environment, then settings files); the header
switch saves it to the user settings file. Keys are the English strings themselves; a missing key shows English.
Domain values (verdicts, stop reasons, flags), repo names and commands are never translated.
"""
import os

from .. import config, llm
from .kit import texts

LANG_VAR = "REPO_SCOUT_LANG"
LANGS = ("en", "ru")
QUASAR = {"en": "en-US", "ru": "ru"}  # Quasar's own texts (pagination etc.)

RU = {
    # navigation and headings
    "Search": "Поиск",
    "Runs": "Прогоны",
    "Index": "Индекс",
    "Eval": "Eval",
    "Interface language": "Язык интерфейса",
    # search page
    "Fill in the task and queries to see the command": "Заполните задачу и запросы, чтобы увидеть команду",
    "Months since last push (0 = any)": "Месяцев с последнего пуша (0 = любые)",
    "Days a repo counts as new": "Сколько дней репо считается новым",
    "Results per query": "Результатов на запрос",
    "Closeness threshold": "Порог близости",
    "Closest repos from Index": "Ближайших репо из Индекса",
    "Repos for round 2 topics": "Репо для тем второго круга",
    "Repos to check for star bursts": "Репо для проверки всплеска звёзд",
    "Skip round 2": "Без второго круга",
    "Skip star burst check": "Без проверки всплеска звёзд",
    "Could not load the draft: the file is damaged or unreadable":
        "Не удалось загрузить черновик: файл повреждён или не читается",
    "Draft failed: the model did not answer or sent an invalid answer. See the log.":
        "Черновик не получился: модель не ответила или ответила с ошибкой. Подробности в логе.",
    "Describe what to find": "Опишите, что найти",
    "Draft ready. Check it, then launch the search.": "Черновик готов. Проверьте его и запустите поиск.",
    "What to search for (any language)": "Что найти (на любом языке)",
    "In your own words, without tool names": "Своими словами, без названий инструментов",
    "Draft from LLM": "Черновик от LLM",
    "Draft": "Черновик",
    "From a past Run or eval dataset": "Из прошлого прогона или набора eval",
    "Task (English)": "Задача (на английском)",
    "1-3 sentences: what you need": "1-3 предложения: что нужно",
    "Queries": "Запросы",
    "One per line; 3-6 variants": "По одному на строку, 3-6 вариантов",
    "Project": "Проект",
    "Language": "Язык",
    "For example python": "Например, python",
    "Required words": "Обязательные слова",
    "Regexes, one per line": "Регулярные выражения, по одному на строку",
    "Excluded words": "Запрещённые слова",
    "Advanced": "Дополнительно",
    "Paste command": "Вставить команду",
    "Command": "Команда",
    "A repo-scout command": "Команда repo-scout",
    "Cancel": "Отмена",
    "Apply": "Применить",
    "Too many runs at once. Wait for one to finish.": "Слишком много запусков сразу. Дождитесь, пока один закончится.",
    "Search started": "Поиск запущен",
    'Done: {title}. <a href="/runs/{stem}">Open run</a>': 'Готово: {title}. <a href="/runs/{stem}">Открыть прогон</a>',
    "Close": "Закрыть",
    "Launch": "Запустить",
    "Agent prompt": "Промпт для агента",
    "Copy": "Копировать",
    "No runs yet": "Запусков пока нет",
    "Add a task description": "Добавьте описание задачи",
    "Add at least one query": "Добавьте хотя бы один запрос",
    "Run": "Прогон",
    # run view
    "Closeness": "Близость",
    "Fit": "Пригодность",
    "Source": "Источник",
    "Score": "Баллы",
    "Repo": "Репо",
    "Forks": "Форки",
    "Commits": "Коммиты",
    "Pushed, d": "Пуш, дн.",
    "Pushed, days ago": "Пуш, дней назад",
    "Created": "Создан",
    "Flags / drop": "Флаги / отсев",
    "Seen": "Видели",
    "Description": "Описание",
    "project: {name}": "проект: {name}",
    "queries: {n}": "запросов: {n}",
    "Showing {shown} of {total}": "Показано {shown} из {total}",
    "Search by repo and description": "Поиск по репо и описанию",
    "Flag": "Флаг",
    "All sources": "Все источники",
    "All flags": "Все флаги",
    "Show dropped": "Показать отсеянные",
    "Open on GitHub": "Открыть на GitHub",
    "Flags and drop: {flags}": "Флаги и отсев: {flags}",
    "Already seen: {seen}": "Уже видели: {seen}",
    "No README in Index: check on GitHub": "README нет в Индексе. Посмотрите на GitHub",
    "Rerun as draft": "Повторить как черновик",
    "Set verdict": "Поставить вердикт",
    "Round 2:": "Второй круг:",
    "README closeness to the task, 0-1": "Близость README к задаче, 0-1",
    "Score: f = freshness, p = popularity": "Балл: f = свежесть, p = популярность",
    "Days since the last push": "Дней с последнего пуша",
    "No rows match these filters.": "Под эти фильтры ничего не подходит.",
    "Run not found or unreadable": "Прогон не найден или не читается",
    "Back to runs": "К прогонам",
    "dropped: {stop}": "отсеян: {stop}",
    # runs list
    "Date": "Дата",
    "Task": "Задача",
    "Kept / total": "Прошли / всего",
    "Unreadable file: {name}": "Файл не читается: {name}",
    "Delete run?": "Удалить прогон?",
    "{task}: the file will be deleted permanently.": "{task}: файл будет удалён навсегда.",
    "Could not delete: {error}": "Не удалось удалить: {error}",
    "Delete": "Удалить",
    "No runs yet. Start one on the Search page.": "Прогонов пока нет. Запустите поиск на странице Поиск.",
    # verdicts
    "→ Inspect": "→ Посмотреть",
    "→ Study": "→ Изучить",
    "Drop": "Отбросить",
    "Doubt": "Сомнение",
    "Study goal": "Цель изучения",
    "Drop reason": "Причина отказа",
    "What to clarify": "Что уточнить",
    "explanation required": "нужно пояснение",
    "All": "Все",
    "Could not open the Index. See the log.": "Не удалось открыть Индекс. Подробности в логе.",
    "Verdict": "Вердикт",
    "Explanation": "Пояснение",
    "One line": "Одной строкой",
    "Which project task, in a few words": "Какая задача проекта, в двух словах",
    "Save verdict": "Сохранить вердикт",
    "Verdict saved: {repo}": "Вердикт сохранён: {repo}",
    # index page
    "All projects": "Все проекты",
    "Added": "Добавлен",
    "README": "README",
    "Verdicts": "Вердикты",
    "Use the owner/repo format": "Укажите в формате owner/repo",
    "yes": "да",
    "no": "нет",
    "Verdicts: {seen}": "Вердикты: {seen}",
    "No README in Index": "README нет в Индексе",
    "Rename": "Переименовать",
    "Forget": "Забыть",
    "Rename repo": "Переименовать репо",
    "Old record will be removed from Index; verdicts will move to the new name.":
        "Старая запись уйдёт из Индекса, вердикты перейдут на новое имя.",
    "New name": "Новое имя",
    "Renamed: {name}": "Переименовано: {name}",
    "Forget repo?": "Забыть репо?",
    "{name} leaves Index search. Its verdicts stay.": "{name} пропадёт из поиска по Индексу. Вердикты останутся.",
    "No repos in the Index yet. Run a search to add them.": "В Индексе пока нет репо. Запустите поиск, чтобы их добавить.",
    # eval page
    "List repos per set": "Список репо по наборам",
    "Closeness thresholds 0.50-0.90": "Пороги близости 0.50-0.90",
    "API call counts": "Число вызовов API",
    "Index check": "Проверка Индекса",
    "Star burst flag": "Флаг всплеска звёзд",
    "Star burst: full threshold grid": "Всплеск звёзд: полная сетка порогов",
    "Eval started": "Eval запущен",
    "Report": "Отчёт",
    "Eval failed. See the log above.": "Eval не удался. Подробности в логе выше.",
    "Expected: {n} · snapshot: {date}": "Ожидается: {n} · снапшот: {date}",
    "Snapshots (offline)": "Снапшоты (офлайн)",
    "Record snapshots (network)": "Записать снапшоты (сеть)",
    "Top results to show (0 = none)": "Сколько верхних результатов показать (0 = ни одного)",
    "Launch eval": "Запустить eval",
    "Export verdicts": "Выгрузить вердикты",
    "Index verdicts as [[expected]] blocks for datasets.": "Вердикты из Индекса в виде блоков [[expected]] для наборов.",
    "Empty: all projects": "Пусто: все проекты",
    "Export": "Выгрузить",
    "No eval sets found (eval/*.toml)": "Наборы eval не найдены (eval/*.toml)",
    "Select at least one set": "Выберите хотя бы один набор",
}


def current() -> str:
    lang = llm.setting(LANG_VAR, "en").lower()
    return lang if lang in LANGS else "en"


def t(text: str) -> str:
    return RU.get(text, text) if current() == "ru" else text


def sync_kit() -> None:
    """Kit strings (statuses, buttons, pagination) in the current language; call on every page build."""
    texts.TEXTS.update(texts.RU if current() == "ru" else texts.EN)


def set_lang(lang: str) -> None:
    """Switch now (this process) and remember it in the user settings file; English needs no line."""
    lang = lang if lang in LANGS else "en"
    os.environ[LANG_VAR] = lang  # a real environment value would otherwise win over the file
    config.update_env(llm.user_env_path(), {LANG_VAR: "" if lang == "en" else lang})
