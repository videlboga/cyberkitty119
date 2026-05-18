from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from core_api.domains.agent.core.agent_runtime import AGENT_MANAGER

router = APIRouter()

class TelegramUserProxy:
    def __init__(self, id: int, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None):
        self.id = id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name

class AgentMessageRequest(BaseModel):
    telegram_id: int
    text: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class ActiveNoteRequest(BaseModel):
    telegram_id: int
    note_id: int
    local_artifact: bool = False

class IngestRequest(BaseModel):
    telegram_id: int
    payload: Dict[str, Any]

class ToolResultResponse(BaseModel):
    tool_name: str
    argument: Optional[str] = None
    result: str
    success: bool
    message: Optional[str] = None

    class Config:
        populate_by_name = True

class AgentMessageResponse(BaseModel):
    text: str
    tool_results: List[ToolResultResponse] = []
    suggestions: List[str] = []

@router.post("/chat", response_model=AgentMessageResponse)
async def chat_with_agent(req: AgentMessageRequest):
    """
    Основной эндпоинт когнитивного агента (ReAct Loop).
    Принимает сообщение от пользователя и возвращает ответ LLM, включая список вызванных тулов.
    """
    # 1. Формируем "прокси" пользователя для легаси-совместимости внутри AgentManager
    tg_user = TelegramUserProxy(
        id=req.telegram_id,
        username=req.username,
        first_name=req.first_name,
        last_name=req.last_name
    )
    
    # 2. Получаем или создаем сессию для пользователя
    try:
        session = AGENT_MANAGER.get_session(tg_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot initialize agent session: {e}")
        
    # 3. Передаем текст в агента
    try:
        response = await session.handle_user_message(text=req.text)
        AGENT_MANAGER.save_session(session)
        
        # 4. Форматируем ответ
        tool_results = []
        for tr in response.tool_results:
            tool_results.append(ToolResultResponse(
                tool_name=getattr(tr, "name", getattr(tr, "tool_name", "tool")),
                argument=str(getattr(tr, "args", getattr(tr, "details", getattr(tr, "arguments", {}))))[:500],
                result=str(getattr(tr, "result", getattr(tr, "message", getattr(tr, "content", ""))))[:500],
                success=(getattr(tr, "status", getattr(tr, "state", "success")) not in ["error", "blocked", "failed"]),
                message=getattr(tr, "message", getattr(tr, "error", None))
            ))
            
        return AgentMessageResponse(
            text=response.text,
            tool_results=tool_results,
            suggestions=response.suggestions
        )
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Agent error details: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/active_note")
async def set_active_note(req: ActiveNoteRequest):
    try:
        tg_user = TelegramUserProxy(id=req.telegram_id)
        session = AGENT_MANAGER.get_session(tg_user)
        # Note proxy for minimal required functionality (id attribute)
        class NoteProxy:
            def __init__(self, id):
                # Minimal proxy implementing attributes expected by AgentSession.set_active_note
                self.id = id
                self.summary = None
                self.type_hint = None
                self.text = None
                self.links = {}
        session.set_active_note(NoteProxy(req.note_id), local_artifact=req.local_artifact)
        session._refresh_active_note()
        AGENT_MANAGER.save_session(session)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingest", response_model=AgentMessageResponse)
async def handle_ingest(req: IngestRequest):
    try:
        tg_user = TelegramUserProxy(id=req.telegram_id)
        session = AGENT_MANAGER.get_session(tg_user)
        response = await session.handle_ingest(req.payload)
        AGENT_MANAGER.save_session(session)
        
        tool_results = []
        for tr in response.tool_results:
            tool_results.append(ToolResultResponse(
                tool_name=getattr(tr, "name", getattr(tr, "tool_name", "tool")),
                argument=str(getattr(tr, "args", getattr(tr, "details", getattr(tr, "arguments", {}))))[:500],
                result=str(getattr(tr, "result", getattr(tr, "message", getattr(tr, "content", ""))))[:500],
                success=(getattr(tr, "status", getattr(tr, "state", "success")) not in ["error", "blocked", "failed"]),
                message=getattr(tr, "message", getattr(tr, "error", None))
            ))
            
        return AgentMessageResponse(
            text=response.text,
            tool_results=tool_results,
            suggestions=response.suggestions
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
