# ai_design_assistant/ui/chat_view.py
from PyQt6.QtCore import Qt  # ← главный импорт
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QHBoxLayout, QLabel
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from typing import Optional

from ai_design_assistant.ui.widgets import MessageBubble

import re

def markdown_to_html(text: str) -> str:
    # Экранируем HTML
    text = (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )

    # Базовое форматирование
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'__(.+?)__', r'<u>\1</u>', text)
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    # Списки (начинающиеся с - или * в начале строки)
    text = re.sub(r'(^|\n)[\-\*]\s+(.*)', r'\1• \2', text)

    # Переносы строк
    text = text.replace("\n", "<br>")

    return text



class ChatView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        # Контейнер для сообщений
        self.message_container = QWidget()
        self.message_layout = QVBoxLayout(self.message_container)
        self.message_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # ← исправлено
        self.message_layout.setSpacing(10)
        self.message_layout.setContentsMargins(20, 20, 20, 20)

        self.scroll_area.setWidget(self.message_container)

        # Основной layout
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.scroll_area)
        self.setLayout(main_layout)

    def add_message(self, text: str, is_user: bool, image: Optional[str] = None) -> MessageBubble:
        bubble = MessageBubble(markdown_to_html(text), is_user, image=image, parent=self.message_container)

        self.message_layout.addWidget(bubble)

        self.scroll_to_bottom()
        return bubble

    def add_user(self, text: str):
        self.add_message(text, is_user=True)

    def add_assistant(self, text: str):
        self.add_message(text, is_user=False)

    def add_assistant_token(self, token: str):
        if not self.message_layout.count():
            self.add_assistant(token)
            return

        last_item = self.message_layout.itemAt(self.message_layout.count() - 1)
        if last_item and isinstance(last_item.widget(), MessageBubble):
            last_bubble = last_item.widget()
            if not last_bubble.is_user:
                last_bubble.label.setText(last_bubble.label.text() + token)
                self.scroll_area.ensureWidgetVisible(last_bubble)

    def clear(self):
        while self.message_layout.count():
            item = self.message_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def scroll_to_bottom(self) -> None:
        """Прокручивает чат до последнего сообщения."""
        self.scroll_area.ensureWidgetVisible(self.message_container)
