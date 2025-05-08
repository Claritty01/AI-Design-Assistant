"""
Публичный интерфейс слоя core, доступный UI-части.
"""
from __future__ import annotations

from .chat import ChatSession, Message      # noqa: F401
from .settings import Settings              # noqa: F401
from .models import ModelBackend            # ← вернули для бекендов

__all__ = [
    "ChatSession",
    "Message",
    "Settings",
    "get_global_router",
]


# ──────────────────────────────────────────────
#  ЛЕНИВАЯ фабрика глобального роутера LLM
# ──────────────────────────────────────────────
from typing import Optional

_GLOBAL_ROUTER: Optional["LLMRouter"] = None


def get_global_router():              # noqa: D401
    """Singleton-роутер, создаётся при первом обращении."""
    global _GLOBAL_ROUTER
    if _GLOBAL_ROUTER is None:
        from .models import LLMRouter  # импорт здесь ↷ нет циклов
        _GLOBAL_ROUTER = LLMRouter()
    return _GLOBAL_ROUTER
