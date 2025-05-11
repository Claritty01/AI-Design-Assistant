from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox
)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import QSize, Qt
from rembg import remove
from PIL import Image

from ai_design_assistant.core.plugins import BaseImagePlugin

class RemoveBGPlugin(BaseImagePlugin):
    display_name = "Удаление фона"
    description = "Удаляет фон с изображения при помощи rembg."

    def run(self, image_path: str, **kwargs):
        src = Path(image_path)
        dst = src.with_stem(f"{src.stem}_nobg").with_suffix(".png")
        with Image.open(src) as img:
            result = remove(img)
            result.save(dst)
        return str(dst)

    def get_widget(self) -> QWidget:
        return RemoveBGWidget(self)


class RemoveBGWidget(QWidget):
    THUMB_SIZE = QSize(80, 80)

    def __init__(self, plugin: RemoveBGPlugin):
        super().__init__()
        self.plugin = plugin
        self.selected_path: Path | None = None
        self.current_folder: Path | None = None

        self.title = QLabel("Выберите изображение для удаления фона:")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gallery = QListWidget()
        self.gallery.setIconSize(self.THUMB_SIZE)
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
                icon = QIcon(QPixmap(str(path)).scaled(self.THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio))
                item = QListWidgetItem(icon, "")
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self.gallery.addItem(item)
