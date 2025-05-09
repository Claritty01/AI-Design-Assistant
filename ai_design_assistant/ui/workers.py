"""
ui.workers
~~~~~~~~~~
Фоновые потоки/задачи, чтобы не блокировать UI.
"""

from __future__ import annotations

from typing import Any, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal


# ai_design_assistant/ui/workers.py
from PyQt6.QtCore import QThread, pyqtSignal
from ai_design_assistant.core.models import LLMRouter


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
            # Используем метод stream() из backend'а
            for token in self.router.stream(self.messages):
                self.token_received.emit(token)  # Отправляем каждый токен
        except Exception as e:
            self.error.emit(str(e))