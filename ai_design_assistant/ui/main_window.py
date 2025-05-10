from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from urllib.parse import urlparse, unquote

# ────────────────────────────────────────────────
#  internal imports
# ────────────────────────────────────────────────
from ai_design_assistant.core.chat import ChatSession, Message
from ai_design_assistant.core.models import LLMRouter
from ai_design_assistant.core.settings import Settings
from ai_design_assistant.ui.chat_view import ChatView
from ai_design_assistant.ui.settings_dialog import SettingsDialog
from ai_design_assistant.ui.theme_utils import load_stylesheet
from ai_design_assistant.ui.workers import GenerateThread

ASSETS = Path(__file__).with_suffix("").parent.parent / "resources" / "icons"
USER_ICON = ASSETS / "user.png"
AI_ICON = ASSETS / "ai.png"


# ╭──────────────────────────────────────────────╮
# │                   Helpers                    │
# ╰──────────────────────────────────────────────╯
class EnterTextEdit(QTextEdit):
    """QTextEdit → emit sendRequested on bare Enter (Shift+Enter = newline)."""

    sendRequested = pyqtSignal()

    def keyPressEvent(self, ev: QKeyEvent) -> None:  # noqa: D401
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            ev.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.sendRequested.emit()
            return  # suppress newline
        super().keyPressEvent(ev)


class InputBar(QWidget):
    sendClicked = pyqtSignal(str)
    imageAttached = pyqtSignal(Path)

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # noqa: D401
        super().__init__(parent)
        self._build_ui()

    # ------------------------------------------------------------------#
    def _build_ui(self) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        self.text_edit = EnterTextEdit(self)
        self.text_edit.setPlaceholderText("Write a message…")
        self.text_edit.setFixedHeight(70)
        self.text_edit.sendRequested.connect(self._emit_send)

        attach_btn = QPushButton(self)
        attach_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        attach_btn.setToolTip("Attach image")
        attach_btn.clicked.connect(self._attach_image)

        send_btn = QPushButton(self)
        send_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward)
        )
        send_btn.setToolTip("Send")
        send_btn.clicked.connect(self._emit_send)

        lay.addWidget(attach_btn)
        lay.addWidget(self.text_edit, 1)
        lay.addWidget(send_btn)

    # ------------------------------------------------------------------#
    # slots
    # ------------------------------------------------------------------#
    def _emit_send(self) -> None:
        text = self.text_edit.toPlainText().strip()
        if text:
            self.text_edit.clear()
            self.sendClicked.emit(text)

    def _attach_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if file_path:
            self.imageAttached.emit(Path(file_path))


# ╭──────────────────────────────────────────────╮
# │                 MainWindow                   │
# ╰──────────────────────────────────────────────╯
class MainWindow(QMainWindow):
    def __init__(self) -> None:  # noqa: D401
        super().__init__()
        self.setWindowTitle("AI Design Assistant")
        self.resize(1200, 780)

        # keep references to active threads to avoid premature GC
        self._threads: list[QThread] = []

        self.router = LLMRouter()
        self.sessions: List[ChatSession] = []
        self.current: Optional[ChatSession] = None

        self._build_ui()
        self._load_chats()
        self._new_chat()  # initial session

    # ------------------------------------------------------------------#
    # UI layout
    # ------------------------------------------------------------------#
    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.setCentralWidget(splitter)

        # ── left sidebar ────────────────────────────────────────────────
        left = QWidget(self)
        l_lay = QVBoxLayout(left)
        new_btn = QPushButton("＋ New chat")
        new_btn.clicked.connect(self._new_chat)
        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self._switch_chat)
        settings_btn = QPushButton("⚙ Settings")
        settings_btn.setToolTip("Open preferences (Ctrl+,)")
        settings_btn.clicked.connect(self._open_settings)
        l_lay.addWidget(new_btn)
        l_lay.addWidget(self.chat_list, 1)
        l_lay.addWidget(settings_btn)

        # ── centre (chat) ──────────────────────────────────────────────
        center = QWidget(self)
        c_lay = QVBoxLayout(center)
        self.chat_view = ChatView(self)
        self.input_bar = InputBar(self)
        self.input_bar.sendClicked.connect(self._on_user_text)
        self.input_bar.imageAttached.connect(self._on_attachment)
        c_lay.addWidget(self.chat_view, 1)
        c_lay.addWidget(self.input_bar)

        # ── right sidebar (plugins) ────────────────────────────────────
        right = QTabWidget(self)
        right.setMinimumWidth(260)
        right.addTab(QLabel("Upscale (todo)"), "Upscale")
        right.addTab(QLabel("Remove BG (todo)"), "Remove BG")

        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setSizes([220, 700, 280])

    # ------------------------------------------------------------------#
    # Settings dialog helper
    # ------------------------------------------------------------------#
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        if dlg.exec() == dlg.accepted:
            # reload stylesheet according to saved theme
            style = load_stylesheet(Settings.load().theme)
            QApplication.instance().setStyleSheet(style)

    # ------------------------------------------------------------------#
    # Chat-session helpers
    # ------------------------------------------------------------------#
    def _new_chat(self) -> None:
        session = ChatSession()
        self.sessions.append(session)

        item = QListWidgetItem("Chat " + session.uuid[:6])
        item.setData(Qt.ItemDataRole.UserRole, session)
        self.chat_list.addItem(item)
        self.chat_list.setCurrentItem(item)

        self._activate_session(session)

    def _switch_chat(self, item: QListWidgetItem) -> None:
        session = item.data(Qt.ItemDataRole.UserRole)
        self._activate_session(session)

    def _activate_session(self, session: ChatSession) -> None:
        self.current = session
        self.chat_view.clear()
        for m in session.messages:
            self.chat_view.add_message(m.content, is_user=(m.role == "user"), image=m.image)

    # ------------------------------------------------------------------#
    # Sending / receiving
    # ------------------------------------------------------------------#
    def _on_user_text(self, text: str) -> None:  # noqa: C901 – verbose but straightforward
        if not self.current:
            return

        # Проверяем: это путь к файлу?
        if text.startswith("file://"):
            url = urlparse(text)
            path = unquote(url.path)

            # Убираем ведущий слэш под Windows
            if sys.platform.startswith("win") and path.startswith("/"):
                path = path[1:]

            if Path(path).exists():
                return self._on_attachment(Path(path))

        # append user message
        user_msg = Message(role="user", content=text)
        self.current.messages.append(user_msg)
        self.current.save()
        self.chat_view.add_message(text, is_user=True, image=None)


        # guard: only one generation at a time
        if any(t.isRunning() for t in self._threads):
            QMessageBox.warning(self, "Wait", "The model is still responding…")
            return

        # create empty assistant bubble for streaming
        assistant_bubble = self.chat_view.add_message("", is_user=False)
        self.current.assistant_bubble = assistant_bubble  # type: ignore[attr-defined]

        worker = GenerateThread(self.router, list(self.current.messages))
        worker.token_received.connect(self._on_token_received)
        worker.finished.connect(self._on_llm_reply)
        worker.error.connect(self._on_llm_error)
        worker.finished.connect(lambda: self._cleanup_thread(worker))
        worker.error.connect(lambda _: self._cleanup_thread(worker))
        worker.start()
        self._threads.append(worker)

    def _on_token_received(self, token: str) -> None:
        """Stream token-by-token into assistant bubble."""
        if not self.current or not hasattr(self.current, "assistant_bubble"):
            return
        lbl = self.current.assistant_bubble.label
        lbl.setText(lbl.text() + token)
        self.chat_view.scroll_to_bottom()

    def _on_llm_reply(self, _: str) -> None:
        if not self.current or not hasattr(self.current, "assistant_bubble"):
            return
        final_text = self.current.assistant_bubble.label.text()
        self.current.messages.append(Message(role="assistant", content=final_text))
        self.current.save()
        delattr(self.current, "assistant_bubble")

    def _on_llm_error(self, err: str) -> None:
        QMessageBox.critical(self, "LLM error", err)

    # ------------------------------------------------------------------#
    # Misc helpers
    # ------------------------------------------------------------------#
    def _cleanup_thread(self, thread: QThread) -> None:
        try:
            self._threads.remove(thread)
        except ValueError:
            pass
        thread.deleteLater()

    def _on_attachment(self, path: Path) -> None:
        if not self.current:
            return

            # 1. Добавляем сообщение с изображением
        text = self.input_bar.text_edit.toPlainText().strip()
        msg = Message(role="user", content=text, image=str(path))
        self.input_bar.text_edit.clear()

        self.current.messages.append(msg)
        self.current.save()

        # 2. Добавляем в UI
        self.chat_view.add_message(text, is_user=True, image=str(path))



        # 3. Запускаем генерацию
        if any(t.isRunning() for t in self._threads):
            QMessageBox.warning(self, "Wait", "The model is still responding…")
            return

        assistant_bubble = self.chat_view.add_message("", is_user=False)
        self.current.assistant_bubble = assistant_bubble  # type: ignore[attr-defined]

        worker = GenerateThread(self.router, list(self.current.messages))
        worker.token_received.connect(self._on_token_received)
        worker.finished.connect(self._on_llm_reply)
        worker.error.connect(self._on_llm_error)
        worker.finished.connect(lambda: self._cleanup_thread(worker))
        worker.error.connect(lambda _: self._cleanup_thread(worker))
        worker.start()
        self._threads.append(worker)

    def _load_chats(self) -> None:
        for session in ChatSession.load_all():
            self.sessions.append(session)
            item = QListWidgetItem("Chat " + session.uuid[:6])
            item.setData(Qt.ItemDataRole.UserRole, session)
            self.chat_list.addItem(item)


# ────────────────────────────────────────────────
# Entry-point convenience (dev only)
# ────────────────────────────────────────────────

def main() -> None:  # pragma: no cover
    app = QApplication(sys.argv)

    # apply stylesheet *before* showing window
    style = load_stylesheet(Settings.load().theme)
    app.setStyleSheet(style)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
