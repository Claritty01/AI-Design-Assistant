# ai_design_assistant/ui/widgets.py
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QGraphicsDropShadowEffect

class MessageBubble(QWidget):
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.setObjectName("bubble")
        self.init_ui(text)

    def init_ui(self, text: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(text)
        self.effect = QGraphicsDropShadowEffect()
        self.effect.setBlurRadius(10)
        self.effect.setColor(Qt.GlobalColor.gray)
        self.effect.setOffset(3, 3)
        self.setGraphicsEffect(self.effect)

        if self.is_user:
            self.setStyleSheet("""
                QWidget#bubble {
                    background: #DCF8C6;
                    color: #333;
                    border-radius: 15px;
                    padding: 10px;
                    margin: 5px;
                    border: 1px solid #ccc;
                }
            """)
            self.label.setAlignment(Qt.AlignmentFlag.AlignRight)  # ← исправлено
        else:
            self.setStyleSheet("""
                QWidget#bubble {
                    background: #F0F0F0;
                    color: #000;
                    border-radius: 15px;
                    padding: 10px;
                    margin: 5px;
                    border: 1px solid #ccc;
                }
            """)
            self.label.setAlignment(Qt.AlignmentFlag.AlignLeft)   # ← исправлено

        layout.addWidget(self.label)
        self.setLayout(layout)