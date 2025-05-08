# ai_design_assistant/api/openai_backend.py  ──────────────────────────
from __future__ import annotations

import os
from typing import Iterator, List

import openai                                      # 0.28 или >=1.0
from packaging import version

from ai_design_assistant.core.models import ModelBackend, normalize

_API_KEY = os.getenv("OPENAI_API_KEY")
if not _API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

_VER = version.parse(openai.__version__)
_IS_NEW = _VER.major >= 1                          # True для 1.x, 2.x …

# ---------------------------------------------------------------------
class _OpenAIBackend(ModelBackend):
    name = "openai"

    # ── one-shot ──────────────────────────────────────────────────────
    def generate(self, messages: List, **kw) -> str:  # noqa: D401
        msgs = normalize(messages)
        if _IS_NEW:
            resp = openai.chat.completions.create(    # ≥ 1.0
                model="gpt-4o", messages=msgs, **kw
            )
            return resp.choices[0].message.content.strip()
        else:
            resp = openai.ChatCompletion.create(      # 0.28
                model="gpt-4o", messages=msgs, **kw
            )
            return resp.choices[0].message.content.strip()

    # ── streaming (yield tokens) ─────────────────────────────────────
    def stream(self, messages: List, **kw) -> Iterator[str]:
        msgs = normalize(messages)
        if _IS_NEW:
            resp = openai.chat.completions.create(
                model="gpt-4o", messages=msgs, stream=True, **kw
            )
            for chunk in resp:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        else:
            resp = openai.ChatCompletion.create(
                model="gpt-4o", messages=msgs, stream=True, **kw
            )
            for chunk in resp:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content


backend = _OpenAIBackend()                          # auto-register
