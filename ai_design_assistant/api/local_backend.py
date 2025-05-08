"""Local backend wrapping *llama.cpp* / *Ollama* server.

By дефолту пытаемся подключиться к Ollama‑совместимому REST‑серверу
(``http://localhost:11434``). Такой режим умеет *ollama serve* или
*llama.cpp* с web‑socket фронтом.

• Для простоты используем ``requests``. Если сервер не найден – бэкенд
  регистрируется, но каждый вызов бросит ``RuntimeError`` (GUI сможет вывести
  сообщение «Локальная модель недоступна»).

• *stream=True* реализуется через бесконечный чанковый HTTP и Sse‑like формат:
  сервер шлёт строки ``data: {json}\n``
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterable

import requests
from requests import Response, Session

from ai_design_assistant.core import Message, ModelBackend, Settings, get_global_router

_LOGGER = logging.getLogger(__name__)

_DEFAULT_BASE_URL = os.getenv("AI_DA_LOCAL_BASE_URL", "http://localhost:11434")


class LocalBackend(ModelBackend):
    """Backend proxying to a local LLM HTTP server (Ollama style)."""

    name = "local"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._base_url = _DEFAULT_BASE_URL.rstrip("/")
        self._session = requests.Session()
        self._default_model = "llama3"
        # probe server
        try:
            r = self._session.get(f"{self._base_url}/v1/models", timeout=3)
            r.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Local LLM server not reachable at {self._base_url}: {exc}") from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _convert_messages(messages: list[Message]) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------
    def stream(self, messages: list[Message], *, model: str | None = None, temperature: float = 0.7, **kwargs) -> Iterable[str]:
        model = model or self._default_model
        payload = {
            "model": model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "stream": True,
            **kwargs,
        }
        resp = self._session.post(f"{self._base_url}/v1/chat/completions", json=payload, stream=True, timeout=30)
        resp.raise_for_status()
        for line in resp.iter_lines():  # type: ignore[arg-type]
            if not line:
                continue
            if line.startswith(b"data: "):
                data = json.loads(line[6:])
                delta = data["choices"][0]["delta"].get("content", "")
                if delta:
                    yield delta

    def complete(self, messages: list[Message], *, model: str | None = None, temperature: float = 0.7, **kwargs) -> str:
        model = model or self._default_model
        payload = {
            "model": model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "stream": False,
            **kwargs,
        }
        resp: Response = self._session.post(f"{self._base_url}/v1/chat/completions", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def metadata(self) -> dict[str, str]:
        return {"provider": "local", "model": self._default_model}


# ---------------------------------------------------------------------------
# Self‑registration
# ---------------------------------------------------------------------------
try:
    router = get_global_router()
    router.register(LocalBackend(router._settings))  # type: ignore[attr-defined]
except Exception as exc:  # pragma: no cover
    _LOGGER.warning("Local backend not registered: %s", exc)
