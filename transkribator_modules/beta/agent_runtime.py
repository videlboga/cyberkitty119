"""MemGPT-inspired agent runtime for the beta branch."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

import re
from zoneinfo import ZoneInfo

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, UserService, NoteService
from transkribator_modules.db.models import Note, User

from .llm import call_agent_llm_with_retry, AgentLLMError
from .prompts import build_system_prompt, build_event_message
from .tools import (
    AgentTool,
    ToolResult,
    format_note_saved_message,
    get_tool_specs,
    resolve_tool,
    _looks_like_question,
)


@dataclass(slots=True)
class AgentUser:
    telegram_id: int
    db_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]


@dataclass(slots=True)
class AgentResponse:
    text: str
    tool_results: list[ToolResult] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class ProgressReporter(Protocol):
    async def update(self, text: str, *, mark_error: bool = False) -> None:  # pragma: no cover - protocol definition
        ...

    async def finalize(self, text: str) -> None:  # pragma: no cover - protocol definition
        ...


class AgentSession:
    """Stateful conversation session per Telegram user."""

    def __init__(self, user: AgentUser):
        self.user = user
        self.history: list[dict[str, str]] = []
        self.active_note_id: Optional[int] = None
        self.active_note_summary: Optional[str] = None
        self.active_note_type: str = "other"
        self.active_note_text: Optional[str] = None
        self.active_note_links: dict[str, str] = {}
        self.active_note_has_local_artifact: bool = False

    @property
    def user_db_id(self) -> int:
        return self.user.db_id

    def set_active_note(
        self,
        note: Note,
        *,
        links: Optional[dict[str, str]] = None,
        local_artifact: bool = False,
    ) -> None:
        self.active_note_id = note.id
        self.active_note_summary = note.summary or None
        self.active_note_type = note.type_hint or "other"
        self.active_note_text = note.text or None
        self.active_note_links = links if links is not None else _parse_note_links(note.links)
        self.active_note_has_local_artifact = local_artifact

    def update_note_snapshot(
        self,
        *,
        text: Optional[str] = None,
        summary: Optional[str] = None,
        links: Optional[dict[str, str]] = None,
        local_artifact: Optional[bool] = None,
    ) -> None:
        if text is not None:
            self.active_note_text = text
        if summary is not None:
            self.active_note_summary = summary
        if links is not None:
            self.active_note_links = links
        if local_artifact is not None:
            self.active_note_has_local_artifact = local_artifact

    async def handle_ingest(
        self,
        payload: dict,
        *,
        progress: Optional[ProgressReporter] = None,
    ) -> AgentResponse:
        message = build_event_message("ingest", payload)
        fallback_context = {
            "mode": "ingest",
            "note_id": payload.get("note_id") or self.active_note_id,
            "created": bool(payload.get("created")),
            "summary": payload.get("summary") or self.active_note_summary,
            "text": payload.get("text"),
            "links": self.active_note_links,
            "local_artifact": self.active_note_has_local_artifact,
        }
        return await self._call_agent(
            message,
            fallback_context=fallback_context,
            progress=progress,
            original_query=payload.get("text"),
        )

    async def handle_user_message(
        self,
        text: str,
        *,
        progress: Optional[ProgressReporter] = None,
    ) -> AgentResponse:
        payload = {
            "text": text,
            "active_note_id": self.active_note_id,
            "active_note_summary": self.active_note_summary,
            "active_note_type": self.active_note_type,
        }
        message = build_event_message("user", payload)
        fallback_context = {
            "mode": "user",
            "note_id": self.active_note_id,
            "note_type": self.active_note_type,
            "summary": self.active_note_summary,
            "links": self.active_note_links,
            "local_artifact": self.active_note_has_local_artifact,
        }
        return await self._call_agent(
            message,
            fallback_context=fallback_context,
            progress=progress,
            original_query=text,
        )

    async def _call_agent(
        self,
        user_message: str,
        *,
        fallback_context: Optional[dict[str, Any]] = None,
        progress: Optional[ProgressReporter] = None,
        original_query: Optional[str] = None,
    ) -> AgentResponse:
        system_prompt = build_system_prompt(get_tool_specs())
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.history)
        enriched_user_message = self._prepend_time_context(user_message)
        question_like = False
        if original_query:
            question_like = await _looks_like_question(original_query)
        messages.append({"role": "user", "content": enriched_user_message})

        logger.debug(
            "Agent session calling LLM",
            extra={
                "user_id": self.user.telegram_id,
                "history_len": len(self.history),
                "active_note": self.active_note_id,
            },
        )

        await _progress_safe_update(progress, "🤖 Думаю над ответом…")

        try:
            raw_response = await call_agent_llm_with_retry(messages, retries=1)
        except AgentLLMError:
            await _progress_safe_update(progress, "⚠️ LLM сейчас недоступна. Попробуем ещё раз позже.", mark_error=True)
            return AgentResponse(text="LLM сейчас недоступна. Попробуем ещё раз позже.")

        parsed = _parse_agent_json(raw_response)
        response_text = parsed.get("response")
        actions = parsed.get("actions") or []
        suggestions = parsed.get("suggestions") or []

        tool_results: list[ToolResult] = []
        search_executed = False
        if not actions:
            await _progress_safe_update(progress, "ℹ️ Дополнительных действий не требуется.")
        for action in actions:
            tool_name = action.get("tool")
            if not tool_name:
                continue
            args = action.get("args") or {}
            if (
                tool_name == "update_note_text"
                and original_query
                and question_like
            ):
                await _progress_safe_update(progress, "🔍 Вместо правки ищу ответ в заметках…")
                try:
                    k_value = int(args.get("k", 3))
                except (TypeError, ValueError):
                    k_value = 3
                forced_search = await self._invoke_tool(
                    "search_notes",
                    {"query": original_query, "k": max(1, k_value)},
                    None,
                )
                if forced_search:
                    tool_results.append(forced_search)
                    status = (forced_search.status or "").lower()
                    if status in {"error", "blocked"}:
                        await _progress_safe_update(
                            progress,
                            _shorten_progress(forced_search.message or "Поиск не удался"),
                            mark_error=True,
                        )
                    else:
                        await _progress_safe_update(progress, "✅ Нашёл подходящие заметки")
                        search_executed = True
                else:
                    await _progress_safe_update(progress, "⚠️ Поиск временно недоступен.", mark_error=True)
                continue
            comment = (action.get("comment") or "").strip()
            tool_obj = resolve_tool(str(tool_name))
            description = comment or (tool_obj.description if tool_obj else f"Выполняю {tool_name}")
            await _progress_safe_update(progress, f"🔧 {description}")
            result = await self._invoke_tool(tool_name, args, comment if comment else None)
            if not result:
                await _progress_safe_update(progress, f"⚠️ Инструмент {tool_name} недоступен.", mark_error=True)
                continue
            tool_results.append(result)
            status = (result.status or "").lower()
            if status in {"error", "blocked"}:
                message = _shorten_progress(result.message or description)
                await _progress_safe_update(progress, f"⚠️ {message}", mark_error=True)
            else:
                await _progress_safe_update(progress, f"✅ {description}")
            if tool_name == "search_notes" and status not in {"error", "blocked"}:
                search_executed = True

        if tool_results and any(result.status in {"error", "blocked"} for result in tool_results):
            response_text = ""

        if (
            original_query
            and question_like
            and not search_executed
        ):
            await _progress_safe_update(progress, "🔍 Дополнительно ищу в заметках…")
            extra_search = await self._invoke_tool(
                "search_notes",
                {"query": original_query, "k": 3},
                None,
            )
            if extra_search:
                tool_results.append(extra_search)
                status = (extra_search.status or "").lower()
                if status in {"error", "blocked"}:
                    await _progress_safe_update(
                        progress,
                        _shorten_progress(extra_search.message or "Поиск не удался"),
                        mark_error=True,
                    )
                else:
                    await _progress_safe_update(progress, "✅ Нашёл подходящие заметки")
                search_executed = True

        await _progress_safe_update(progress, "🧾 Формирую ответ…")

        # Update conversation history
        self.history.append({"role": "user", "content": enriched_user_message})
        tool_suggestions = [res.suggestion for res in tool_results if res.suggestion]
        merged_suggestions = _merge_suggestions(tool_suggestions, [])
        rendered_response = _render_final_message(
            response_text,
            tool_results,
            merged_suggestions,
            fallback_context=fallback_context,
        )
        self.history.append({"role": "assistant", "content": rendered_response})
        self.active_note_has_local_artifact = False

        # Update cached note text if the last tool modified it
        if tool_results and self.active_note_id:
            self._refresh_active_note()

        return AgentResponse(text=rendered_response, tool_results=tool_results, suggestions=merged_suggestions)

    async def _execute_tool(self, tool: AgentTool, args: dict[str, Any]) -> ToolResult:
        if tool.requires_note and not (args.get("note_id") or self.active_note_id):
            return ToolResult(message=f"Инструмент {tool.name} требует активную заметку, но она не установлена.", status="blocked")

        maybe_coro = tool.func(self, args)
        if asyncio.iscoroutine(maybe_coro):
            return await maybe_coro
        return maybe_coro  # type: ignore[return-value]

    async def _invoke_tool(self, tool_name: str, args: dict[str, Any], comment: Optional[str] = None) -> Optional[ToolResult]:
        tool = resolve_tool(str(tool_name))
        if not tool:
            logger.warning("Agent requested unknown tool", extra={"tool": tool_name})
            return None

        try:
            result = await self._execute_tool(tool, args)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Agent tool failed",
                extra={"tool": tool.name, "error": str(exc)},
            )
            return ToolResult(message=f"Инструмент {tool.name} завершился с ошибкой.", status="error")

        if comment:
            cleaned_comment = comment.strip()
            if cleaned_comment and not (result.message and result.message.strip()):
                return ToolResult(
                    message=cleaned_comment,
                    details=result.details,
                    suggestion=result.suggestion,
                    status=result.status,
                )

        return result

    def _refresh_active_note(self) -> None:
        if not self.active_note_id:
            return
        db = SessionLocal()
        try:
            service = NoteService(db)
            note = service.get_note(self.active_note_id)
            if note and note.user_id == self.user_db_id:
                self.update_note_snapshot(
                    text=note.text,
                    summary=note.summary,
                    links=_parse_note_links(note.links),
                    local_artifact=False,
                )
        finally:
            db.close()

    def _get_user_timezone(self) -> Optional[str]:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == self.user_db_id).one_or_none()
            if not user:
                return None
            tz = getattr(user, "timezone", None)
            if isinstance(tz, str) and tz.strip():
                return tz.strip()
            return None
        finally:
            db.close()

    def _prepend_time_context(self, message: str) -> str:
        header = []
        user_tz = self._get_user_timezone()
        header_label = None
        tzinfo = None
        if user_tz:
            header_label = user_tz
            try:
                tzinfo = ZoneInfo(user_tz)
            except Exception:  # noqa: BLE001
                tzinfo = None
        now_dt = datetime.now(tzinfo) if tzinfo else datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        if header_label:
            header.append(f"Сейчас (таймзона {header_label}): {now_iso}")
        else:
            header.append(f"Сейчас: {now_iso}")
        if header:
            return "\n".join(header + [message])
        return message

class AgentManager:
    """Creates and caches AgentSession instances per Telegram user."""

    def __init__(self):
        self._sessions: dict[int, AgentSession] = {}

    def get_session(self, telegram_user) -> AgentSession:
        telegram_id = telegram_user.id
        session = self._sessions.get(telegram_id)
        if session:
            return session

        user = self._ensure_user(telegram_user)
        session = AgentSession(user)
        self._sessions[telegram_id] = session
        return session

    def _ensure_user(self, telegram_user) -> AgentUser:
        db = SessionLocal()
        try:
            user_service = UserService(db)
            user = user_service.get_or_create_user(
                telegram_id=telegram_user.id,
                username=getattr(telegram_user, "username", None),
                first_name=getattr(telegram_user, "first_name", None),
                last_name=getattr(telegram_user, "last_name", None),
            )
            db_id = int(user.id)
        finally:
            db.close()

        return AgentUser(
            telegram_id=telegram_user.id,
            db_id=db_id,
            username=getattr(telegram_user, "username", None),
            first_name=getattr(telegram_user, "first_name", None),
            last_name=getattr(telegram_user, "last_name", None),
        )


def _merge_suggestions(primary: list[str], extra: list[str]) -> list[str]:
    merged: list[str] = []
    for item in (primary or []) + (extra or []):
        text = (item or "").strip()
        if text and text not in merged:
            merged.append(text)
    return merged

def _parse_agent_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().startswith("json"):
            text = text[text.find("\n") + 1 :]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            snippet = text[start : end + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                preview = (raw or "")[:500]
                logger.warning("Failed to parse agent JSON: %s", preview)
                return {}
        preview = (raw or "")[:500]
        logger.warning("Agent returned non-JSON response: %s", preview)
        return {}


def _render_final_message(
    base: Optional[str],
    tool_results: list[ToolResult],
    suggestions: list[str],
    *,
    fallback_context: Optional[dict[str, Any]] = None,
) -> str:
    parts: list[str] = []
    normalized_base = _normalize_response_text(base)
    if tool_results and normalized_base:
        lower_base = normalized_base.casefold()
        negative_markers = (
            "не нашёл",
            "не нашел",
            "ничего не нашлось",
            "не нашла",
            "не нашёл информации",
            "не нашел информации",
            "no information",
            "no results",
        )
        has_negative = any(marker in lower_base for marker in negative_markers)
        if has_negative:
            has_positive_tool = any(
                _extract_note_ids((result.message or ""))
                or "нашёл заметки" in (result.message or "").casefold()
                or "found notes" in (result.message or "").casefold()
                for result in tool_results
            )
            if has_positive_tool:
                normalized_base = ""
    seen_note_ids = _extract_note_ids(normalized_base)
    if normalized_base:
        parts.append(normalized_base)
    
    # Для режима ingest не показываем результаты search_notes
    is_ingest = fallback_context and fallback_context.get("mode") == "ingest"
    
    for result in tool_results:
        message = (result.message or "").strip()
        if not message:
            continue
        
        # Пропускаем search_notes результаты в режиме ingest
        if is_ingest and result.details and "note_links" in result.details:
            continue
            
        note_ids = _extract_note_ids(message)
        if note_ids and note_ids.issubset(seen_note_ids):
            continue
        if note_ids:
            seen_note_ids.update(note_ids)
        parts.append(message)
    if suggestions:
        inline_suggestions = [item.strip() for item in suggestions if item and item.strip()]
        if inline_suggestions:
            if len(inline_suggestions) == 1:
                parts.append(f"Следом: {inline_suggestions[0]}")
            else:
                parts.append("Предложения:")
                for item in inline_suggestions:
                    parts.append(f"• {item}")
    if not parts:
        fallback = _build_fallback_message(fallback_context)
        if fallback:
            parts.append(fallback)
    return "\n\n".join(parts).strip()





AGENT_MANAGER = AgentManager()


async def _progress_safe_update(
    progress: Optional[ProgressReporter],
    text: str,
    *,
    mark_error: bool = False,
    parse_mode: Optional[str] = None,
    disable_preview: bool = True,
) -> None:
    if not progress or not text:
        return
    try:
        await progress.update(
            text,
            mark_error=mark_error,
            parse_mode=parse_mode,
            disable_preview=disable_preview,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Progress update failed", extra={"error": str(exc)})


def _shorten_progress(text: Optional[str], limit: int = 160) -> str:
    if not text:
        return ""
    compact = " ".join(text.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"



_NOTE_ID_RE = re.compile(r"#(\d+)")

def _extract_note_ids(text: Optional[str]) -> set[int]:
    if not text:
        return set()
    try:
        return {int(match) for match in _NOTE_ID_RE.findall(text)}
    except ValueError:
        return set()


def _normalize_response_text(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if not cleaned:
        return ""
    lowered = cleaned.casefold()
    if lowered in {"готово", "готово.", "ok", "ок", "done", "done."}:
        return ""
    return cleaned


def _build_fallback_message(context: Optional[dict[str, Any]]) -> str:
    if not context:
        return "Агент выполнил действие, но не прислал подробностей."

    mode = context.get("mode")
    if mode == "ingest":
        return _fallback_for_ingest(context)
    if mode == "user":
        return _fallback_for_user(context)
    return "Агент выполнил действие, но не прислал подробностей."


def _fallback_for_ingest(context: dict[str, Any]) -> str:
    note_id = context.get("note_id")
    note: Optional[Note] = None

    if note_id:
        db = SessionLocal()
        try:
            note = NoteService(db).get_note(note_id)
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to fetch note for fallback message",
                exc_info=True,
                extra={"note_id": note_id},
            )
        finally:
            db.close()

    if note:
        return format_note_saved_message(note=note)

    summary = context.get("summary") or _compact_text(context.get("text"))
    fallback_title = summary or (f"Заметка #{note_id}" if note_id else "Заметка сохранена")
    raw_tags = context.get("tags")
    tags = raw_tags if isinstance(raw_tags, list) else None

    return format_note_saved_message(
        note=None,
        note_id=note_id,
        title=fallback_title,
        tags=tags,
    )


def _fallback_for_user(context: dict[str, Any]) -> str:
    note_id = context.get("note_id")
    links = context.get("links") or {}

    lines: list[str] = []
    if note_id:
        lines.append(f"Не уверен, что ответить по заметке #{note_id}. Уточни, пожалуйста, запрос.")
    else:
        lines.append("Я пока не понял, что сделать. Расскажи подробнее, пожалуйста.")

    link_line = _format_links(links)
    if link_line:
        lines.append(link_line)

    if context.get("local_artifact"):
        lines.append("Файл заметки отправил отдельным сообщением.")

    lines.append("Уточни запрос или попроси конкретное действие, чтобы получить результат.")
    return "\n".join(lines)


def _format_links(links: dict[str, Any]) -> str:
    if not isinstance(links, dict):
        return ""
    parts: list[str] = []
    mapping = {
        "drive_url": "Drive",
        "doc_url": "Doc",
        "transcript_doc": "Transcript",
        "calendar_url": "Calendar",
    }
    for key, label in mapping.items():
        url = links.get(key)
        if isinstance(url, str) and url.strip():
            parts.append(f"{label}: {url}")
    return "Ссылки: " + ", ".join(parts) if parts else ""


def _compact_text(text: Optional[str], limit: int = 160) -> str:
    if not text:
        return ""
    snippet = text.strip().splitlines()[0]
    if len(snippet) > limit:
        snippet = snippet[: limit - 1] + "…"
    return snippet


def _parse_note_links(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {k: str(v) for k, v in raw.items() if isinstance(v, str) and v.strip()}
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return {k: str(v) for k, v in data.items() if isinstance(v, str) and v.strip()}
    return {}
