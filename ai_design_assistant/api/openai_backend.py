"""OpenAI backend implementation.

Requires `openai>=1.10` declared in pyproject dependencies.
On import, attempts to register itself with the global router so that the
application does *not* need explicit wiring.
"""
from __future__ import annotations

import logging
from typing import Iterable

import openai
from openai import OpenAI

from ai_design_assistant.core import ModelBackend, Message, Settings, get_global_router

_LOGGER = logging.getLogger(__name__)


class OpenAIBackend(ModelBackend):
    """Backend using the official `openai` Python client."""

    name = "openai"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        api_key = settings.active_api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY missing; set env var or in settings.json")
        # Configure the client – thread‑safe
        self._client = OpenAI(api_key=api_key, timeout=30.0)
        # default model; can be overriden via kwargs
        self._default_model = "gpt-3.5-turbo"

    # ------------------------------------------------------------------
    # Core LLM calls
    # ------------------------------------------------------------------
    def _convert_messages(self, messages: list[Message]) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def stream(self, messages: list[Message], *, model: str | None = None, temperature: float = 0.7, **kwargs) -> Iterable[str]:
        model = model or self._default_model
        _LOGGER.debug("OpenAI stream model=%s temperature=%s", model, temperature)
        response = self._client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            stream=True,
            **kwargs,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content  # type: ignore[attr-defined]
            if delta:
                yield delta

    def complete(self, messages: list[Message], *, model: str | None = None, temperature: float = 0.7, **kwargs) -> str:  # noqa: D401
        model = model or self._default_model
        _LOGGER.debug("OpenAI complete model=%s", model)
        response = self._client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            stream=False,
            **kwargs,
        )
        return response.choices[0].message.content  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Optional metadata (for UI)
    # ------------------------------------------------------------------
    def metadata(self) -> dict[str, str]:
        return {"provider": "openai", "model": self._default_model}


# ---------------------------------------------------------------------------
# Self‑registration on import
# ---------------------------------------------------------------------------
try:
    router = get_global_router()
    router.register(OpenAIBackend(router._settings), override=True)  # type: ignore[attr-defined]
except Exception as exc:  # pragma: no cover
    _LOGGER.warning("OpenAI backend not registered: %s", exc)
