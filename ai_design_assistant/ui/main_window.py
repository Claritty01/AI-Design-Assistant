# ai_design_assistant/ui/main_window.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QEvent, QThread
from PyQt6.QtGui import QAction, QIcon, QKeyEvent, QPixmap
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
    QScrollArea,
    QSplitter,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ────────────────────────────────────────────────
#  internal imports ― пути поправлены
# ────────────────────────────────────────────────
from ai_design_assistant.core.chat import ChatSession, Message  # ⬅️ renamed
from ai_design_assistant.core.models import LLMRouter  # ⬅️ moved
from ai_design_assistant.ui.chat_view import ChatView
from ai_design_assistant.ui.workers import GenerateThread

from ai_design_assistant.ui.widgets import MessageBubble

ASSETS = Path(__file__).with_suffix("").parent.parent / "assets" / "icons"


# ╭──────────────────────────────────────────────╮
# │                   Helpers                    │
# ╰──────────────────────────────────────────────╯
class EnterTextEdit(QTextEdit):
    """QTextEdit → emit sendRequested on bare Enter (Shift + Enter → newline)."""
    sendRequested = pyqtSignal()

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                ev.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.sendRequested.emit()
            return  # откусываем перевод строки
        super().keyPressEvent(ev)



class InputBar(QWidget):
    sendClicked = pyqtSignal(str)
    imageAttached = pyqtSignal(Path)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

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
        send_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        send_btn.setToolTip("Send")
        send_btn.clicked.connect(self._emit_send)

        lay.addWidget(attach_btn)
        lay.addWidget(self.text_edit, 1)
        lay.addWidget(send_btn)

    # ――― slots ――― #
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
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI Design Assistant")
        self.resize(1200, 780)
        # храним ссылки на работающие потоки, чтобы их не прибило GC
        self._threads: list[QThread] = []

        self.router = LLMRouter()
        self.sessions: List[ChatSession] = []
        self.current: Optional[ChatSession] = None

        self._build_ui()
        self._create_menu()
        self._new_chat()  # стартовая сессия

    # ――― UI каркас ――― #
    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.setCentralWidget(splitter)

        # left sidebar
        left = QWidget(self)
        l_lay = QVBoxLayout(left)
        new_btn = QPushButton("＋ New chat")
        new_btn.clicked.connect(self._new_chat)
        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self._switch_chat)
        settings_btn = QPushButton("⚙ Settings")
        settings_btn.clicked.connect(lambda: QMessageBox.information(self, "Settings", "todo"))
        l_lay.addWidget(new_btn)
        l_lay.addWidget(self.chat_list, 1)
        l_lay.addWidget(settings_btn)

        # center (chat)
        center = QWidget(self)
        c_lay = QVBoxLayout(center)
        self.chat_view = ChatView(self)
        self.input_bar = InputBar(self)
        self.input_bar.sendClicked.connect(self._on_user_text)
        self.input_bar.imageAttached.connect(self._on_attachment)
        c_lay.addWidget(self.chat_view, 1)
        c_lay.addWidget(self.input_bar)

        # right sidebar (plugins)
        right = QTabWidget(self)
        right.setMinimumWidth(260)
        right.addTab(QLabel("Upscale (todo)"), "Upscale")
        right.addTab(QLabel("Remove BG (todo)"), "Remove BG")

        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setSizes([220, 700, 280])

    def _create_menu(self) -> None:
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        self.menuBar().addAction(quit_action)

    # ――― chat-session helpers ――― #
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
            self.chat_view.add_message(m.content, is_user=(m.role == "user"))

    # ――― sending / receiving ――― #
    def _on_user_text(self, text: str) -> None:
        try:
            if not self.current:
                return
            msg = Message(role="user", content=text)
            self.current.messages.append(msg)
            self.chat_view.add_message(text, is_user=True)

            if any(t.isRunning() for t in self._threads):
                QMessageBox.warning(self, "Подождите", "Модель ещё отвечает.")
                return

            worker = GenerateThread(self.router, list(self.current.messages))
            worker.finished.connect(self._on_llm_reply)
            worker.error.connect(self._on_llm_error)
            worker.finished.connect(lambda: self._cleanup_thread(worker))
            worker.error.connect(lambda _: self._cleanup_thread(worker))
            worker.start()
            self._threads.append(worker)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Ошибка при отправке сообщения: {e}"
            )
            raise  # Перебросить исключение для отладки

    def _on_llm_reply(self, reply: str) -> None:
        try:
            if not self.current:
                return
            self.current.messages.append(Message(role="assistant", content=reply))
            self.chat_view.add_message(reply, is_user=False)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при получении ответа: {e}")
            import traceback
            traceback.print_exc()

    def _cleanup_thread(self, thread: QThread) -> None:
        try:
            self._threads.remove(thread)
        except ValueError:
            pass
        thread.deleteLater()

    def _on_attachment(self, path: Path) -> None:
        self._on_user_text(f"[Image] {path.name}")

    def _on_llm_reply(self, reply: str) -> None:
        if not self.current:
            return
        self.current.messages.append(Message(role="assistant", content=reply))
        self.chat_view.add_message(reply, is_user=False)

    def _on_llm_error(self, err: str) -> None:
        QMessageBox.critical(self, "LLM error", err)


# ────────────────────────────────────────────────
def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()