"""MemGPT-inspired agent runtime for the beta branch."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, UserService, NoteService
from transkribator_modules.db.models import Note

from .llm import call_agent_llm_with_retry, AgentLLMError
from .prompts import build_system_prompt, build_event_message
from .tools import AgentTool, ToolResult, get_tool_specs, resolve_tool


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

    async def handle_ingest(self, payload: dict) -> AgentResponse:
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
        return await self._call_agent(message, fallback_context=fallback_context)

    async def handle_user_message(self, text: str) -> AgentResponse:
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
        return await self._call_agent(message, fallback_context=fallback_context)

    async def _call_agent(self, user_message: str, *, fallback_context: Optional[dict[str, Any]] = None) -> AgentResponse:
        system_prompt = build_system_prompt(get_tool_specs())
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_message})

        logger.debug(
            "Agent session calling LLM",
            extra={
                "user_id": self.user.telegram_id,
                "history_len": len(self.history),
                "active_note": self.active_note_id,
            },
        )

        try:
            raw_response = await call_agent_llm_with_retry(messages, retries=1)
        except AgentLLMError:
            return AgentResponse(text="LLM сейчас недоступна. Попробуем ещё раз позже.")

        parsed = _parse_agent_json(raw_response)
        response_text = parsed.get("response")
        actions = parsed.get("actions") or []
        suggestions = parsed.get("suggestions") or []

        tool_results: list[ToolResult] = []
        for action in actions:
            tool_name = action.get("tool")
            if not tool_name:
                continue
            tool = resolve_tool(str(tool_name))
            if not tool:
                logger.warning("Agent requested unknown tool", extra={"tool": tool_name})
                continue
            args = action.get("args") or {}
            try:
                result = await self._execute_tool(tool, args)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Agent tool failed",
                    extra={"tool": tool.name, "error": str(exc)},
                )
                tool_results.append(ToolResult(message=f"Инструмент {tool.name} завершился с ошибкой."))
                continue
            if comment := action.get("comment"):
                message = f"{comment}\n{result.message}" if result.message else comment
                tool_results.append(ToolResult(message=message, details=result.details, suggestion=result.suggestion))
            else:
                tool_results.append(result)

        # Update conversation history
        self.history.append({"role": "user", "content": user_message})
        rendered_response = _render_final_message(
            response_text,
            tool_results,
            suggestions,
            fallback_context=fallback_context,
        )
        self.history.append({"role": "assistant", "content": rendered_response})
        self.active_note_has_local_artifact = False

        # Update cached note text if the last tool modified it
        if tool_results and self.active_note_id:
            self._refresh_active_note()

        return AgentResponse(text=rendered_response, tool_results=tool_results, suggestions=suggestions)

    async def _execute_tool(self, tool: AgentTool, args: dict[str, Any]) -> ToolResult:
        if tool.requires_note and not (args.get("note_id") or self.active_note_id):
            return ToolResult(message=f"Инструмент {tool.name} требует активную заметку, но она не установлена.")

        maybe_coro = tool.func(self, args)
        if asyncio.iscoroutine(maybe_coro):
            return await maybe_coro
        return maybe_coro  # type: ignore[return-value]

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
    if normalized_base:
        parts.append(normalized_base)
    for result in tool_results:
        if result.message:
            parts.append(result.message.strip())
    if suggestions:
        parts.append("Предложения:")
        for item in suggestions:
            parts.append(f"• {item}")
    if not parts:
        fallback = _build_fallback_message(fallback_context)
        if fallback:
            parts.append(fallback)
    return "\n\n".join(parts).strip()


AGENT_MANAGER = AgentManager()


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
    summary = context.get("summary") or _compact_text(context.get("text"))
    created = context.get("created", False)
    links = context.get("links") or {}

    lines: list[str] = []
    if note_id:
        prefix = "Создана новая заметка" if created else "Заметка обновлена"
        lines.append(f"{prefix} #{note_id}.")
    else:
        lines.append("Текст сохранён, но идентификатор заметки неизвестен.")

    if summary:
        lines.append(f"Кратко: {summary}")

    link_line = _format_links(links)
    if link_line:
        lines.append(link_line)

    if context.get("local_artifact"):
        lines.append("Файл заметки отправил отдельным сообщением.")

    if not note_id and not summary and not link_line:
        lines.append("Модель не прислала ответ — запроси действие ещё раз, если нужно.")

    return "\n".join(lines)


def _fallback_for_user(context: dict[str, Any]) -> str:
    note_id = context.get("note_id")
    links = context.get("links") or {}
    summary = context.get("summary")

    lines: list[str] = []
    if note_id:
        lines.append(f"Команда выполнена для заметки #{note_id}, но агент не прислал подробностей.")
    else:
        lines.append("Агент не смог сформировать ответ на сообщение.")

    if summary:
        lines.append(f"Текущий контекст: {summary}")

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
