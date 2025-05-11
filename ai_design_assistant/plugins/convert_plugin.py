from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QComboBox, QHBoxLayout
)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import QSize, Qt
from PIL import Image
from datetime import datetime

from ai_design_assistant.core.plugins import BaseImagePlugin


class ConvertPlugin(BaseImagePlugin):
    display_name = "Конвертация форматов"
    description = "Конвертирует изображения в PNG, JPEG, BMP и др."

    def run(self, image_path: str, to_format: str = "png", **kwargs) -> str:
        src = Path(image_path)
        dst = src.with_stem(f"{src.stem}_converted").with_suffix(f".{to_format}")
        with Image.open(src) as img:
            rgb = img.convert("RGB")  # на всякий случай
            rgb.save(dst, format=to_format.upper())
        return str(dst)

    def get_widget(self) -> QWidget:
        from ai_design_assistant.ui.main_window import get_main_window
        main = get_main_window()
        if main and hasattr(main, "gallery_panel"):
            return ConvertWidget(self, gallery_refresh_callback=main.gallery_panel.refresh)
        return ConvertWidget(self)


class ConvertWidget(QWidget):
    THUMB_SIZE = QSize(80, 80)

    def __init__(self, plugin: ConvertPlugin, gallery_refresh_callback=None):
        super().__init__()
        self.plugin = plugin
        self.gallery_refresh_callback = gallery_refresh_callback
        self.current_folder: Path | None = None
        self.selected_path: Path | None = None
        self.last_result_path: Path | None = None

        self.title = QLabel("Выберите изображение для конвертации:")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gallery = QListWidget()
        self.gallery.setIconSize(self.THUMB_SIZE)
        self.gallery.setMinimumHeight(350)
        self.gallery.itemClicked.connect(self._on_image_selected)

        self.preview = QLabel("Превью")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.format_box = QComboBox()
        self.format_box.addItems(["png", "jpeg", "bmp", "webp"])

        self.btn = QPushButton("Конвертировать")
        self.btn.clicked.connect(self._on_click)
        self.btn.setEnabled(False)

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Формат:"))
        form_row.addWidget(self.format_box)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.gallery)
        layout.addWidget(self.preview, 1)
        layout.addLayout(form_row)
        layout.addWidget(self.btn)

    def set_chat_folder(self, folder_path: str):
        self.current_folder = Path(folder_path) / "images"
        self._refresh_gallery()

    def _refresh_gallery(self):
        self.gallery.clear()
        if not self.current_folder or not self.current_folder.exists():
            return

        for path in sorted(self.current_folder.glob("*")):
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                self._create_gallery_item(path)

    def _on_image_selected(self, item: QListWidgetItem):
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        self._update_preview(path)
        self.selected_path = path
        self.btn.setEnabled(True)

    def _update_preview(self, path: Path):
        pixmap = QPixmap(str(path)).scaledToWidth(240, Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pixmap)
        self.title.setText(f"Выбрано: {path.name}")

    def _highlight_item(self, path: Path):
        for i in range(self.gallery.count()):
            item = self.gallery.item(i)
            if Path(item.data(Qt.ItemDataRole.UserRole)) == path:
                self.gallery.setCurrentItem(item)
                item.setSelected(True)
                self.gallery.scrollToItem(item)
                self._update_preview(path)
                self.selected_path = path
                self.btn.setEnabled(True)
                break

    def _on_click(self):
        if not self.selected_path:
            QMessageBox.warning(self, "Нет изображения", "Выберите изображение в галерее.")
            return
        try:
            fmt = self.format_box.currentText()
            result = self.plugin.run(str(self.selected_path), to_format=fmt)
            self.last_result_path = Path(result)
            QMessageBox.information(self, "Готово", f"Изображение сохранено: {result}")
            self._refresh_gallery()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
        if self.gallery_refresh_callback:
            self.gallery_refresh_callback()

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