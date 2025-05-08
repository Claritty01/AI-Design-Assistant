from __future__ import annotations

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QLabel,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QDialog,
    QMessageBox, QScrollArea, QToolButton, QSplitter, QSizePolicy
)
from PyQt5.QtWidgets import QComboBox
from ai_design_assistant.core.models import get_current_model, set_current_model, list_models
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QEvent
from PyQt5.QtGui import QFont, QPixmap, QIcon
import os
import shutil
from pathlib import Path

from ai_design_assistant.core.logger import get_logger
from ai_design_assistant.core.models import stream_chat_response
from ai_design_assistant.core.settings import load_settings, save_settings
from ai_design_assistant.core.chat import ChatSession
from ai_design_assistant.core.chat import load_chats, create_new_chat
from ai_design_assistant.core.plugins import get_plugins

from settings_dialog import SettingsDialog   # <— новый импорт
from ai_design_assistant.core.settings import AppSettings             # <— нужен для apply_theme




log = get_logger("ui")


USER_AVA = "icons/user.png"
AI_AVA   = "icons/ai.png"


def list_chat_images(chat_json_name: str) -> list[str]:
    """Вернуть список путей к изображениям, хранящимся в папке текущего чата."""
    folder = Path("../chat_data") / chat_json_name.replace(".json", "")
    exts = ("*.png", "*.jpg", "*.jpeg", "*.bmp")
    paths: list[str] = []
    for p in exts:
        paths.extend(map(str, folder.glob(p)))
    paths.sort()
    return paths

# ────────────────────────────────────────────────────────────
# Background stream worker
# -----------------------------------------------------------------------------

class StreamWorker(QThread):
    token_received = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, user_text: str, image_path: str | None = None):
        super().__init__()
        self.user_text = user_text
        self.image_path = image_path

    def run(self):
        try:
            for token, _ in stream_chat_response(self.user_text, image_path=self.image_path):
                self.token_received.emit(token)
        except Exception as exc:
            log.exception("StreamWorker failed")
            self.token_received.emit(f"\n[Ошибка потока: {exc}]")
        self.finished.emit()


# ────────────────────────────────────────────────────────────
# Bubble widget ala Silly Tavern
# ---------------------------------------------------------------------------
class MessageBubble(QWidget):
    def __init__(self, text: str, role: str, avatar: QPixmap | None = None):
        super().__init__()

        # 1) Основной вертикальный лэйаут
        main = QVBoxLayout(self)
        main.setSpacing(4)
        main.setContentsMargins(6, 6, 6, 6)

        user_side = (role == "user")

        # 2) Создаём QLabel для текста сразу, до компоновки
        self.txt = QLabel(text)
        self.txt.setWordWrap(True)
        self.txt.setMaximumWidth(480)
        self.txt.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.txt.setProperty("bubbleRole", role)

        # 3) Верхняя строка: аватар + пузырь + спейсер
        top = QHBoxLayout()
        top.setSpacing(6)

        # аватар (если есть)
        if avatar:
            ava_lbl = QLabel()
            ava_lbl.setPixmap(avatar.scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        # «губка» для прижатия
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        if user_side:
            # пользователь: [spacer][txt][avatar?]
            top.addWidget(spacer)
            top.addWidget(self.txt)
            if avatar:
                top.addWidget(ava_lbl)
        else:
            # ассистент: [avatar?][txt][spacer]
            if avatar:
                top.addWidget(ava_lbl)
            top.addWidget(self.txt)
            top.addWidget(spacer)

        main.addLayout(top)

        # 4) Нижняя строка: зарезервированная зона под кнопку копирования
        self.copy_bar = QWidget()
        self.copy_bar.setFixedHeight(24)
        copy_layout = QHBoxLayout(self.copy_bar)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.addStretch()
        copy_btn = QToolButton()
        copy_btn.setText("📋")
        copy_btn.clicked.connect(self.copy_text)
        copy_layout.addWidget(copy_btn)
        self.copy_bar.hide()
        main.addWidget(self.copy_bar)

        # 5) Включаем Hover-события
        self.setAttribute(Qt.WA_Hover)

    def copy_text(self):
        QApplication.clipboard().setText(self.txt.text())

    # Пока эта функция не нужна, пусть пока всегда скрыта кнопка
    def event(self, e):
        if e.type() == QEvent.HoverEnter:
            self.copy_bar.hide()
        elif e.type() == QEvent.HoverLeave:
            self.copy_bar.hide()
        return super().event(e)





# ────────────────────────────────────────────────────────────
# Main Chat Window
# -----------------------------------------------------------------------------

class ChatWindow(QMainWindow):
    THUMB_SIZE = QSize(80, 80)

    def __init__(self):
        super().__init__()
        self.current_chat = create_new_chat()
        set_current_chat(os.path.join("../chat_data", self.current_chat["file"]))

        self.chat_history = load_history()
        self.settings = load_settings()
        self.current_theme = self.settings.get("theme", "dark").lower()

        self.image_path: str | None = None  # last uploaded image (for sending)
        self.reply_buffer: str = ""
        self.selected_gallery_image: str | None = None

        self.setWindowTitle("ИИ‑ассистент дизайна")
        self.setMinimumSize(1100, 700)

        self.build_ui()
        self.apply_theme()

    # ────────────────────────────────────────────────────────
    # UI build helpers
    # -------------------------------------------------------

    def build_ui(self):
        # левые / центральные / правые панели
        sidebar_left = self.build_left_sidebar()
        chat_widget = self.build_chat_area()
        sidebar_right = self.build_right_sidebar()
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(sidebar_left)
        splitter.addWidget(chat_widget)
        splitter.addWidget(sidebar_right)
        splitter.setStretchFactor(1, 3)  # центр тянется больше

        self.setCentralWidget(splitter)

    def build_left_sidebar(self) -> QWidget:
        vbox = QVBoxLayout()
        app_title = QLabel("🎨 ИИ‑ассистент")
        app_title.setFont(QFont("Arial", 18, QFont.Bold))
        vbox.addWidget(app_title)

        self.chat_list_widget = QListWidget()
        self.chat_list_widget.itemClicked.connect(self.handle_chat_selection)
        vbox.addWidget(QLabel("💬 Диалоги"))
        vbox.addWidget(self.chat_list_widget)
        self.refresh_chat_list()

        settings_btn = QPushButton("⚙️ Настройки…")
        settings_btn.clicked.connect(self.open_settings)
        vbox.addWidget(settings_btn)

        new_btn = QPushButton("➕ Новый диалог")
        new_btn.clicked.connect(self.create_and_switch_chat)
        vbox.addWidget(new_btn)

        theme_btn = QPushButton("🌓 Переключить тему")
        theme_btn.clicked.connect(self.toggle_theme)
        vbox.addWidget(theme_btn)

        # ─── выбор LLM ─────────────────────────────────────────
        h_model = QHBoxLayout()
        h_model.addWidget(QLabel("🧠 Модель"))
        self.cmb_model = QComboBox()
        self.cmb_model.addItems(list_models())
        self.cmb_model.setCurrentText(get_current_model())
        self.cmb_model.currentTextChanged.connect(self.on_model_changed)
        h_model.addWidget(self.cmb_model)
        vbox.addLayout(h_model)

        vbox.addStretch()
        w = QWidget(); w.setLayout(vbox); return w

    def build_chat_area(self) -> QWidget:
        # ---------- область прокрутки с пузырями ----------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setSpacing(4)
        self.chat_layout.addStretch()  # чтобы всё липло вверх

        self.scroll.setWidget(self.chat_container)

        # восстановим историю
        for msg in self.chat_history:
            self._add_bubble(msg["role"], msg["content"], avatar_path=None)

        self.spinner_label = QLabel("💬 ИИ набирает ответ…")
        self.spinner_label.setStyleSheet("color: gray;")
        self.spinner_label.setVisible(False)

        # ---------- нижняя панель ввода ----------
        self.input_field = QLineEdit();
        self.input_field.setPlaceholderText("Введите сообщение…")
        self.input_field.setMinimumHeight(40)
        self.input_field.setStyleSheet("padding-left:6px; font-size:14px;")

        self.upload_button = QPushButton("📎");
        self.upload_button.setFixedSize(40, 40);
        self.upload_button.clicked.connect(self.upload_image)
        self.send_button = QPushButton("Отправить");
        self.send_button.setMinimumHeight(40);
        self.send_button.setStyleSheet("font-size:14px;")
        self.send_button.clicked.connect(self.send_message)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input_field, 1)
        input_row.addWidget(self.upload_button)
        input_row.addWidget(self.send_button)

        # ---------- финальная сборка ----------
        vbox = QVBoxLayout()
        vbox.addWidget(self.spinner_label)
        vbox.addWidget(self.scroll, 1)  # растягиваем
        vbox.addLayout(input_row, 0)

        wrapper = QWidget();
        wrapper.setLayout(vbox)
        return wrapper

    def build_right_sidebar(self) -> QWidget:
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("🧩 Плагины"))

        self.plugins = get_plugins()  # ← словарь {name: module}

        for name, plugin in self.plugins.items():
            btn = QPushButton(name)
            btn.clicked.connect(lambda _, p=plugin: self.run_plugin(p))
            vbox.addWidget(btn)


        vbox.addWidget(QLabel("🖼️ Галерея"))
        self.gallery = QListWidget(); self.gallery.setIconSize(self.THUMB_SIZE); self.gallery.itemClicked.connect(self.select_gallery_item)
        vbox.addWidget(self.gallery, 1)
        self.refresh_gallery()

        vbox.addStretch(); w = QWidget(); w.setLayout(vbox); return w



    # ────────────────────────────────────────────────────────
    # Chat / history helpers
    # -------------------------------------------------------



    # ────────────────────────────────────────────────────────
    # Message sending
    # -------------------------------------------------------

    def send_message(self):
        user_text = self.input_field.text().strip()
        if not user_text and not self.image_path:
            return

        # record last image (if none newly picked, re‑use last from history)
        if not self.image_path:
            for m in reversed(self.chat_history):
                if m.get("role") == "user" and "image" in m:
                    self.image_path = m["image"]; break

        # display user prompt
        self._add_bubble("user", user_text or "[изображение]")
        self.current_bubble = self._add_bubble("assistant", "")  # пустой, будем дописывать
        self.spinner_label.setVisible(True)

        self.last_user_text = user_text; self.last_user_image = self.image_path

        self.worker = StreamWorker(user_text, image_path=self.image_path)
        self.worker.token_received.connect(self.append_streamed_token)
        self.worker.finished.connect(self.on_stream_finished)
        self.worker.start()

        self.input_field.clear(); self.image_path = None; self.reply_buffer = ""; self.refresh_gallery()

    # stream callbacks
    def append_streamed_token(self, token: str):
        self.reply_buffer += token
        self.current_bubble.txt.setText(self.reply_buffer)
        self.current_bubble.txt.adjustSize()  # пересчитать QLabel
        self.current_bubble.adjustSize()  # пересчитать весь пузырь
        self.chat_layout.invalidate()  # перестроить layout

        QApplication.processEvents()

    def on_stream_finished(self):
        self.spinner_label.setVisible(False)
        append_message(self.chat_history, "user", self.last_user_text, image=self.last_user_image)
        append_message(self.chat_history, "assistant", self.reply_buffer)
        save_history(self.chat_history)


    # ────────────────────────────────────────────────────────
    # Gallery functionality
    # -------------------------------------------------------


    def refresh_gallery(self):
        self.gallery.clear()
        for path in list_chat_images(self.current_chat["file"]):
            if not os.path.exists(path):
                continue
            icon = QIcon(QPixmap(path).scaled(self.THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            item = QListWidgetItem(icon, "")
            item.setData(Qt.UserRole, path)
            self.gallery.addItem(item)

    def select_gallery_item(self, item: QListWidgetItem):
        self.selected_gallery_image = item.data(Qt.UserRole)
        # highlight selection handled automatically by QListWidget

    # module actions from sidebar (operate on selected image)
    def _require_selection(self) -> str | None:
        if not self.selected_gallery_image:
            QMessageBox.information(self, "Нет изображения", "Сначала выберите изображение в галерее.")
            return None
        return self.selected_gallery_image

    # ────────────────────────────────────────────────────────
    # Image upload
    # -------------------------------------------------------

    def upload_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите изображение", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not file_path:
            return
        chat_folder = Path("../chat_data") / self.current_chat["file"].replace(".json", "")
        chat_folder.mkdir(parents=True, exist_ok=True)
        img_idx = len([m for m in self.chat_history if "image" in m]) + 1
        dest = chat_folder / f"image_{img_idx}{Path(file_path).suffix}"
        shutil.copy(file_path, dest)
        self.image_path = str(dest)
        html_img = f'<img src="{self.image_path}" width="300">'
        self._add_bubble("user", html_img)
        self.refresh_gallery()

    # ────────────────────────────────────────────────────────
    # Theme + chat management (unchanged vs previous)
    # -------------------------------------------------------

    def toggle_theme(self):
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.settings["theme"] = self.current_theme
        AppSettings.set_theme(self.current_theme.capitalize())  # ← добавили
        save_settings(self.settings)
        self.apply_theme()

    def apply_theme(self):
        qss_file = Path(__file__).parent / "themes" / ("dark.qss" if self.current_theme == "dark" else "light.qss")
        try:
            self.setStyleSheet(qss_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            log.warning("QSS not found: %s", qss_file)
            self.setStyleSheet("")

    # chat list helpers (same logic as before, omitted for brevity)
    def refresh_chat_list(self):
        self.chat_list_widget.clear(); chats = load_chats()
        for chat in chats:
            item = QListWidgetItem(chat["title"]); item.setData(Qt.UserRole, chat); self.chat_list_widget.addItem(item)
            if chat["file"] == self.current_chat["file"]: self.chat_list_widget.setCurrentItem(item)

    def handle_chat_selection(self, item: QListWidgetItem):
        self.switch_chat(item.data(Qt.UserRole))

    def create_and_switch_chat(self):
        new_chat = create_new_chat(); self.switch_chat(new_chat); self.refresh_chat_list()

    def switch_chat(self, chat: dict):
        self.current_chat = chat; set_current_chat(os.path.join("../chat_data", chat["file"]))
        self.chat_history = load_history();
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            item.widget().deleteLater()

        for m in self.chat_history:
            self._add_bubble(m["role"], m["content"])
        self.refresh_gallery()

    def _add_bubble(self, role: str, text: str, avatar_path: str | None = None):
        if avatar_path is None:
            avatar_path = USER_AVA if role == "user" else AI_AVA
        avatar = QPixmap(avatar_path) if avatar_path else None
        bubble = MessageBubble(text, role, avatar)

        # вставляем перед stretch‑заглушкой (‑1)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))
        return bubble

    # ────────────────────────────────────────────────────────
    # Plugin runner
    # -------------------------------------------------------

    def run_plugin(self, plugin):
        if not self.selected_gallery_image:
            QMessageBox.warning(self, "Нет изображения",
                                "Сначала выберите изображение в галерее.")
            return

        try:
            # ➊ Сперва спрашиваем параметры, если плагин их поддерживает
            kwargs = {}
            if hasattr(plugin, "configure"):
                cfg = plugin.configure(self, self.selected_gallery_image)
                if cfg is None:  # пользователь нажал Cancel
                    return
                kwargs.update(cfg)

            # ➋ Запускаем обработку
            new_path = plugin.process(self.selected_gallery_image, **kwargs)

            # ➌ Фиксируем результат
            append_message(self.chat_history, "assistant",
                           f"[{plugin.display_name} applied]", image=new_path)
            save_history(self.chat_history)
            self.refresh_gallery()

        except Exception as exc:
            QMessageBox.critical(self, "Plugin error", str(exc))


    def on_model_changed(self, name: str):
        set_current_model(name)

    # ────────────────────────────────────────────────────────
    # Settings dialog
    # -------------------------------------------------------
    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            # применяем изменившиеся настройки
            self.current_theme = AppSettings.theme().lower()
            self.apply_theme()

            # если пользователь сменил каталог chat_data,
            # перечитаем список диалогов
            self.refresh_chat_list()
            self.refresh_gallery()