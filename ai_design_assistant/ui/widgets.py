"""Reusable Qt widgets for AI Design Assistant UI."""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QSizePolicy,
)

ICONS_DIR = Path(__file__).with_suffix("").parent.parent / "resources" / "icons"


class MessageBubble(QWidget):
    """Single chat message bubble.

    Parameters
    ----------
    text
        Message text.
    is_user
        ``True`` – message was sent by user, ``False`` – by assistant.
    parent
        Optional Qt parent.
    """

    def __init__(self, text: str, is_user: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.role = "user" if is_user else "assistant"
        self._init_ui(text)

    # ---------------------------------------------------------------------#
    #                               UI                                     #
    # ---------------------------------------------------------------------#
    def _init_ui(self, text: str, avatar_path: str | os.PathLike | None = None) -> None:
        # Fallback avatar
        if avatar_path is None:
            default_icon = "user.png" if self.role == "user" else "ai.png"
            avatar_path = ICONS_DIR / default_icon

        # ----- Layouts ---------------------------------------------------#
        root = QVBoxLayout(self)
        root.setSpacing(4)
        root.setContentsMargins(6, 6, 6, 6)

        #  Avatar + text in a single row
        row = QHBoxLayout()
        row.setSpacing(6)

        # Avatar label
        avatar_lbl = QLabel()
        if avatar_path and Path(avatar_path).exists():
            pixmap = QPixmap(str(avatar_path)).scaled(
                36,
                36,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            avatar_lbl.setPixmap(pixmap)

        # Text bubble label
        text_lbl = QLabel(text)
        text_lbl.setWordWrap(True)
        text_lbl.setObjectName(f"{self.role}_bubble")  #  <-- QSS hook

        # Assemble row: avatars left for assistant, right for user
        if self.role == "assistant":
            if avatar_lbl.pixmap():
                row.addWidget(avatar_lbl)
            row.addWidget(text_lbl)
            row.addStretch(1)
        else:
            row.addStretch(1)
            row.addWidget(text_lbl)
            if avatar_lbl.pixmap():
                row.addWidget(avatar_lbl)

        root.addLayout(row)

        # Optional copy‑button bar ---------------------------------------#
        self._copy_bar = QWidget()
        copy_row = QHBoxLayout(self._copy_bar)
        copy_row.setContentsMargins(0, 0, 0, 0)

        copy_btn = QToolButton()
        copy_btn.setText("📋")
        copy_btn.setToolTip("Copy message text")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(text_lbl.text()))

        copy_row.addWidget(copy_btn)
        self._copy_bar.hide()  # shown on hover via eventFilter later (todo)
        root.addWidget(self._copy_bar)

        # Save refs for later use
        self.text_label = text_lbl
        self.avatar_label = avatar_lbl

        # Remove drop‑shadow (was causing visual noise)
        # (If future themes require shadow, implement purely in QSS)

    # ------------------------------------------------------------------#
    #                  Public helpers                                   #
    # ------------------------------------------------------------------#
    def set_text(self, text: str) -> None:
        """Change message text and update size."""
        self.text_label.setText(text)
        self.adjustSize()
