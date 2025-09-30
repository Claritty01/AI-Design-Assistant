from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import List, Optional

from importlib import import_module

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QKeyEvent, QPixmap
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
    QToolButton,
    QWidget,
)

from urllib.parse import urlparse, unquote

# ────────────────────────────────────────────────
#  internal imports
# ────────────────────────────────────────────────
from ai_design_assistant.core.chat import ChatSession, Message, _DEFAULT_TITLE
from ai_design_assistant.core.models import LLMRouter
from ai_design_assistant.core.plugins import get_plugin_manager
from ai_design_assistant.core.settings import Settings
from ai_design_assistant.ui.chat_view import ChatView
from ai_design_assistant.ui.settings_dialog import SettingsDialog
from ai_design_assistant.ui.theme_utils import load_stylesheet
from ai_design_assistant.ui.workers import GenerateThread
from ai_design_assistant.ui.gallery_panel import GalleryPanel
from ai_design_assistant.core.settings import get_chats_directory

import logging
_LOGGER = logging.getLogger(__name__)


ASSETS = Path(__file__).with_suffix("").parent.parent / "resources" / "icons"
USER_ICON = ASSETS / "user.png"
AI_ICON = ASSETS / "ai.png"


# ╭──────────────────────────────────────────────╮
# │                   Helpers                    │
# ╰──────────────────────────────────────────────╯
class EnterTextEdit(QTextEdit):
    """QTextEdit → emit sendRequested on bare Enter (Shift+Enter = newline)."""

    sendRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.input_bar = parent  # прямой доступ к InputBar

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                # ⬇ здесь нужно повторить логику как при нажатии на кнопку 📎
                self.input_bar._attach_image_from_path(path)



    def keyPressEvent(self, ev: QKeyEvent) -> None:  # noqa: D401
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            ev.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.sendRequested.emit()
            return  # suppress newline
        super().keyPressEvent(ev)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                    event.acceptProposedAction()
                    return
        event.ignore()


class InputBar(QWidget):
    sendClicked = pyqtSignal(tuple)  # text + image
    imageAttached = pyqtSignal(Path)  # (можно удалить, если не используешь)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.attached_image: Optional[Path] = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.text_edit = EnterTextEdit(self)
        self.text_edit.setPlaceholderText("Write a message…")
        self.text_edit.setFixedHeight(70)
        self.text_edit.sendRequested.connect(self._emit_send)

        self.attach_btn = QPushButton("📎", self)
        self.attach_btn.setObjectName("upload_button")
        self.attach_btn.setFixedWidth(30)
        self.attach_btn.clicked.connect(self._attach_image)

        send_btn = QPushButton("📤", self)
        send_btn.setObjectName("send_button")
        send_btn.setFixedWidth(30)
        send_btn.clicked.connect(self._emit_send)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(4, 4, 4, 0)
        input_row.setSpacing(6)
        input_row.addWidget(self.attach_btn)
        input_row.addWidget(self.text_edit, 1)
        input_row.addWidget(send_btn)

        # --- Превью выбранного файла ---
        self.preview_widget = QWidget(self)
        preview_layout = QHBoxLayout(self.preview_widget)
        preview_layout.setContentsMargins(6, 2, 6, 2)

        self.preview_thumb = QLabel()
        self.preview_thumb.setFixedSize(48, 48)

        self.preview_name = QLabel()
        self.preview_name.setStyleSheet("color: #ccc; font-size: 12px;")

        remove_btn = QToolButton()
        remove_btn.setText("✖")
        remove_btn.clicked.connect(self._clear_attachment)

        preview_layout.addWidget(self.preview_thumb)
        preview_layout.addWidget(self.preview_name, 1)
        preview_layout.addWidget(remove_btn)

        self.preview_widget.setVisible(False)

        # --- Общий layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.addLayout(input_row)
        main_layout.addWidget(self.preview_widget)

    def _emit_send(self) -> None:
        text = self.text_edit.toPlainText().strip()
        if text or self.attached_image:
            self.sendClicked.emit((text, self.attached_image))
            self.text_edit.clear()
            self._clear_attachment()

    def _attach_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", str(Path.home()), "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if file_path:
            self.attached_image = Path(file_path)
            pixmap = QPixmap(file_path).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
            self.preview_thumb.setPixmap(pixmap)
            self.preview_name.setText(Path(file_path).name)
            self.preview_widget.setVisible(True)

    def _clear_attachment(self) -> None:
        self.attached_image = None
        self.preview_widget.setVisible(False)
        self.preview_thumb.clear()
        self.preview_name.setText("")

    def _attach_image_from_path(self, file_path: str) -> None:
        self._clear_attachment()

        self.attached_image = Path(file_path)
        pixmap = QPixmap(file_path).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
        self.preview_thumb.setPixmap(pixmap)
        self.preview_name.setText(Path(file_path).name)
        self.preview_widget.setVisible(True)


# ╭──────────────────────────────────────────────╮
# │                 MainWindow                   │
# ╰──────────────────────────────────────────────╯
class MainWindow(QMainWindow):
    def __init__(self) -> None:  # noqa: D401
        super().__init__()
        self.plugin_widgets: dict[str, QWidget] = {}
        self.setWindowTitle("AI Design Assistant")
        self.resize(1400, 780)

        # keep references to active threads to avoid premature GC
        self._threads: list[QThread] = []

        self.settings = Settings.load()
        try:
            if self.settings.model_provider.startswith("local"):
                import_module(f"ai_design_assistant.api.{self.settings.model_provider}_backend")
        except Exception as e:
            # не критично для старта окна — просто залогируем
            _LOGGER.warning("Начальный backend '%s' не загрузился: %s",
                            self.settings.model_provider, e)
        self.router = LLMRouter(default=self.settings.model_provider)
        self.sessions: List[ChatSession] = []
        self.current: Optional[ChatSession] = None

        self.plugin_display_names: dict[str, str] = {}

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
        new_btn.setObjectName("new_chat_button")
        new_btn.clicked.connect(self._new_chat)
        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self._switch_chat)
        settings_btn = QPushButton("⚙ Settings")
        settings_btn.setObjectName("settings_button")
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
        self.input_bar.sendClicked.connect(self._on_user_message)
        self.input_bar.imageAttached.connect(self._on_attachment)
        c_lay.addWidget(self.chat_view, 1)
        c_lay.addWidget(self.input_bar)

        # ── right sidebar (plugins) ────────────────────────────────────
        right = QTabWidget(self)
        right.setMinimumWidth(260)
        right.currentChanged.connect(self._on_tab_changed)
        self._tabs = right

        self.gallery_panel = GalleryPanel(self._get_current_chat_folder, self._on_gallery_image_selected)
        right.addTab(self.gallery_panel, "Gallery")

        # ⬇ сначала плагин-вкладки
        from ai_design_assistant.core.plugins import get_plugin_manager
        for plugin in get_plugin_manager().metadata().values():
            instance = get_plugin_manager().get(plugin.name)
            widget = getattr(instance, "get_widget", lambda: None)()
            if widget:
                self.plugin_widgets[plugin.name] = widget
                self.plugin_display_names[plugin.name] = plugin.display_name  # обязательно сохраняем

                if self.settings.plugins_enabled.get(plugin.name, True):  # показываем только включённые
                    right.addTab(widget, plugin.display_name)

        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(right)

        # ⬅ обязательно вернуть splitter.setSizes([...]) если было
        splitter.setSizes([220, 700, 480])

    def _get_current_chat_folder(self) -> str:
        if not self.current:
            return ""
        return str(self.current._path.parent)

    def _on_gallery_image_selected(self, path: str) -> None:
        for plugin in get_plugin_manager().metadata().values():
            instance = get_plugin_manager().get(plugin.name)
            widget = getattr(instance, "get_widget", lambda: None)()
            if widget and hasattr(widget, "set_image"):
                widget.set_image(path)

    # ------------------------------------------------------------------#
    # Settings dialog helper
    # ------------------------------------------------------------------#
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        if dlg.exec():
            self.reload_settings()
            self._update_plugin_tabs()  # применяем чекбоксы плагинов

    # ------------------------------------------------------------------#
    # Chat-session helpers
    # ------------------------------------------------------------------#
    def _new_chat(self) -> None:
        session = ChatSession.create_new()
        self.sessions.append(session)

        item = QListWidgetItem(session.title)
        item.setData(Qt.ItemDataRole.UserRole, session)
        self.chat_list.addItem(item)
        self.chat_list.setCurrentItem(item)

        self._activate_session(session)

    def _switch_chat(self, item: QListWidgetItem) -> None:
        session = item.data(Qt.ItemDataRole.UserRole)
        self._activate_session(session)
        self.gallery_panel.refresh()

    def _activate_session(self, session: ChatSession) -> None:
        self.current = session
        self.chat_view.clear()
        chat_folder = session._path.parent

        for m in session.messages:
            img = str(chat_folder / m.image) if m.image else None
            self.chat_view.add_message(m.content, is_user=(m.role == "user"), image=img)

        self.gallery_panel.refresh()

        # 👇 Вот здесь можно безопасно использовать session
        chat_folder = str(session._path.parent)
        for plugin_name, widget in self.plugin_widgets.items():
            if hasattr(widget, "set_chat_folder"):
                widget.set_chat_folder(chat_folder)

    # ------------------------------------------------------------------#
    # Sending / receiving
    # ------------------------------------------------------------------#
    def _on_user_message(self, payload: tuple[str, Optional[Path]]) -> None:
        if not self.current:
            return

        text, image_path = payload
        if image_path:
            msg = self.current.add_image_message(role="user", content=text, image_path=image_path)
        else:
            msg = self.current.add_message(role="user", content=text)
        self.chat_view.add_message(text, is_user=True, image=str(image_path) if image_path else None)
        self.gallery_panel.refresh()

        # Проверка и суммаризация
        user_msgs = [m for m in self.current.messages if m.role == "user"]
        if len(user_msgs) == 2 and self.current.title == _DEFAULT_TITLE:
            new_title = self.current.summarize_chat()
            if (item := self.chat_list.currentItem()):
                item.setText(new_title)

        # guard: only one generation at a time
        if any(t.isRunning() for t in self._threads):
            QMessageBox.warning(self, "Wait", "The model is still responding…")
            return
        assistant_bubble = self.chat_view.add_message("", is_user=False)
        self.gallery_panel.refresh()
        self.current.assistant_bubble = assistant_bubble  # type: ignore[attr-defined]

        worker = GenerateThread(
            self.get_router,  # передаём ссылку на функцию, а не сам объект
            list(self.current.messages),
            self.current._path.parent,
            self.current._path
        )

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
        # ── обновляем заголовок, если уже есть ≥ 2 user-сообщений ──────────
        if sum(1 for m in self.current.messages if m.role == "user") >= 2:
            new_title = self.current.summarize_chat()

            # ищем соответствующий QListWidgetItem и меняем текст
            for i in range(self.chat_list.count()):
                item = self.chat_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) is self.current:
                    item.setText(new_title)
                    break

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

    def get_router(self) -> LLMRouter:
        return self.router

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

        self.gallery_panel.refresh()


        # 3. Запускаем генерацию
        if any(t.isRunning() for t in self._threads):
            QMessageBox.warning(self, "Wait", "The model is still responding…")
            return

        assistant_bubble = self.chat_view.add_message("", is_user=False)
        self.gallery_panel.refresh()
        self.current.assistant_bubble = assistant_bubble  # type: ignore[attr-defined]

        worker = GenerateThread(
            self.get_router,  # передаём ссылку на функцию, а не сам объект
            list(self.current.messages),
            self.current._path.parent,
            self.current._path
        )

        worker.token_received.connect(self._on_token_received)
        worker.finished.connect(self._on_llm_reply)
        worker.error.connect(self._on_llm_error)
        worker.finished.connect(lambda: self._cleanup_thread(worker))
        worker.error.connect(lambda _: self._cleanup_thread(worker))
        worker.start()
        self._threads.append(worker)

    def _load_chats(self) -> None:
        """Заполняем левую колонку уже существующими чатами."""
        for session in ChatSession.load_all():
            self.sessions.append(session)

            item = QListWidgetItem(session.title)  # ← создаём item
            item.setData(Qt.ItemDataRole.UserRole, session)
            self.chat_list.addItem(item)

    def refresh_gallery(self):
        self.gallery_panel.refresh()

    def _on_tab_changed(self, index: int) -> None:
        widget = self._tabs.widget(index)
        if widget is self.gallery_panel:
            self.gallery_panel.refresh()

    def _update_plugin_tabs(self) -> None:
        """Показать или скрыть вкладки плагинов согласно настройкам."""
        enabled_plugins = self.settings.plugins_enabled
        for name, widget in self.plugin_widgets.items():
            index = self._tabs.indexOf(widget)
            if enabled_plugins.get(name, True):
                if index == -1:
                    display_name = self.plugin_display_names.get(name, name)
                    self._tabs.addTab(widget, display_name)
            else:
                if index != -1:
                    self._tabs.removeTab(index)

    def reload_settings(self) -> None:
        """Перезагрузить настройки и пересоздать router безопасно (с фолбэком на local)."""
        from importlib import import_module, reload
        from ai_design_assistant.core.models import LLMRouter, register_backend, _BACKENDS

        self.settings = Settings.load()

        # Чистим список зарегистрированных бэкендов
        _BACKENDS.clear()

        desired = self.settings.model_provider

        def _try_load_and_register(name: str) -> bool:
            """Пробует импортировать модуль бэкенда и зарегистрировать его. Возвращает успех."""
            module_path = f"ai_design_assistant.api.{name}_backend"
            try:
                mod = import_module(module_path)
                # Перезагрузим модуль, если уже был импортирован (чтобы сработал register заново)
                if module_path in sys.modules:
                    mod = reload(mod)
                backend = getattr(mod, "backend", None)
                if backend is not None:
                    register_backend(backend)
                    _LOGGER.info("Backend '%s' загружен и зарегистрирован", name)
                    return True
                _LOGGER.warning("Модуль %s загружен, но не содержит 'backend'", module_path)
            except ImportError as e:
                _LOGGER.warning("Backend '%s' пропущен (ImportError): %s", name, e)
            except Exception as e:
                _LOGGER.warning("Backend '%s' не загрузился: %s", name, e)
            return False

        # 1) Пытаемся загрузить желаемый провайдер из настроек
        loaded_name = None
        if _try_load_and_register(desired):
            loaded_name = desired
        else:
            # 2) Фолбэки: сначала 'local', затем 'local_qwen25' (если есть в проекте)
            for fallback in ("local", "local_qwen25"):
                if _try_load_and_register(fallback):
                    loaded_name = fallback
                    _LOGGER.info("Провайдер '%s' недоступен — используем фолбэк '%s'", desired, fallback)
                    break

        if not loaded_name:
            # Это совсем крайний случай: ни один бэкенд не поднялся.
            # Чтобы не падать дальше, просто оставим старый router как есть (если был),
            # и применим тему. В лог — ошибку.
            _LOGGER.error("Не удалось загрузить ни один LLM backend. Оставляю прежний router.")
            self._apply_theme(self.settings.theme)
            return

        # Пересоздаём роутер с рабочим дефолтом
        self.router = LLMRouter(default=loaded_name)

        # Применяем тему сразу
        self._apply_theme(self.settings.theme)

    def _apply_theme(self, theme: str) -> None:
        """Загрузить QSS-файл и применить к приложению."""
        style = load_stylesheet(theme)
        QApplication.instance().setStyleSheet(style)


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


_MAIN_WINDOW: MainWindow | None = None

def get_main_window() -> MainWindow:
    return _MAIN_WINDOW