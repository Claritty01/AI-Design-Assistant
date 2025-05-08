"""Primary Qt window for AI Design Assistant.

The goal is to keep *all* Qt‑specific code in the ``ui`` package. This module
hosts the main frame, assembles child widgets (chat list, input line, plugin
panel), wires menus and forwards user input to the **core** layer.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ai_design_assistant.core import ChatSession, Message, Settings, get_global_router
from ai_design_assistant.ui.workers import StreamWorker
from ai_design_assistant.ui.plugin_panel import PluginPanel


_LOGGER = logging.getLogger(__name__)
_RES_DIR: Final = Path(__file__).with_suffix("").parent / "resources"


# ---------------------------------------------------------------------------
# Background worker (simple streaming wrapper)
# ---------------------------------------------------------------------------


class StreamWorker(QThread):
    token_received = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, messages: list[Message]):
        super().__init__()
        self._messages = messages
        self._router = get_global_router()

    def run(self) -> None:  # noqa: D401
        try:
            for token in self._router.stream(self._messages):
                self.token_received.emit(token)
        except Exception as exc:  # pragma: no cover
            _LOGGER.exception("Streaming failed")
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    """Top‑level application window."""

    def __init__(self) -> None:  # noqa: D401
        super().__init__()
        self.setWindowTitle("AI Design Assistant")
        self.resize(1024, 720)

        # state
        self.settings = Settings.load()
        self.chat = ChatSession(title="Session")
        # ui helpers
        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI construction helpers
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        # Splitter: left (chat list) | right (plugins) — placeholders
        self.splitter = QSplitter(Qt.Orientation.Horizontal, central)

        # Left pane: chat history + input
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self.chat_list = QListWidget()
        self.input_line = QLineEdit()
        self.send_button = QPushButton("Send")

        left_layout.addWidget(self.chat_list, 1)
        input_box = QWidget()
        h = QHBoxLayout(input_box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.input_line, 1)
        h.addWidget(self.send_button)
        left_layout.addWidget(input_box)

        # Right pane placeholder (plugins later)
        right_pane = QWidget()
        right_layout = QVBoxLayout(right_pane)
        right_layout.addWidget(QWidget())  # TODO: plugin panel

        self.splitter.addWidget(left_pane)
        self.splitter.addWidget(right_pane)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.splitter)

        # Toolbar (theme switch, model provider, etc.) — minimal now
        tb = QToolBar("Main")
        self.addToolBar(tb)
        save_act = QAction(QIcon.fromTheme("document-save"), "Save chat", self)
        save_act.triggered.connect(self._save_chat)
        tb.addAction(save_act)

    def _connect_signals(self) -> None:  # noqa: D401
        self.send_button.clicked.connect(self._on_send_clicked)
        self.input_line.returnPressed.connect(self._on_send_clicked)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_send_clicked(self) -> None:
        text = self.input_line.text().strip()
        if not text:
            return
        self.input_line.clear()

        # add user msg
        user_msg = self.chat.add_message("user", text)
        QListWidgetItem(f"🧑 {text}", self.chat_list)

        # start stream worker
        self.worker = StreamWorker(self.chat.messages)
        self.worker.token_received.connect(self._on_token)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self._on_stream_finished)
        self.worker.start()

    def _on_token(self, token: str) -> None:  # noqa: D401
        # if last item is assistant line, append; else create
        if self.chat_list.count() and self.chat_list.item(self.chat_list.count() - 1).text().startswith("🤖"):
            item = self.chat_list.item(self.chat_list.count() - 1)
            item.setText(item.text() + token)
        else:
            QListWidgetItem(f"🤖 {token}", self.chat_list)
        self.chat_list.scrollToBottom()

    def _on_stream_finished(self) -> None:  # noqa: D401
        # save assistant message fully
        if self.chat_list.count():
            last = self.chat_list.item(self.chat_list.count() - 1).text()
            # strip emoji & space
            content = last[2:].lstrip()
            self.chat.add_message("assistant", content)
        _LOGGER.debug("Assistant message saved (%d total)", len(self.chat.messages))

    def _on_error(self, msg: str) -> None:  # noqa: D401
        QListWidgetItem(f"⚠️  Error: {msg}", self.chat_list)

    # ------------------------------------------------------------------
    # Menu / toolbar callbacks
    # ------------------------------------------------------------------
    def _save_chat(self) -> None:
        path = self.chat.save()
        _LOGGER.info("Chat saved to %s", path)


# ---------------------------------------------------------------------------
# Entry‑point for `python -m ai_design_assistant.ui.main_window` (dev‑only)
# ---------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    import sys

    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
