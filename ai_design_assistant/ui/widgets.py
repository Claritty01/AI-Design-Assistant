# ai_design_assistant/ui/widgets.py
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QGraphicsDropShadowEffect

from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtGui import QFont, QPixmap, QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QSizePolicy, QApplication
import os

class MessageBubble(QWidget):
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.role = "user" if is_user else "assistant"
        self._init_ui(text)


    def _init_ui(self, text: str, avatar_path: str | None = None):
        # Основной вертикальный лэйаут
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # Текст сообщения
        self.text_label = QLabel(text)
        self.text_label.setWordWrap(True)
        self.text_label.setProperty("bubbleRole", self.role)
        self.text_label.setStyleSheet(self._get_bubble_style())

        # Аватарка
        self.avatar_label = QLabel()
        if avatar_path and os.path.exists(avatar_path):
            pixmap = QPixmap(avatar_path).scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.avatar_label.setPixmap(pixmap)

        # Горизонтальный лэйаут для аватарки и текста
        top_layout = QHBoxLayout()
        top_layout.setSpacing(6)

        if self.role == "user":
            # Пользователь: [спейсер][текст][аватар]
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            top_layout.addWidget(spacer)
            top_layout.addWidget(self.text_label)
            if self.avatar_label.pixmap():
                top_layout.addWidget(self.avatar_label)
        else:
            # Ассистент: [аватар][текст][спейсер]
            if self.avatar_label.pixmap():
                top_layout.addWidget(self.avatar_label)
            top_layout.addWidget(self.text_label)
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            top_layout.addWidget(spacer)

        main_layout.addLayout(top_layout)

        # Копировать текст (опционально)
        self.copy_bar = QWidget()
        copy_layout = QHBoxLayout(self.copy_bar)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_btn = QToolButton()
        copy_btn.setText("📋")
        copy_btn.clicked.connect(self.copy_text)
        copy_layout.addWidget(copy_btn)
        self.copy_bar.hide()
        main_layout.addWidget(self.copy_bar)

        # Тень (вместо box-shadow)
        self._add_shadow()

    def _add_shadow(self):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setColor(Qt.GlobalColor.gray)
        shadow.setOffset(3, 3)
        self.setGraphicsEffect(shadow)

    def _get_bubble_style(self):
        if self.role == "user":
            return """
                QLabel {
                    background: #DCF8C6;
                    color: #333;
                    border-radius: 15px;
                    padding: 10px;
                    margin: 5px;
                    border: 1px solid #ccc;
                }
            """
        else:
            return """
                QLabel {
                    background: #F0F0F0;
                    color: #000;
                    border-radius: 15px;
                    padding: 10px;
                    margin: 5px;
                    border: 1px solid #ccc;
                }
            """

    # В widgets.py
    def copy_text(self):
        QApplication.clipboard().setText(self.text_label.text())

    def set_text(self, text: str):
        self.text_label.setText(text)
        self.adjustSize()