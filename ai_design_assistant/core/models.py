"""Public API of ``ai_design_assistant.core``.

Re‑exports the most commonly used classes/functions so consumer code can simply

>>> from ai_design_assistant.core import Settings, ChatSession, get_global_router
"""

from __future__ import annotations

from .logger import configure_logging
from .settings import Settings
from .chat import ChatSession, Message
from .models import LLMRouter, ModelBackend, get_global_router

__all__ = [
    "Settings",
    "configure_logging",
    "ChatSession",
    "Message",
    "LLMRouter",
    "ModelBackend",
    "get_global_router",
]
