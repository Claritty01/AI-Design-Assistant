from __future__ import annotations

import os
import json
from typing import Iterator, List

import openai
from packaging import version

from ai_design_assistant.core.models import ModelBackend, normalize
from ai_design_assistant.core.plugins import get_function_descriptions, call_function_by_name


_API_KEY = os.getenv("OPENAI_API_KEY")
if not _API_KEY:
    raise ImportError("OPENAI_API_KEY missing – backend disabled")


_VER = version.parse(openai.__version__)
_IS_NEW = _VER.major >= 1  # True для 1.x, 2.x …

# ---------------------------------------------------------------------
class _OpenAIBackend(ModelBackend):
    name = "openai"

    # ── one-shot ──────────────────────────────────────────────────────
    def generate(self, messages: List, **kw) -> str:
        msgs = normalize(messages)

        msgs.insert(0, {
            "role": "system",
            "content": (
                "Ты — ИИ-ассистент по графическому дизайну. "
                "Если получаешь изображение с людьми, игнорируй лица и сосредоточься на UI/UX или на эстетике кадра."
            )
        })

        tools = get_function_descriptions()

        if _IS_NEW:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=msgs,
                tools=tools,
                tool_choice="auto",
                **kw
            )
            msg = response.choices[0].message

            if msg.tool_calls:
                tool_messages = []

                for tool_call in msg.tool_calls:
                    name = getattr(getattr(tool_call, "function", None), "name", None)
                    if not name:
                        continue

                    try:
                        args = json.loads(getattr(tool_call.function, "arguments", "") or "{}")
                        if isinstance(args, str):
                            args = {"image_path": args, "quality": 60}
                        elif not isinstance(args, dict):
                            args = {}
                    except Exception:
                        args = {}

                    args.pop("name", None)

                    # подставим последнее изображение
                    last_image = next(
                        (m.get("image") for m in reversed(msgs) if m.get("role") == "user" and m.get("image")),
                        None
                    )

                    if "image_path" not in args and last_image:
                        args["image_path"] = last_image

                    try:
                        result = call_function_by_name(name, **args)
                    except Exception as e:
                        result = f"❌ Ошибка выполнения функции `{name}`: {e}"

                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })

                msgs.append(msg)
                msgs.extend(tool_messages)

                followup = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=msgs,
                    **kw
                )
                return followup.choices[0].message.content or "✓"

            return msg.content or "✓"

        else:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=msgs,
                tools=tools,
                tool_choice="auto",
                **kw
            )
            return response.choices[0].message.content or "✓"

    # ── streaming (yield tokens) ─────────────────────────────────────
    def stream(self, messages: List, **kw) -> Iterator[str]:
        msgs = normalize(messages)

        msgs.insert(0, {
            "role": "system",
            "content": (
                "Ты — ИИ-ассистент по графическому дизайну. "
                "Если получаешь изображение с людьми, игнорируй лица и сосредоточься на UI/UX или на эстетике кадра."
            )
        })

        tools = get_function_descriptions()
        tool_calls_raw = []
        full_text = ""

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
                delta = chunk.choices[0].delta
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    tool_calls_raw.extend(delta.tool_calls)
                elif hasattr(delta, "content") and delta.content:
                    full_text += delta.content
                    yield delta.content

            if tool_calls_raw:
                yield "\n[⚙️ Выполняю инструмент...]\n"
                valid_tool_calls = [
                    tc for tc in tool_calls_raw
                    if getattr(tc, "id", None) and getattr(getattr(tc, "function", None), "name", None)
                ]

                if not valid_tool_calls:
                    yield "\n❌ Ошибка: не найдено ни одного валидного tool_call\n"
                    return

                msgs.append({
                    "role": "assistant",
                    "tool_calls": valid_tool_calls
                })

                for tool_call in valid_tool_calls:
                    name = getattr(getattr(tool_call, "function", None), "name", None)
                    tool_call_id = getattr(tool_call, "id", None)

                    if not name or not tool_call_id:
                        yield "\n❌ Ошибка: tool_call без имени или без id\n"
                        continue

                    arguments = getattr(tool_call.function, "arguments", None)
                    if not arguments or arguments in ("", "null"):
                        arguments = "{}"

                    try:
                        args = json.loads(arguments)
                        if isinstance(args, str):
                            args = {"image_path": args, "quality": 60}
                        elif not isinstance(args, dict):
                            raise TypeError(f"Неверный тип аргументов: {type(args)} — {args!r}")
                    except Exception as e:
                        error_msg = f"❌ Ошибка разбора аргументов: {e}"
                        yield f"\n{error_msg}\n"
                        msgs.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": error_msg
                        })
                        continue

                    last_image = next(
                        (m.get("image") for m in reversed(msgs) if m.get("role") == "user" and m.get("image")),
                        None
                    )

                    if "image_path" not in args and last_image:
                        args["image_path"] = last_image

                    args.pop("name", None)

                    try:
                        result = call_function_by_name(name, **args)
                    except Exception as e:
                        result = f"❌ Ошибка выполнения функции `{name}`: {e}"

                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result or "Готово"
                    })

                followup = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=msgs,
                    **kw
                )
                final = followup.choices[0].message.content
                if final:
                    yield "\n" + final

        else:
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
                if "content" in delta:
                    yield delta["content"]


backend = _OpenAIBackend()

def summarize_chat(prompt: str) -> str:
    """Суммаризация чата через OpenAI."""
    messages = [{"role": "user", "content": prompt}]
    return backend.generate(messages)