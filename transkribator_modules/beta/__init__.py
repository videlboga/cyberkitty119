"""Utilities and entrypoints for beta mode."""

from core_api.domains.agent.core.agent_runtime import AGENT_MANAGER, AgentResponse, AgentSession
from .handlers.entrypoint import handle_callback, handle_update, process_text

__all__ = [
    "AGENT_MANAGER",
    "AgentResponse",
    "AgentSession",
    "process_text",
    "handle_update",
    "handle_callback",
]
