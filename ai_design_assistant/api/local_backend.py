"""
Пример локального LLM-бекенда.
"""

from __future__ import annotations

from typing import List

from ai_design_assistant.core.models import ModelBackend

class _LocalBackend(ModelBackend):
    name = "local"

    def generate(self, messages: List[dict[str, str]], **kw) -> str:  # noqa: D401
        return "Локальная модель пока не реализована."

backend = _LocalBackend()
