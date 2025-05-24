"""Background remove plugin – full‑featured editor dialog."""

from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QApplication
)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from rembg import remove
from PIL import Image
from datetime import datetime

from ai_design_assistant.core.plugins import BaseImagePlugin
from ai_design_assistant.ui.main_window import get_main_window

class RemoveBGPlugin(BaseImagePlugin):
    name = "remove_background"
    description = "Удаляет фон с изображения при помощи rembg."
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Путь к изображению"
            }
        },
        "required": ["image_path"]
    }

    display_name = "Удаление фона"

    def run(self, image_path: str, **kwargs):
        src = Path(image_path)
        dst = src.with_stem(f"{src.stem}_nobg").with_suffix(".png")
        with Image.open(src) as img:
            result = remove(img)
            result.save(dst)
        return str(dst)

    def get_widget(self) -> QWidget:
        from ai_design_assistant.ui.main_window import get_main_window
        main = get_main_window()
        if main and hasattr(main, "gallery_panel"):
            return RemoveBGWidget(self, gallery_refresh_callback=main.gallery_panel.refresh)
        return RemoveBGWidget(self)


class RemoveBGWidget(QWidget):
    THUMB_SIZE = QSize(80, 80)
    background_removed = pyqtSignal(str)  # путь к новому изображению

    def __init__(self, plugin: RemoveBGPlugin, gallery_refresh_callback=None):  # ← gallery_refresh_callback здесь
        super().__init__()
        self.plugin = plugin
        self.gallery_refresh_callback = gallery_refresh_callback
        self.selected_path: Path | None = None
        self.current_folder: Path | None = None

        self.title = QLabel("Выберите изображение для удаления фона:")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gallery = QListWidget()
        self.gallery.setIconSize(self.THUMB_SIZE)
        self.gallery.setMinimumHeight(350)
        self.gallery.itemClicked.connect(self._on_image_selected)

        self.preview = QLabel("Превью")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn = QPushButton("Удалить фон")
        self.btn.clicked.connect(self._on_click)
        self.btn.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.gallery)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.btn)

    def set_image(self, image_path: str):
        """Поддержка внешней галереи — необязательно, но можно."""
        self._update_preview(Path(image_path))
        self.selected_path = Path(image_path)
        self.btn.setEnabled(True)

    def _on_image_selected(self, item: QListWidgetItem):
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        self._update_preview(path)
        self.selected_path = path
        self.btn.setEnabled(True)

    def _update_preview(self, path: Path):
        pixmap = QPixmap(str(path)).scaledToWidth(240, Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pixmap)
        self.title.setText(f"Выбрано: {path.name}")

    def _on_click(self):
        if not self.selected_path:
            QMessageBox.warning(self, "Нет изображения", "Выберите изображение в галерее.")
            return
        try:
            result_path = self.plugin.run(image_path=str(self.selected_path))
            QMessageBox.information(self, "Готово", f"Фон удалён: {result_path}")
            self._refresh_gallery()
            self._highlight_item(Path(result_path))

            if self.gallery_refresh_callback:
                self.gallery_refresh_callback()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка удаления фона: {e}")

    def set_chat_folder(self, folder_path: str):
        """Вызывается из MainWindow при активации сессии."""
        self.current_folder = Path(folder_path) / "images"
        self._refresh_gallery()

    def _refresh_gallery(self):
        self.gallery.clear()
        if not self.current_folder or not self.current_folder.exists():
            return

        for path in sorted(self.current_folder.glob("*")):
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                self._create_gallery_item(path)

    def _highlight_item(self, path: Path):
        """Находит и выделяет элемент галереи по пути и показывает его превью."""
        for i in range(self.gallery.count()):
            item = self.gallery.item(i)
            if Path(item.data(Qt.ItemDataRole.UserRole)) == path:
                self.gallery.setCurrentItem(item)
                item.setSelected(True)
                self.gallery.scrollToItem(item)
                self._update_preview(path)  # Показываем превью
                self.selected_path = path
                self.btn.setEnabled(True)
                break

    def _create_gallery_item(self, path: Path) -> QListWidgetItem:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 0, 4, 0)

        name_label = QLabel(path.name)
        name_label.setStyleSheet("font-weight: bold;")

        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        now = datetime.now()
        subtitle = mtime.strftime("%H:%M") if mtime.date() == now.date() else mtime.strftime("%d.%m.%Y")

        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet("color: gray; font-size: 10px;")

        layout.addWidget(name_label)
        layout.addWidget(subtitle_label)

        icon = QIcon(QPixmap(str(path)).scaled(
            self.THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

        item = QListWidgetItem()
        item.setSizeHint(widget.sizeHint())
        item.setSizeHint(QSize(100, 80))
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setIcon(icon)

        self.gallery.addItem(item)
        self.gallery.setItemWidget(item, widget)

        return item
