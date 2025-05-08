"""DeepSeek backend (placeholder implementation).

DeepSeek LLM пока не имеет официального Python SDK, поэтому здесь приведён
минимальный REST-обёртка через `requests`. Как только команда DeepSeek
выпустит клиентскую библиотеку, код можно заменить.

* Требует переменной окружения / Settings: ``DEEPSEEK_API_KEY``
* Base‑URL принятое в документации 2025‑04: ``https://api.deepseek.com/v1/``

Оба метода — ``complete`` и ``stream`` — оборачивают эндпоинт
``POST /chat/completions``. Если сервер вернул ``Transfer‑Encoding: chunked``
и поле ``stream: true`` — стримим чанки.

***NB***: Сейчас это каркас: без ключа или при ошибке возвращает
``RuntimeError``. Тем не менее, модуль регистрируется в глобальном роутере,
чтобы UI мог показать провайдера «недоступен».
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterable, Iterator

import requests
from requests import Response, Session

from ai_design_assistant.core import Message, ModelBackend, Settings, get_global_router

_LOGGER = logging.getLogger(__name__)

_BASE_URL = "https://api.deepseek.com/v1"
_HEADERS = {
    "Content-Type": "application/json",
}


class DeepSeekBackend(ModelBackend):
    """Minimal DeepSeek LLM backend via REST."""

    name = "deepseek"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._api_key = settings.active_api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self._api_key:
            raise RuntimeError("DEEPSEEK_API_KEY missing; set env var or in settings.json")
        self._headers = {**_HEADERS, "Authorization": f"Bearer {self._api_key}"}
        self._session: Session | None = None
        self._default_model = "deepseek-chat"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _s(self) -> Session:  # lazily create
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(self._headers)
        return self._session

    @staticmethod
    def _convert_messages(messages: list[Message]) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    # ------------------------------------------------------------------
    # Public API
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
        _LOGGER.debug("DeepSeek stream model=%s", model)
        resp = self._s().post(f"{_BASE_URL}/chat/completions", json=payload, stream=True, timeout=30)
        resp.raise_for_status()
        for line in resp.iter_lines():  # type: ignore[arg-type]
            if not line:
                continue
            if line.startswith(b"data: "):
                chunk_json = json.loads(line[6:])
                delta = chunk_json["choices"][0]["delta"].get("content", "")
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
        _LOGGER.debug("DeepSeek complete model=%s", model)
        resp: Response = self._s().post(f"{_BASE_URL}/chat/completions", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def metadata(self) -> dict[str, str]:
        return {"provider": "deepseek", "model": self._default_model}


# ---------------------------------------------------------------------------
# Self‑registration
# ---------------------------------------------------------------------------
try:
    router = get_global_router()
    router.register(DeepSeekBackend(router._settings))  # type: ignore[attr-defined]
except Exception as exc:  # pragma: no cover
    _LOGGER.warning("DeepSeek backend not registered: %s", exc)
