"""Enhance plugin – full‑featured editor dialog."""

from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox, QListWidgetItem, \
    QListWidget
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QSize
from PIL import Image
import torch
from torchvision.transforms.functional import to_tensor, to_pil_image
from datetime import datetime


from ai_design_assistant.core.plugins import BaseImagePlugin
from .tools.SwinIR.models.network_swinir import SwinIR



class EnhancePlugin(BaseImagePlugin):
    display_name = "Улучшение качества"
    description = "Повышает чёткость изображения с помощью SwinIR."

    def run(self, image_path: str, **kwargs) -> str:
        src = Path(image_path)
        dst = src.with_stem(f"{src.stem}_enhanced").with_suffix(".png")

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        use_half = device.type == "cuda"

        model = SwinIR(
            upscale=2,
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

        # веса на 4x
        # weights = Path("plugins/tools/SwinIR/003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x4_GAN.pth")
        weights = Path("plugins/tools/SwinIR/003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x2_GAN.pth")
        state_dict = torch.load(weights, map_location=device)
        print("state_dict keys:", list(state_dict.keys()))

        if "params" in state_dict:
            model.load_state_dict(state_dict["params"], strict=True)
        else:
            model.load_state_dict(state_dict, strict=True)

        model.eval().to(device)

        with Image.open(src).convert("RGB") as img:
            lr_tensor = to_tensor(img).unsqueeze(0).to(device)

            with torch.no_grad():
                sr_tensor = model(lr_tensor)

            out_img = to_pil_image(sr_tensor.squeeze(0).clamp(0, 1).float().cpu())
            out_img.save(dst)

        return str(dst)

    def get_widget(self):
        return EnhanceWidget(self)


class EnhanceWidget(QWidget):
    THUMB_SIZE = QSize(80, 80)

    def __init__(self, plugin: EnhancePlugin):
        super().__init__()
        self.plugin = plugin
        self.current_folder: Path | None = None
        self.selected_path: Path | None = None
        self.last_result_path: Path | None = None

        self.label = QLabel("Выберите изображение для улучшения:")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gallery = QListWidget()
        self.gallery.setIconSize(self.THUMB_SIZE)
        self.gallery.setMinimumHeight(350)
        self.gallery.itemClicked.connect(self._on_image_selected)

        self.preview = QLabel("Превью")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_run = QPushButton("🚀 Улучшить")
        self.btn_run.clicked.connect(self._run)
        self.btn_run.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.gallery)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.btn_run)

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

        if self.last_result_path:
            self._highlight_item(self.last_result_path)

    def _on_image_selected(self, item: QListWidgetItem):
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        self.selected_path = path
        self._update_preview(path)
        self.btn_run.setEnabled(True)

    def _update_preview(self, path: Path):
        pixmap = QPixmap(str(path)).scaledToWidth(240, Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pixmap)
        self.label.setText(f"Выбрано: {path.name}")

    def _highlight_item(self, path: Path):
        for i in range(self.gallery.count()):
            item = self.gallery.item(i)
            if Path(item.data(Qt.ItemDataRole.UserRole)) == path:
                self.gallery.setCurrentItem(item)
                item.setSelected(True)
                self.gallery.scrollToItem(item)
                self._update_preview(path)
                self.selected_path = path
                self.btn_run.setEnabled(True)
                break

    def _run(self):
        if not self.selected_path:
            QMessageBox.warning(self, "Нет файла", "Сначала выберите изображение.")
            return
        try:
            result = self.plugin.run(str(self.selected_path))
            self.last_result_path = Path(result)  # ⬅ запоминаем
            QMessageBox.information(self, "Готово", f"Изображение сохранено: {result}")
            self._refresh_gallery()
            self.last_result_path = Path(result)  # запоминаем путь

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))


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

