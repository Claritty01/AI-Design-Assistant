# ai_design_assistant/api/openai_backend.py  ──────────────────────────
from __future__ import annotations

import os
from typing import Iterator, List

import openai                                      # 0.28 или >=1.0
from packaging import version

from ai_design_assistant.core.models import ModelBackend, normalize
from ai_design_assistant.core.plugins import get_function_descriptions


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

        # ⬇️ system message
        msgs.insert(0, {
            "role": "system",
            "content": (
                "Ты — ИИ-ассистент по графическому дизайну. "
                "Если получаешь изображение с людьми, игнорируй лица и сосредоточься на UI/UX или на эстетике кадра: "
                "композиция, кнопки, цвета, читаемость, оформление, экспозиция и так далее. Не обсуждай внешность, даже если она есть."
            )
        })

        tools = get_function_descriptions()

        if _IS_NEW:
            resp = openai.chat.completions.create(
                model="gpt-4o",
                messages=msgs,
                tools=tools,
                tool_choice="auto",
                **kw
            )
            return resp.choices[0].message.content or ""
        else:
            resp = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=msgs,
                tools=tools,
                tool_choice="auto",
                **kw
            )
            return resp.choices[0].message.content or ""

    # ── streaming (yield tokens) ─────────────────────────────────────
    def stream(self, messages: List, **kw) -> Iterator[str]:
        from types import SimpleNamespace
        msgs = normalize(messages)

        msgs.insert(0, {
            "role": "system",
            "content": (
                "Ты — ИИ-ассистент по графическому дизайну. "
                "Если получаешь изображение с людьми, игнорируй лица и сосредоточься на UI/UX или на эстетике кадра: "
                "композиция, кнопки, цвета, читаемость, оформление, экспозиция и так далее. Не обсуждай внешность, даже если она есть."
            )
        })

        tools = get_function_descriptions()
        full_text = ""
        last_tool_calls = None

        if _IS_NEW:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=msgs,
                tools=tools,
                tool_choice="auto",
                stream=True,
                **kw
            )
            for chunk in response:
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    full_text += delta.content
                    yield delta.content

                # Сохраняем tool_calls, если они есть
                if hasattr(delta, "tool_calls"):
                    last_tool_calls = delta.tool_calls

            # ⏎ В самом конце — возвращаем собранное сообщение
            yield SimpleNamespace(final_message={"content": full_text, "tool_calls": last_tool_calls})

        else:
            # старый режим
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=msgs,
                tools=tools,
                tool_choice="auto",
                stream=True,
                **kw
            )
            for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_text += delta.content
                    yield delta.content

            yield SimpleNamespace(final_message={"content": full_text, "tool_calls": []})


backend = _OpenAIBackend()                          # auto-register
