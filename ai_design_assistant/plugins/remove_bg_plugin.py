from rembg import remove
from PIL import Image
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QMessageBox
from PyQt6.QtGui import QPixmap

from ai_design_assistant.core.plugins import BaseImagePlugin

class RemoveBGPlugin(BaseImagePlugin):
    display_name = "Удаление фона"
    description = "Удаляет фон с изображений"

    def __init__(self):
        super().__init__()
        self._widget = RemoveBGWidget()

    def run(self, **kwargs):
        self._widget.show()

    def get_widget(self) -> QWidget:
        return self._widget


class RemoveBGWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.image_label = QLabel("Нет изображения")
        self.image_label.setFixedHeight(200)
        self.image_label.setScaledContents(True)

        self.button = QPushButton("Удалить фон")
        self.button.clicked.connect(self._on_remove)

        self.layout().addWidget(self.image_label)
        self.layout().addWidget(self.button)

        self.current_path: Path | None = None

    def set_image(self, path: Path):
        self.current_path = path
        pixmap = QPixmap(str(path)).scaledToHeight(200)
        self.image_label.setPixmap(pixmap)

    def _on_remove(self):
        if not self.current_path:
            QMessageBox.warning(self, "Нет файла", "Выберите изображение в галерее.")
            return

        output_path = self.current_path.with_stem(f"{self.current_path.stem}_nobg").with_suffix(".png")
        with Image.open(self.current_path) as img:
            out = remove(img)
            out.save(output_path)

        QMessageBox.information(self, "Готово", f"Фон удалён: {output_path.name}")
        self.set_image(output_path)
