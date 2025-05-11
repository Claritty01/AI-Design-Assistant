from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QSlider
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
from PIL import Image

from ai_design_assistant.core.plugins import BaseImagePlugin


class CompressPlugin(BaseImagePlugin):
    display_name = "Сжатие изображения"
    description = "Сжимает изображение (JPEG: по quality, PNG: по compress_level)."

    def run(self, image_path: str, quality: int = 85, **kwargs) -> str:
        src = Path(image_path)
        suffix = src.suffix.lower()

        dst = src.with_stem(f"{src.stem}_compressed")
        if suffix in [".jpg", ".jpeg"]:
            dst = dst.with_suffix(".jpg")
        elif suffix == ".png":
            dst = dst.with_suffix(".png")
        else:
            raise ValueError("Поддерживаются только PNG и JPEG")

        with Image.open(src) as img:
            if suffix in [".jpg", ".jpeg"]:
                img = img.convert("RGB")
                img.save(dst, format="JPEG", quality=quality, optimize=True)
            elif suffix == ".png":
                compress_level = self._map_quality_to_png_level(quality)
                img.save(dst, format="PNG", compress_level=compress_level, optimize=True)

        return str(dst)

    @staticmethod
    def _map_quality_to_png_level(quality: int) -> int:
        # 0 (без сжатия) ... 9 (максимальное сжатие)
        return round((100 - quality) / 10)

    def get_widget(self):
        return CompressWidget(self)


class CompressWidget(QWidget):
    def __init__(self, plugin: CompressPlugin):
        super().__init__()
        self.plugin = plugin
        self.path: Path | None = None
        self.quality = 85

        self.label = QLabel("Выберите изображение для сжатия:")
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(10)
        self.slider.setMaximum(100)
        self.slider.setValue(85)
        self.slider.valueChanged.connect(self._on_slider_changed)

        self.slider_label = QLabel("Качество: 85")

        self.btn_select = QPushButton("📂 Выбрать изображение")
        self.btn_select.clicked.connect(self._choose_image)

        self.btn_run = QPushButton("🗜 Сжать")
        self.btn_run.clicked.connect(self._run)
        self.btn_run.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.preview)
        layout.addWidget(self.slider_label)
        layout.addWidget(self.slider)
        layout.addWidget(self.btn_select)
        layout.addWidget(self.btn_run)

    def _on_slider_changed(self, value: int):
        self.quality = value
        self.slider_label.setText(f"Качество: {value}")

    def _choose_image(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", str(Path.home()), "Images (*.png *.jpg *.jpeg)"
        )
        if file:
            self.path = Path(file)
            self.preview.setPixmap(QPixmap(file).scaledToWidth(300, Qt.TransformationMode.SmoothTransformation))
            self.btn_run.setEnabled(True)

    def _run(self):
        if not self.path:
            QMessageBox.warning(self, "Нет файла", "Сначала выберите изображение.")
            return
        try:
            result = self.plugin.run(str(self.path), quality=self.quality)
            QMessageBox.information(self, "Готово", f"Изображение сохранено: {result}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
