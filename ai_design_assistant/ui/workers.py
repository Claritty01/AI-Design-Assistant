"""
ui.workers
~~~~~~~~~~
Фоновые потоки/задачи, чтобы не блокировать UI.
"""

from __future__ import annotations
from typing import Any, List, Optional
from PyQt6.QtCore import QThread, pyqtSignal
from pathlib import Path

from ai_design_assistant.core.models import LLMRouter
from ai_design_assistant.core.image_utils import image_to_base64
from ai_design_assistant.core.chat import ChatSession, handle_tool_calls


class GenerateThread(QThread):
    token_received = pyqtSignal(str)  # Потоковые токены
    finished = pyqtSignal(str)        # Когда всё завершено
    error = pyqtSignal(str)

    def __init__(self, router: LLMRouter, messages: list, chat_path: Path, chat_json_path: Path):
        super().__init__()
        self.router = router
        self.messages = messages
        self.chat_path = chat_path
        self.chat_path = chat_path  # для изображений
        self.chat_json_path = chat_json_path  # для загрузки чата

    def run(self):
        try:
            # 📨 Подготовка сообщений (включая изображения)
            prepared_messages = []
            for msg in self.messages:
                if getattr(msg, "image", None):
                    image_path = self.chat_path / msg.image
                    base64_data = image_to_base64(image_path)
                    prepared_messages.append({
                        "role": msg.role,
                        "content": [
                            {"type": "text", "text": msg.content},
                            {"type": "image_url", "image_url": {"url": base64_data}},
                        ]
                    })
                else:
                    prepared_messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })

            # 📡 Потоковая генерация с final_message в конце
            full_text = ""
            message = None

            for result in self.router.stream(prepared_messages):
                if isinstance(result, str):
                    self.token_received.emit(result)
                    full_text += result
                elif hasattr(result, "final_message"):
                    message = result.final_message  # ✅ тут tool_calls

            # ✅ Сохраняем сообщение от ассистента
            chat = ChatSession.load(self.chat_json_path)
            msg = chat.add_message("assistant", full_text)

            # 🛠️ Обработка tool_calls (если есть)
            if message and "tool_calls" in message and message["tool_calls"]:
                handle_tool_calls(message.tool_calls, chat)

            if self.chat_path.is_file():
                self.chat_path = self.chat_path.parent

            self.finished.emit("ok")

        except Exception as e:
            self.error.emit(str(e))
