"""
ui.workers
~~~~~~~~~~
Фоновые потоки/задачи, чтобы не блокировать UI.
"""

from __future__ import annotations

from typing import Any, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal
from pathlib import Path

# ai_design_assistant/ui/workers.py
from PyQt6.QtCore import QThread, pyqtSignal
from ai_design_assistant.core.models import LLMRouter
from ai_design_assistant.core.image_utils import image_to_base64


class GenerateThread(QThread):
    token_received = pyqtSignal(str)  # Сигнал для потоковых токенов
    finished = pyqtSignal(str)        # Сигнал для завершения
    error = pyqtSignal(str)

    def __init__(self, router: LLMRouter, messages: list):
        super().__init__()
        self.router = router
        self.messages = messages

    def run(self):
        try:
            prepared_messages = []
            for msg in self.messages:
                if getattr(msg, "image", None):
                    base64_data = image_to_base64(Path(msg.image))
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

            for token in self.router.stream(prepared_messages):
                self.token_received.emit(token)

            self.finished.emit("ok")

        except Exception as e:
            self.error.emit(str(e))
