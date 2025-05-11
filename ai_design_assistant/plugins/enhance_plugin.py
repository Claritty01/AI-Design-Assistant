from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
from PIL import Image
import torch
from torchvision.transforms.functional import to_tensor, to_pil_image



from ai_design_assistant.core.plugins import BaseImagePlugin
from .tools.SwinIR.models.network_swinir import SwinIR



class EnhancePlugin(BaseImagePlugin):
    display_name = "Улучшение качества"
    description = "Повышает чёткость изображения с помощью SwinIR."

    def run(self, image_path: str, **kwargs) -> str:
        src = Path(image_path)
        dst = src.with_stem(f"{src.stem}_enhanced").with_suffix(".png")

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Загрузка модели
        model = SwinIR(
            upscale=4,
            in_chans=3,
            img_size=64,
            window_size=8,
            img_range=1.0,
            depths=[6, 6, 6, 6, 6, 6],
            embed_dim=180,
            num_heads=[6, 6, 6, 6, 6, 6],
            mlp_ratio=2,
            upsampler="nearest+conv",
            resi_connection="1conv"
        )

        weights = Path("plugins/tools/SwinIR/003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x4_GAN.pth")
        state_dict = torch.load(weights, map_location=device)
        print("state_dict keys:", list(state_dict.keys()))

        model.load_state_dict(state_dict["params_ema"])

        model.eval().to(device)

        # Загрузка изображения
        with Image.open(src).convert("RGB") as img:
            lr_tensor = to_tensor(img).unsqueeze(0).to(device)

            with torch.no_grad():
                sr_tensor = model(lr_tensor)

            out_img = to_pil_image(sr_tensor.squeeze(0).clamp(0, 1).cpu())
            out_img.save(dst)

        return str(dst)

    def get_widget(self):
        return EnhanceWidget(self)


class EnhanceWidget(QWidget):
    def __init__(self, plugin: EnhancePlugin):
        super().__init__()
        self.plugin = plugin
        self.path: Path | None = None

        self.label = QLabel("Выберите изображение для улучшения:")
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_select = QPushButton("📂 Выбрать изображение")
        self.btn_select.clicked.connect(self._choose_image)

        self.btn_run = QPushButton("🚀 Улучшить")
        self.btn_run.clicked.connect(self._run)
        self.btn_run.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.preview)
        layout.addWidget(self.btn_select)
        layout.addWidget(self.btn_run)

    def _choose_image(self):
        file, _ = QFileDialog.getOpenFileName(self, "Выберите изображение", str(Path.home()), "Images (*.png *.jpg *.jpeg)")
        if file:
            self.path = Path(file)
            self.preview.setPixmap(QPixmap(file).scaledToWidth(300, Qt.TransformationMode.SmoothTransformation))
            self.btn_run.setEnabled(True)

    def _run(self):
        if not self.path:
            QMessageBox.warning(self, "Нет файла", "Сначала выберите изображение.")
            return
        try:
            result = self.plugin.run(str(self.path))
            QMessageBox.information(self, "Готово", f"Изображение сохранено: {result}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
