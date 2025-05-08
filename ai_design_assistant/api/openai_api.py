import os
import base64
from openai import OpenAI
from dotenv import load_dotenv

from chat_history import load_history

# ────────────────────────────────────────────────────────────
# ENV & CLIENT INITIALISATION
# -----------------------------------------------------------------------------
# • Ключ хранится в .env → OPENAI_API_KEY=<your_key>
# • .env должен находиться в корне проекта (рядом с __main__.py)
# -----------------------------------------------------------------------------

load_dotenv()  # Загружаем переменные окружения из .env
from ai_design_assistant.core.logger import get_logger
log = get_logger("openai_api")

OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError(
        "OPENAI_API_KEY not found. Create a .env file with OPENAI_API_KEY=<your_key> or export the variable in your shell"
    )

client = OpenAI(api_key=OPENAI_API_KEY)

# ────────────────────────────────────────────────────────────
# STREAM CHAT RESPONSE
# -----------------------------------------------------------------------------

def _prepare_messages(history: list[dict]) -> list[dict]:
    """Convert stored history into the format expected by OpenAI chat API."""
    messages: list[dict] = []

    for msg in history:
        # handle multimodal user messages that include an image
        if msg["role"] == "user" and "image" in msg:
            if os.path.exists(msg["image"]):
                with open(msg["image"], "rb") as img:
                    img_b64 = base64.b64encode(img.read()).decode("utf-8")
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": msg["content"]},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                            },
                        ],
                    }
                )
            else:
                print(f"⚠️ Image file not found: {msg['image']}")
        else:
            messages.append({"role": msg["role"], "content": msg["content"]})

    return messages


def stream_chat_response(user_text: str, image_path: str | None = None, *, model: str = "gpt-4o"):
    """Generator that yields tokens in a streaming fashion.

    Args:
        user_text: Text entered by the user.
        image_path: Optional path to an image to send along with the prompt.
        model: OpenAI model name.

    Yields:
        Tuple[str, None]: next token (OpenAI delta.content), second item reserved.
    """

    try:
        history = load_history()
        messages = _prepare_messages(history)

        # Add current user message (optionally with image)
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as img:
                img_b64 = base64.b64encode(img.read()).decode("utf-8")

            if not user_text:
                user_text = "Проанализируй изображение."

            user_input = {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                ],
            }
        else:
            user_input = {"role": "user", "content": user_text}

        messages.append(user_input)

        if not messages:
            yield "[Ошибка: История пуста или изображения недоступны.]", None
            return

        response = client.chat.completions.create(model=model, messages=messages, stream=True)

        full_reply: str = ""
        for chunk in response:
            if chunk.choices[0].delta.content:
                token: str = chunk.choices[0].delta.content
                full_reply += token
                yield token, None

    except Exception as exc:
        log.exception("stream_chat_response failed")
        yield f"\n[Ошибка: {exc}]", None

