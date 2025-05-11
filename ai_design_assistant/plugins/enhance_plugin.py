from pathlib import Path
from PIL import Image
from realesrgan import RealESRGAN
import torch
import urllib.request

from ai_design_assistant.core.plugins import BaseImagePlugin

WEIGHTS_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4.pth"
WEIGHTS_PATH = Path(__file__).parent / "RealESRGAN_x4.pth"


class EnhancePlugin(BaseImagePlugin):
    display_name = "Улучшение качества"
    description = "Повышает чёткость изображения с помощью Real-ESRGAN."

    def run(self, image_path: str, **kwargs) -> str:
        if not WEIGHTS_PATH.exists():
            print("📦 Скачиваем веса Real-ESRGAN...")
            urllib.request.urlretrieve(WEIGHTS_URL, WEIGHTS_PATH)

        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model = RealESRGAN(device, scale=4)
        model.load_weights(str(WEIGHTS_PATH))

        img = Image.open(image_path).convert("RGB")
        sr_image = model.predict(img)
        out_path = Path(image_path).with_stem(Path(image_path).stem + "_enhanced").with_suffix(".png")
        sr_image.save(out_path)
        return str(out_path)

    def get_widget(self):
        return EnhanceWidget(self)


# ───────────────────────────── UI ───────────────────────────── #
from PyQt6.QtWidgets import (
    QWidget, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QMessageBox
)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import QSize, Qt


class EnhanceWidget(QWidget):
    THUMB_SIZE = QSize(80, 80)

    def __init__(self, plugin: EnhancePlugin):
        super().__init__()
        self.plugin = plugin
        self.selected_path: Path | None = None
        self.current_folder: Path | None = None

        self.title = QLabel("Выберите изображение для улучшения:")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gallery = QListWidget()
        self.gallery.setIconSize(self.THUMB_SIZE)
        self.gallery.itemClicked.connect(self._on_image_selected)

        self.preview = QLabel("Превью")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn = QPushButton("Улучшить качество")
        self.btn.clicked.connect(self._on_click)
        self.btn.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.gallery)
        layout.addWidget(self.preview, 1)
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
                icon = QIcon(QPixmap(str(path)).scaled(self.THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio))
                item = QListWidgetItem(icon, "")
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self.gallery.addItem(item)

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
            QMessageBox.warning(self, "Нет изображения", "Выберите изображение.")
            return
        try:
            out_path = self.plugin.run(str(self.selected_path))
            QMessageBox.information(self, "Готово", f"Файл сохранён: {out_path}")
            self._refresh_gallery()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка улучшения качества: {e}")
