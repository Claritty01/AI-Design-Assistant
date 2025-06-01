# ai_design_assistant/ui/chat_view.py
from PyQt6.QtCore import Qt, QPropertyAnimation, QTimer  # ← главный импорт
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

        # Анимация скроллинга
        self.scroll_anim = QPropertyAnimation()

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
        self.message_layout.addStretch(1)

        self.scroll_area.setWidget(self.message_container)

        # Основной layout
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.scroll_area)
        self.setLayout(main_layout)

        bar = self.scroll_area.verticalScrollBar()
        bar.rangeChanged.connect(lambda *_: self._maybe_auto_scroll())

        # флаг, чтобы не мешать пользователю, когда он листает вверх
        self._auto_scroll = True
        bar.valueChanged.connect(self._detect_user_scroll)

    def _detect_user_scroll(self, val: int) -> None:
        bar = self.scroll_area.verticalScrollBar()
        delta = bar.maximum() - val

        if self._auto_scroll:
            # Если автоскролл был включен, но пользователь ушёл вверх — отключаем
            if delta > 4:
                self._auto_scroll = False
        else:
            # Если автоскролл был выключен, но пользователь вернулся вниз — включаем
            if delta < 4:
                self._auto_scroll = True

    def _maybe_auto_scroll(self):
        if self._auto_scroll:
            self.scroll_to_bottom()

    def _last_bubble(self) -> Optional[MessageBubble]:
        # Идём с конца, пропуская спейсер
        for i in range(self.message_layout.count() - 1, -1, -1):
            w = self.message_layout.itemAt(i).widget()
            if isinstance(w, MessageBubble):
                return w
        return None

    def add_message(self, text: str, is_user: bool, image: Optional[str] = None) -> MessageBubble:
        bubble = MessageBubble(markdown_to_html(text), is_user, image=image,
                               parent=self.message_container)
        self.message_layout.addWidget(bubble)

        if self._auto_scroll:  # ← добавили условие
            QTimer.singleShot(0, self.scroll_to_bottom)

        return bubble

    def add_user(self, text: str):
        self.add_message(text, is_user=True)

    def add_assistant(self, text: str):
        self.add_message(text, is_user=False)

    def add_assistant_token(self, token: str):
        last_bubble = self._last_bubble()

        # Если ещё нет ни одного сообщения ИИ – создаём
        if last_bubble is None or last_bubble.is_user:
            last_bubble = self.add_message(token, is_user=False)
            return

        # Дописываем токен в существующий пузырёк
        last_bubble.label.setText(last_bubble.label.text() + token)

        # СКРОЛЛИТЬ ТОЛЬКО ЕСЛИ ПОЛЬЗОВАТЕЛЬ НЕ УШЕЛ ВВЕРХ
        if self._auto_scroll:
            QTimer.singleShot(0, self.scroll_to_bottom)

    def clear(self):
        while self.message_layout.count():
            item = self.message_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def scroll_to_bottom(self) -> None:
        """Плавно прокручивает чат до самого низа."""
        scroll_bar = self.scroll_area.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def message_count(self) -> int:
        return self.message_layout.count()

    def clear(self):
        while self.message_layout.count():
            item = self.message_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # добавляем спейсер заново
        self.message_layout.addStretch(1)

