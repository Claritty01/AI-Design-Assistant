"""Background thread helpers for the Qt UI layer.

All tasks that might block the GUI belong here (network calls, heavy image
processing, etc.). Currently provides **StreamWorker** which streams tokens
from the active LLM backend via the core router.
"""
from __future__ import annotations

import logging
from typing import Iterable, List

from PyQt6.QtCore import QThread, pyqtSignal

from ai_design_assistant.core import Message, get_global_router

_LOGGER = logging.getLogger(__name__)


class StreamWorker(QThread):
    """Runs :pycode:`router.stream()` in a separate thread and emits tokens."""

    token_received = pyqtSignal(str)
    error = pyqtSignal(str)
    finished_success = pyqtSignal()

    def __init__(self, messages: List[Message]):  # noqa: D401 (imperative)
        super().__init__()
        self._messages = messages
        self._router = get_global_router()

    # ------------------------------------------------------------------
    # QThread implementation
    # ------------------------------------------------------------------
    def run(self) -> None:  # noqa: D401 (imperative)
        try:
            for token in self._router.stream(self._messages):
                self.token_received.emit(token)
            self.finished_success.emit()
        except Exception as exc:  # pragma: no cover
            _LOGGER.exception("Stream worker failed")
            self.error.emit(str(exc))
