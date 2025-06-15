"""Reusable Qt widgets for AI Design Assistant UI."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QEvent, QTimer, QSize
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QSizePolicy
)

ICONS_DIR = Path(__file__).with_suffix("").parent.parent / "resources" / "icons"


class MessageBubble(QWidget):
    def __init__(self, text: str, is_user: bool, image: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.is_user = is_user
        self.setProperty("bubbleRole", "user" if is_user else "assistant")

        # Внешний layout: горизонтальный
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(8)

        # Иконка
        icon_label = QLabel()
        icon_path = Path(__file__).parent.parent / "resources" / "icons" / ("user.png" if is_user else "ai.png")
        if icon_path.exists():
            pix = QPixmap(str(icon_path)).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)
            icon_label.setPixmap(pix)

        # Контентный layout (текст + изображение)
        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(12, 8, 12, 8)
        content_layout.setSpacing(6)

        if image and Path(image).exists():
            pixmap = QPixmap(image)
            if not pixmap.isNull():
                img_label = QLabel()
                img_label.setPixmap(pixmap.scaled(
                    QSize(256, 256), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                ))
                content_layout.addWidget(img_label)
                self.has_image = True

        self.label = QLabel(text)
        self.label.setStyleSheet("background: transparent; font-size: 14px;")
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(self.label)

        content_wrapper.setProperty("bubbleRole", "user" if is_user else "assistant")  # <-- фон на обёртке
        content_wrapper.setStyleSheet("")  # пусть применяется из QSS

        if is_user:
            outer_layout.addStretch()
            outer_layout.addWidget(content_wrapper)
            outer_layout.addWidget(icon_label)
        else:
            outer_layout.addWidget(icon_label)
            outer_layout.addWidget(content_wrapper)
            outer_layout.addStretch()

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
