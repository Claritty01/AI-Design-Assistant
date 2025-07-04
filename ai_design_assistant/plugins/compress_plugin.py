"""Compress plugin – full‑featured editor dialog."""

from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QSlider, QHBoxLayout
)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import QSize, Qt
from datetime import datetime
from PIL import Image

from ai_design_assistant.core.plugins import BaseImagePlugin


class CompressPlugin(BaseImagePlugin):
    name = "compress_image"
    display_name = "Сжатие изображения"
    description = "Сжимает изображение с заданным уровнем качества (JPEG)."
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Путь к изображению"
            },
            "quality": {
                "type": "integer",
                "description": "Качество JPEG (0–100)",
                "minimum": 1,
                "maximum": 100
            }
        },
        "required": ["image_path", "quality"]
    }

    def run(self, image_path: str, **kwargs) -> str:
        src = Path(image_path)
        dst = src.with_stem(f"{src.stem}_compressed").with_suffix(src.suffix)

        with Image.open(src) as img:
            if src.suffix.lower() in {".jpg", ".jpeg"}:
                img.save(dst, "JPEG", quality=kwargs.get("quality", 60), optimize=True)
            elif src.suffix.lower() == ".png":
                img.save(dst, "PNG", compress_level=kwargs.get("compress_level", 9), optimize=True)
            else:
                raise ValueError("Неподдерживаемый формат изображения")

        return str(dst)

    def get_widget(self):
        return CompressWidget(self)


class CompressWidget(QWidget):
    THUMB_SIZE = QSize(80, 80)

    def __init__(self, plugin: CompressPlugin):
        super().__init__()
        self.plugin = plugin
        self.selected_path: Path | None = None
        self.current_folder: Path | None = None

        # Основные элементы
        self.title = QLabel("Выберите изображение для сжатия:")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gallery = QListWidget()
        self.gallery.setIconSize(self.THUMB_SIZE)
        self.gallery.setMinimumHeight(350)
        self.gallery.itemClicked.connect(self._on_image_selected)

        self.preview = QLabel("Превью")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Ползунок
        self.slider_label = QLabel("JPEG Quality: 60")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 100)
        self.slider.setValue(60)
        self.slider.valueChanged.connect(self._on_slider_changed)

        self.btn = QPushButton("Сжать изображение")
        self.btn.clicked.connect(self._on_click)
        self.btn.setEnabled(False)

        # Layout
        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.gallery)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.slider_label)
        layout.addWidget(self.slider)
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

        ext = path.suffix.lower()
        if ext in {".jpg", ".jpeg"}:
            self.slider.setRange(1, 100)
            self.slider.setValue(60)
            self.slider_label.setText(f"JPEG Quality: 60")
        elif ext == ".png":
            self.slider.setRange(0, 9)
            self.slider.setValue(6)
            self.slider_label.setText(f"PNG Compress Level: 6")

    def _update_preview(self, path: Path):
        pixmap = QPixmap(str(path)).scaledToWidth(240, Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pixmap)
        self.title.setText(f"Выбрано: {path.name}")

    def _on_slider_changed(self, value: int):
        if not self.selected_path:
            return

        ext = self.selected_path.suffix.lower()
        if ext in {".jpg", ".jpeg"}:
            self.slider_label.setText(f"JPEG Quality: {value}")
        elif ext == ".png":
            self.slider_label.setText(f"PNG Compress Level: {value}")

    def _on_click(self):
        if not self.selected_path:
            QMessageBox.warning(self, "Нет изображения", "Выберите изображение в галерее.")
            return
        try:
            ext = self.selected_path.suffix.lower()
            val = self.slider.value()
            kwargs = {}
            if ext in {".jpg", ".jpeg"}:
                kwargs["quality"] = val
            elif ext == ".png":
                kwargs["compress_level"] = min(val // 10, 9)

            result_path = self.plugin.run(str(self.selected_path), **kwargs)
            QMessageBox.information(self, "Готово", f"Сжато: {result_path}")
            self._refresh_gallery()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка сжатия: {e}")

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