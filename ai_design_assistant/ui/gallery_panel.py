import shutil
from pathlib import Path
from datetime import datetime
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QHBoxLayout, QPushButton, QFileDialog
)


class GalleryPanel(QWidget):
    THUMB_SIZE = QSize(80, 80)

    def __init__(self, get_current_chat_folder: callable, on_image_selected: callable, parent=None):
        super().__init__(parent)
        self.get_current_chat_folder = get_current_chat_folder
        self.on_image_selected = on_image_selected
        self.selected_path: str | None = None

        self.gallery = QListWidget()
        self.gallery.setIconSize(self.THUMB_SIZE)
        self.gallery.setMinimumHeight(350)
        self.gallery.itemClicked.connect(self.select_image)

        self.add_button = QPushButton("➕ Добавить изображение")
        self.add_button.clicked.connect(self._on_add_image)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("🖼️ Галерея"))
        layout.addWidget(self.add_button)
        layout.addWidget(self.gallery, 1)
        self.setLayout(layout)

    def _on_add_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите изображение", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return

        dst_folder = Path(self.get_current_chat_folder()) / "images"
        dst_folder.mkdir(parents=True, exist_ok=True)
        dst_path = dst_folder / Path(path).name

        if dst_path.exists():
            QMessageBox.warning(self, "Файл уже существует", f"Файл {dst_path.name} уже есть в галерее.")
            return

        shutil.copy(path, dst_path)
        self.refresh()

    def refresh(self):
        self.gallery.clear()
        folder = Path(self.get_current_chat_folder()).resolve() / "images"
        if not folder.exists():
            return

        for path in sorted(folder.glob("*")):
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                self._add_image_item(path)

    def _add_image_item(self, path: Path):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 0, 4, 0)

        # Название файла
        name_label = QLabel(path.name)
        name_label.setStyleSheet("font-weight: bold;")

        # Время / дата
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
        item.setSizeHint(QSize(100, 80))
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setIcon(icon)

        self.gallery.addItem(item)
        self.gallery.setItemWidget(item, widget)

    def select_image(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        self.selected_path = path
        self.on_image_selected(path)

    def get_selected_image(self) -> str | None:
        if not self.selected_path:
            QMessageBox.warning(self, "Нет изображения", "Сначала выберите изображение в галерее.")
            return None
        return self.selected_path
