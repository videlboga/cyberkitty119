from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class MaxUser:
    id: Any
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]


@dataclass
class Attachment:
    url: Optional[str]
    token: Optional[str]
    id: Optional[Any]
    filename: Optional[str]
    size: Optional[int]
    mime: Optional[str]
    raw: Dict[str, Any]


@dataclass
class Event:
    raw: Dict[str, Any]
    chat_id: Optional[str]
    user: MaxUser
    text: Optional[str]
    attachments: List[Attachment]
    forwarded: bool = False
    callback_data: Optional[str] = None
