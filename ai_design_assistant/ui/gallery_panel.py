
from pathlib import Path
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox

class GalleryPanel(QWidget):
    THUMB_SIZE = QSize(80, 80)

    def __init__(self, get_current_chat_folder: callable, on_image_selected: callable, parent=None):
        super().__init__(parent)
        self.get_current_chat_folder = get_current_chat_folder
        self.on_image_selected = on_image_selected
        self.selected_path: str | None = None

        self.gallery = QListWidget()
        self.gallery.setIconSize(self.THUMB_SIZE)
        self.gallery.itemClicked.connect(self.select_image)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("🖼️ Галерея"))
        layout.addWidget(self.gallery, 1)
        self.setLayout(layout)

    def refresh(self):
        self.gallery.clear()
        folder = self.get_current_chat_folder()
        if not folder or not Path(folder).exists():
            return
        exts = ('.png', '.jpg', '.jpeg', '.bmp')
        for path in sorted(Path(folder).glob("*")):
            if path.suffix.lower() in exts:
                icon = QIcon(QPixmap(str(path)).scaled(self.THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio))
                item = QListWidgetItem(icon, "")
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self.gallery.addItem(item)

    def select_image(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        self.selected_path = path
        self.on_image_selected(path)

    def get_selected_image(self) -> str | None:
        if not self.selected_path:
            QMessageBox.warning(self, "Нет изображения", "Сначала выберите изображение в галерее.")
            return None
        return self.selected_path


