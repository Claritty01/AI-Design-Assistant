"""
DeepSeek backend (пример, можно удалить если не нужен).
"""

from __future__ import annotations

from typing import List

from ai_design_assistant.core.models import ModelBackend  # ← точечный импорт

# здесь могла бы быть import deepseek …

class _DeepSeekBackend(ModelBackend):
    name = "deepseek"

    def generate(self, messages: List[dict[str, str]], **kw) -> str:  # noqa: D401
        raise NotImplementedError("DeepSeek SDK ещё не подключён")

backend = _DeepSeekBackend()

def summarize_chat(prompt: str) -> str:
    """Суммаризация чата через DeepSeek (заглушка)."""
    raise NotImplementedError("DeepSeek пока не поддерживает суммаризацию в нашем приложении.")
