# RESEARCH.md

## Stack
- **Язык:** Python 3.14 (venv в `/home/cyberkitty/Projects/Cyberkitty119/.venv`). Worktree-local `.venv`/`bin/` НЕ имеют pytest — тесты запускать через `/home/cyberkitty/Projects/Cyberkitty119/.venv/bin/python -m pytest`.
- **Фреймворк тестов:** pytest 9.0.2 + pytest-asyncio (asyncio_mode=auto, pytest.ini: `testpaths = tests`, `python_files = test_*.py`).
- **БД:** SQLAlchemy 2.0.46 (MovedIn20Warning на `declarative_base()` — pre-existing, не блокирует).
- **Агент:** LLM-driven agent runtime. Системный промпт → JSON-ответ `{response, actions, suggestions}` → tool execution loop. Тулы: `save_note`, `update_note_text`, `create_note`, `add_tags`, `remove_tags`, `set_status`, `search_notes`, `answer_question`, `fetch_url`, `open_note`, `create_task`, `suggest_calendar_event`, `create_calendar_event`, `update_calendar_event`, `free_prompt`.
- **Build/test команды:**
  - Полный набор: `cd /home/cyberkitty/.control-room/worktrees/cyberkitty119/run_c27ec17c && /home/cyberkitty/Projects/Cyberkitty119/.venv/bin/python -m pytest tests/ -q --ignore=tests/test_beta_mode.py` (baseline: 39 passed).
  - Одиночный файл: `/home/cyberkitty/Projects/Cyberkitty119/.venv/bin/python -m pytest tests/test_answer_question_tool.py -q`.
  - `make test` → `pytest -q` (Makefile), но использует системный python — НЕ использовать, нужен путь к venv.

## Architecture

### Directory layout (релевантные файлы задачи)
```
core_api/domains/agent/core/
  prompts.py          # 82 строки — build_system_prompt (строка 10-41), build_event_message (44-82). ПРОБЛЕМА: строки 33 и 35.
  agent_runtime.py     # 868 строк — AgentSession._call_agent (189-426). ПРОБЛЕМА: строки 267-318 (update_note_text forced search), 383-405 (runtime fallback).
  tools.py            # 1819 строк — _QUESTION_ANALYZER_SYSTEM_PROMPT (190-194), _LLMQuestionAnalyzer (197-259), _looks_like_question (265-266), _tool_answer_question (957-995), _tool_search_notes, _tool_fetch_url (1043+), TOOL_REGISTRY (1799), get_tool_specs (1802).
tests/
  test_answer_question_tool.py  # 168 строк — СУЩЕСТВУЕТ: 4 теста на сам тул _tool_answer_question (структурированный результат, no-results, empty query, registration). НЕ тестит диалоговый сценарий через handle_user_message.
  test_fetch_url_tool.py        # СУЩЕСТВУЕТ — тесты на fetch_url тул.
  test_beta_mode.py             # 706 строк — collection error: import transkribator_modules.beta.agent_runtime (НЕ существует). PRE-EXISTING, не блокирует.
```

### Key components и flow

**Текущий поток handle_user_message (agent_runtime.py:159-187):**
1. `handle_user_message(text)` → `build_event_message("user", payload)` (с active_note_context) → `_call_agent(message, original_query=text)`.
2. `_call_agent` (строка 189):
   - `question_like = await _looks_like_question(original_query)` (строка 202-203) — LLM-классификатор через `_QUESTION_ANALYZER` singleton (tools.py:262).
   - LLM call → parse JSON `{response, actions, suggestions}`.
   - Tool execution loop (строка 262-378): для каждого action — invoke tool.
     - Особая логика для `update_note_text` + `question_like` без active_note → forced `search_notes` (строка 267-318).
     - `search_executed` ставится в True ТОЛЬКО при `tool_name == "search_notes"` (строка 377-378). ВАЖНО: `answer_question` НЕ устанавливает `search_executed=True` — это баг-усилитель (см. ниже).
   - **Runtime fallback** (строка 383-405): `if original_query and question_like and not search_executed and not self.active_note_id:` → принудительный `search_notes` с k=3. Переопределяет решение LLM: даже если LLM вызвал `answer_question` (и `search_executed` остался False) ИЛИ решил просто ответить (actions=[], response непустой), fallback запускает поиск.
   - `_render_final_message` (строка 617+) — объединяет response + tool_results + suggestions.

**Три источника проблемы:**

1. **Промпт (prompts.py:33, 35):**
   - Строка 33: `"Если пользователь задаёт вопрос по своим заметкам («что я писал про X», «найди и расскажи», «о чём у меня заметки про Y»), предпочитай инструмент answer_question..."` — это правильно (различает).
   - Строка 35: `"Если пользователь задает вопрос о текущей активной заметке... Иначе, если активной заметки нет, выполняй answer_question по общему вопросу."` — ЭТО ПРОБЛЕМА: заставляет LLM вызывать `answer_question` для ЛЮБОГО вопроса без активной заметки. Не различает "привет/как дела" от "что я писал про X".

2. **Runtime fallback (agent_runtime.py:383-405):** блок `if original_query and question_like and not search_executed and not self.active_note_id:` запускает `search_notes` даже когда LLM НЕ вызывал поиск. Два подсценария:
   - LLM дал ответ без тулов (actions=[], response непустой) для "привет" → fallback переопределяет и запускает RAG.
   - LLM вызвал `answer_question` (тул отработал, результат в tool_results) → `search_executed` остаётся False (т.к. строка 377 проверяет только `search_notes`) → fallback запускает `search_notes` НАВЕРХ → двойной RAG.

3. **Анализатор is_question (tools.py:190-193):** `_QUESTION_ANALYZER_SYSTEM_PROMPT` — `"Считай вопросом любые формулировки со словами вроде 'найди', 'покажи', 'скажи', 'дайте', даже если нет вопросительного знака."` — ловит "скажи привет", "покажи что умеешь". `_call_llm` (строка 226-259) шлёт user message: `"Определи, относится ли сообщение к вопросу/поиску заметок."` — но system prompt противоречит (говорит "любые формулировки").

**Дополнительный баг (усилитель):** `search_executed` (agent_runtime.py:257, 377-378) устанавливается только для `tool_name == "search_notes"`. `answer_question` не учитывается. Это значит fallback (383-405) срабатывает даже после успешного `answer_question`. Инженер должен либо учитывать `answer_question` в `search_executed`, либо убрать fallback.

## Acceptance Criteria

### AC1. Промпт различает "вопрос по заметкам" vs "общая реплика"
- **AC1.1:** `build_system_prompt` (prompts.py) должен содержать явное правило: `answer_question`/`search_notes` вызываются ТОЛЬКО когда пользователь явно спрашивает про свои заметки (примеры: "что я писал про X", "найди заметки про Y", "о чём мои заметки", "покажи заметку про Z"). Для общих реплик ("привет", "как дела", "что ты умеешь", "расскажи о себе", "спасибо") — отвечать в поле `response` БЕЗ вызова тулов (actions=[]).
- **AC1.2:** Промпт должен содержать конкретные примеры обоих классов (по заметкам → answer_question/search_notes; общие → response без тулов), чтобы LLM могла различить.
- **AC1.3:** Промпт НЕ должен содержать старое правило "если активной заметки нет, выполняй answer_question по общему вопросу" (строка 35). Заменить на суженное правило: answer_question — только при явном запросе по заметкам.

### AC2. Runtime fallback доверяет решению LLM
- **AC2.1:** Блок `agent_runtime.py:383-405` (forced `search_notes` при `question_like and not search_executed and not active_note_id`) должен быть изменён так, чтобы НЕ запускать поиск, если LLM уже вернул непустой `response` и не вызывал тулов. Fallback допустим ТОЛЬКО при: LLM вернул пустой `response` AND `actions` пуст AND нет `active_note_id` AND сообщение похоже на запрос по заметкам (`question_like` от суженного анализатора).
- **AC2.2:** Условие fallback не должно срабатывать после успешного `answer_question`. Либо: (a) учитывать `answer_question` в `search_executed` (строка 377-378), либо (b) fallback проверяет `not tool_results` (не было вообще тулов), либо (c) fallback убран полностью. Инженер выбирает минимально-инвазивный вариант.
- **AC2.3:** Forced `search_notes` для `update_note_text + question_like + no active_note` (строки 267-318) — оставить, но условие `question_like` должно использовать суженный анализатор (после AC3).

### AC3. Анализатор is_question сужен до "запрос по заметкам"
- **AC3.1:** `_QUESTION_ANALYZER_SYSTEM_PROMPT` (tools.py:190-194) должен определять "относится ли сообщение к запросу/поиску СОБСТВЕННЫХ заметок пользователя", а НЕ "является ли вообще вопросом". Убрать инструкцию "считай вопросом любые формулировки со словами 'найди/покажи/скажи/дайте' даже без знака вопроса".
- **AC3.2:** User-prompt в `_call_llm` (tools.py:231-235) должен соответствовать новой семантике.
- **AC3.3:** Поведение (через LLM-стаб в тестах):
  - "привет" → False
  - "как дела" → False
  - "что ты умеешь" → False
  - "расскажи о себе" → False
  - "спасибо" → False
  - "что я писал про X" → True
  - "найди заметки про Y" → True
  - "о чём мои заметки" → True
  - "покажи заметку про Z" → True
- **AC3.4:** `_looks_like_question` (tools.py:265-266) и `_LLMQuestionAnalyzer` (строка 197-259) — сохранить LRU-кеш и fallback на False при LLM-ошибке (строка 246). Сигнатура НЕ меняется (возвращает bool).

### AC4. Тесты
- **AC4.1:** Добавить тесты в `tests/test_answer_question_tool.py` (файл СУЩЕСТВУЕТ, 168 строк) на диалоговый сценарий через `AgentSession.handle_user_message`:
  - "привет" / "как дела" / "что ты умеешь" — LLM-стаб возвращает `{"response": "...", "actions": []}`. Проверить: `IndexService.search` НЕ вызывается, в `tool_results` нет RAG-результатов, `result.text` непустой (естественный ответ).
  - "что я писал про X" / "найди заметки про Y" — LLM-стаб возвращает `{"response": "...", "actions": [{"tool": "answer_question", ...}]}`. Проверить: `answer_question` вызывается (через мок `IndexService.search`), результат отображается.
  - Runtime fallback НЕ срабатывает для "привет" (LLM дал response без тулов → нет forced search).
- **AC4.2:** Тесты используют `AgentSession` из `core_api.domains.agent.core.agent_runtime` (НЕ `transkribator_modules.beta.agent_runtime` — того не существует). Моки: `call_agent_llm_with_retry` (в `core_api.domains.agent.core.agent_runtime` и `core_api.domains.agent.core.tools`), `IndexService.search`, `_looks_like_question` (через `monkeypatch.setattr("core_api.domains.agent.core.agent_runtime._looks_like_question", ...)` для детерминированности).
- **AC4.3:** Тесты запускаются через `/home/cyberkitty/Projects/Cyberkitty119/.venv/bin/python -m pytest tests/test_answer_question_tool.py -q` и проходят (exit 0).
- **AC4.4:** Существующие 39 тестов (`--ignore=tests/test_beta_mode.py`) остаются passing. Существующие 4 теста в `test_answer_question_tool.py` (tool-level) НЕ ломаются. НЕ чинить `test_beta_mode.py` (pre-existing import error, вне scope).

### AC5. Регресс
- **AC5.1:** При active_note_id + вопрос по активной заметке — ответ без `search_notes`/`answer_question` (промпт строка 35 первая часть, сохранить).
- **AC5.2:** Запрос по заметкам без active_note → `answer_question` вызывается (LLM решает), результат отображается. Fallback НЕ дублирует `search_notes` поверх `answer_question`.

## Engineering Notes

### Constraints для инженера

1. **`answer_question` и `fetch_url` — РЕАЛЬНЫЕ тулы** (tools.py:1786, 1792). В отличие от предыдущей итерации кода, они существуют. Промпт (строка 33) уже упоминает `answer_question` правильно. Проблема — строка 35 ("Иначе, если активной заметки нет, выполняй answer_question по общему вопросу").

2. **test_beta_mode.py — НЕ чинить.** `transkribator_modules.beta.agent_runtime` не существует (pre-existing). Для запуска всего набора: `--ignore=tests/test_beta_mode.py`.

3. **Тесты через venv основного проекта:** `/home/cyberkitty/Projects/Cyberkitty119/.venv/bin/python -m pytest`. Worktree-local `.venv`/`bin/` НЕ имеют pytest.

4. **Минимальные изменения, 3 файла + 1 существующий тест-файл:**
   - `core_api/domains/agent/core/prompts.py` — переписать строку 35 (правило "Иначе... answer_question по общему вопросу"). Добавить примеры классов. ~5-10 строк.
   - `core_api/domains/agent/core/agent_runtime.py` — изменить условие блока 383-405 (fallback) + учесть `answer_question` в `search_executed` (строка 377-378). ~5-10 строк.
   - `core_api/domains/agent/core/tools.py` — переписать `_QUESTION_ANALYZER_SYSTEM_PROMPT` (строка 190-194) и user-prompt в `_call_llm` (строка 231-235). ~4-6 строк.
   - `tests/test_answer_question_tool.py` — ДОБАВИТЬ тесты на диалоговый сценарий (привет/как дела не триггерят RAG). Существующие 4 теста сохранить.

5. **`_LLMQuestionAnalyzer` — async LLM-классификатор с LRU-кешем.** Менять только промпты, НЕ логику кеширования/fallback. При LLM-ошибке возвращает False (строка 246) — сохранить (безопасный default: не считать чат-реплику запросом по заметкам).

6. **`search_executed` баг (строка 377-378):** сейчас `if tool_name == "search_notes" and status not in {"error", "blocked"}: search_executed = True`. `answer_question` не учитывается. Рекомендация: расширить условие до `tool_name in {"search_notes", "answer_question"}` ИЛИ добавить отдельный флаг `answer_executed`. Минимально: `if tool_name in ("search_notes", "answer_question") and status not in {"error", "blocked"}: search_executed = True`.

7. **`_call_agent` вызывает `_looks_like_question` ДО LLM-вызова** (строка 202-203). Это дополнительный LLM-запрос (latency). Анализатор используется в двух местах: fallback (383-405) и update_note_text forced search (267-318). После сужения оба блока станут консервативнее.

8. **`_render_final_message` (строка 617+)** — не трогать. Рендерит response + tool_results. Если search не запущен — в tool_results нет RAG-результата, response идёт как есть.

9. **Структура ответа LLM:** `{response: str, actions: [{tool, args, comment}], suggestions: [str]}`. При `actions=[]` и непустом `response` — валидный "просто ответить" сценарий. Runtime НЕ должен переопределять forced search.

10. **`original_query` передаётся в `_call_agent`** из `handle_user_message` (строка 186) и `handle_ingest` (строка 156). Для ingest-событий forced search по question_like — сомнителен (это не пользовательский вопрос, а новая заметка). Рекомендация: fallback (383-405) не должен срабатывать для ingest. Проверить: `fallback_context.get("mode") == "user"` или аналогично.

11. **Тесты с моками:** `monkeypatch.setattr` для `call_agent_llm_with_retry` в `core_api.domains.agent.core.agent_runtime` и `core_api.domains.agent.core.tools`. Для `_looks_like_question` — `monkeypatch.setattr("core_api.domains.agent.core.agent_runtime._looks_like_question", async_mock)` для детерминированности. Для `IndexService.search` — `monkeypatch.setattr(tools.IndexService, "search", _fake_search)`.

12. **Импорты в тестах:** `from core_api.domains.agent.core import tools`, `from core_api.domains.agent.core.agent_runtime import AgentSession, AgentUser`. `os.environ.setdefault("DATABASE_URL", "sqlite://")` + in-memory engine через `monkeypatch.setattr` на `SessionLocal` (как в существующем `_inmemory_db` fixture, строки 32-50). Использовать существующий fixture — он уже корректен.

13. **Базовый commit:** `a2f56201a24f526b1ca1f67f8236454ff6e785f1`. Git worktree: `/home/cyberkitty/.control-room/worktrees/cyberkitty119/run_c27ec17c`.

### Что НЕ делать
- НЕ чинить `test_beta_mode.py` (pre-existing import error, вне scope).
- НЕ менять сигнатуру `_looks_like_question` / `_LLMQuestionAnalyzer.is_question` (возвращает bool).
- НЕ убирать LRU-кеш анализатора.
- НЕ вводить синхронные хардкод-списки ключевых слов вместо LLM-классификатора (задача требует сузить промпт, не заменить механизм).
- НЕ удалять тулы `answer_question` или `fetch_url` — они валидны и используются.
- НЕ ломать существующие 4 теста в `test_answer_question_tool.py` (tool-level тесты на `_tool_answer_question`).