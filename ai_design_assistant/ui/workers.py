"""
ui.workers
~~~~~~~~~~
Фоновые потоки/задачи, чтобы не блокировать UI.
"""

from __future__ import annotations

from typing import Any, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal


class GenerateThread(QThread):
    """
    Выполняет запрос к LLM в отдельном потоке.
    Излучает:
        • finished(str) ― полный ответ модели;
        • error(str)    ― текст исключения.
    """

    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        router: Any,
        messages: List[Any],
        *,
        backend: Optional[str] = None,
        parent: Optional[object] = None,
    ) -> None:
        super().__init__(parent)
        self._router = router
        self._messages = messages
        self._backend = backend

    # ----------------------------------------- #
    def run(self) -> None:  # noqa: D401  (коротко)
        try:
            reply: str = self._router.chat(
                self._messages, backend=self._backend
            )  # sync-вызов модели
            self.finished.emit(reply)
        except Exception as exc:  # pragma: no cover
            self.error.emit(str(exc))
