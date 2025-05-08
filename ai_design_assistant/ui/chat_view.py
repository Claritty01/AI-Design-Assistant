"""Reusable chat timeline widget.

Encapsulates a ``QListWidget`` (for simplicity) and offers typed helpers
``add_user(text)``, ``add_assistant(token)``, ``add_system(text)`` so higher
level widgets (``MainWindow``) don’t duplicate logic.

Later we could replace with ``QListView`` + custom delegate for rich markdown
rendering, but for MVP a ``QListWidget`` is enough.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextOption
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QWidget, QVBoxLayout

_USER_PREFIX = "🧑"
_ASSIST_PREFIX = "🤖"
_SYS_PREFIX = "⚙️"


class ChatView(QWidget):
    """Simple widget showing chat messages top-to-bottom."""

    def __init__(self, parent: QWidget | None = None) -> None:  # noqa: D401
        super().__init__(parent)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(False)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.list)

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------


    def add_user(self, text: str) -> None:
        QListWidgetItem(f"{_USER_PREFIX} {text}", self.list)
        self.scroll_to_bottom()

    def add_assistant_token(self, token: str) -> None:
        if self.list.count() and self.list.item(self.list.count() - 1).text().startswith(_ASSIST_PREFIX):
            item = self.list.item(self.list.count() - 1)
            item.setText(item.text() + token)
        else:
            QListWidgetItem(f"{_ASSIST_PREFIX} {token}", self.list)
        self.scroll_to_bottom()

    def finalize_assistant_message(self) -> str:
        if not self.list.count():
            return ""
        item = self.list.item(self.list.count() - 1)
        if item.text().startswith(_ASSIST_PREFIX):
            return item.text()[2:].lstrip()
        return ""

    def add_system(self, text: str) -> None:
        QListWidgetItem(f"{_SYS_PREFIX} {text}", self.list)
        self.scroll_to_bottom()

    # ------------------------------------------------------------------
    def scroll_to_bottom(self) -> None:  # noqa: D401 (imperative)
        self.list.scrollToBottom()

    def clear(self) -> None:
        """
        Удаляет все сообщения из вида.

        Используется при переключении сессии, чтобы показать новый
        список сообщений. Проходим по элементам layout-а сверху вниз
        и корректно удаляем дочерние виджеты (иначе утечка памяти).
        """
        self.list.clear()

    def add_message(self, text: str, is_user: bool) -> None:
        if is_user:
            self.add_user(text)
        else:
            # сразу показываем весь ответ целиком
            QListWidgetItem(f"{_ASSIST_PREFIX} {text}", self.list)
            self.scroll_to_bottom()
