from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox, QListWidgetItem, \
    QListWidget, QProgressBar, QTabWidget
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QObject
from PIL import Image
import torch
from torchvision.transforms.functional import to_tensor, to_pil_image
from datetime import datetime

from ai_design_assistant.core.plugins import BaseImagePlugin
from .tools.SwinIR.models.network_swinir import SwinIR


# ─────────────────────────────────────────────────────────────────────────────
# WORKERS
# ─────────────────────────────────────────────────────────────────────────────

class SwinIRWorkerFull(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, image_path: str, model: torch.nn.Module):
        super().__init__()
        self.image_path = image_path
        self.model = model

    def run(self):
        import gc
        try:
            src = Path(self.image_path)
            dst = src.with_stem(f"{src.stem}_enhanced").with_suffix(".png")

            with Image.open(src).convert("RGB") as img:
                lr_tensor = to_tensor(img).unsqueeze(0).to(next(self.model.parameters()).device)

                with torch.no_grad():
                    sr_tensor = self.model(lr_tensor)

                out_img = to_pil_image(sr_tensor.squeeze(0).clamp(0, 1).float().cpu())
                out_img.save(dst)

            self.finished.emit(str(dst))
            del lr_tensor, sr_tensor, out_img
            torch.cuda.empty_cache()
            gc.collect()
        except Exception as e:
            self.error.emit(str(e))


class SwinIRWorkerTiled(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, image_path: str, model: torch.nn.Module, tile_size=256):
        super().__init__()
        self.image_path = image_path
        self.model = model
        self.tile_size = tile_size

    def run(self):
        import gc
        try:
            src = Path(self.image_path)
            dst = src.with_stem(f"{src.stem}_enhanced_tiled").with_suffix(".png")
            device = next(self.model.parameters()).device

            with Image.open(src).convert("RGB") as img:
                w, h = img.size
                tile = self.tile_size
                result = Image.new("RGB", (w * 2, h * 2))

                count_x = (w + tile - 1) // tile
                count_y = (h + tile - 1) // tile
                total = count_x * count_y
                done = 0

                for y in range(0, h, tile):
                    for x in range(0, w, tile):
                        crop = img.crop((x, y, x + tile, y + tile))
                        lr_tensor = to_tensor(crop).unsqueeze(0).to(device)

                        with torch.no_grad():
                            sr_tensor = self.model(lr_tensor)

                        sr_img = to_pil_image(sr_tensor.squeeze(0).clamp(0, 1).float().cpu())
                        result.paste(sr_img, (x * 2, y * 2))

                        done += 1
                        self.progress.emit(int(done / total * 100))

                result.save(dst)
                self.finished.emit(str(dst))

                del lr_tensor, sr_tensor, result
                torch.cuda.empty_cache()
                gc.collect()
        except Exception as e:
            self.error.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PLUGIN
# ─────────────────────────────────────────────────────────────────────────────

class EnhancePlugin(BaseImagePlugin):
    display_name = "Улучшение качества"
    description = "Повышает чёткость изображения с помощью SwinIR."

    def get_widget(self):
        return EnhanceTabs()


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────

class EnhanceTabs(QWidget):
    def __init__(self):
        super().__init__()
        self.model = self._init_model()
        self.tabs = QTabWidget()

        self.full = EnhanceSubWidget(self.model, tiled=False)
        self.tiled = EnhanceSubWidget(self.model, tiled=True)

        self.tabs.addTab(self.full, "Обычное улучшение")
        self.tabs.addTab(self.tiled, "Поштучное улучшение")

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

    def set_chat_folder(self, folder: str):
        self.full.set_chat_folder(folder)
        self.tiled.set_chat_folder(folder)

    def _init_model(self):
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
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
        weights = Path("plugins/tools/SwinIR/003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x2_GAN.pth")
        state_dict = torch.load(weights, map_location=device)
        model.load_state_dict(state_dict["params"] if "params" in state_dict else state_dict, strict=True)
        model.eval().to(device)
        return model


class EnhanceSubWidget(QWidget):
    THUMB_SIZE = QSize(80, 80)

    def __init__(self, model: torch.nn.Module, tiled: bool):
        super().__init__()
        self.model = model
        self.tiled = tiled
        self.selected_path: Path | None = None
        self.current_folder: Path | None = None
        self.thread: QThread | None = None
        self.worker: QObject | None = None

        self.label = QLabel("Выберите изображение:")
        self.gallery = QListWidget()
        self.gallery.setIconSize(self.THUMB_SIZE)
        self.gallery.itemClicked.connect(self._on_image_selected)

        self.preview = QLabel("Превью")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress = QProgressBar()
        self.progress.setVisible(False)

        self.btn_run = QPushButton("🚀 Улучшить")
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self._run)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.gallery)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.progress)
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
                item = QListWidgetItem(Path(path).name)
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                icon = QIcon(QPixmap(str(path)).scaled(
                    self.THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
                item.setIcon(icon)
                self.gallery.addItem(item)

    def _on_image_selected(self, item: QListWidgetItem):
        self.selected_path = Path(item.data(Qt.ItemDataRole.UserRole))
        pixmap = QPixmap(str(self.selected_path)).scaledToWidth(240, Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pixmap)
        self.label.setText(f"Выбрано: {self.selected_path.name}")
        self.btn_run.setEnabled(True)

    def _run(self):
        if not self.selected_path:
            return

        if self.thread and self.thread.isRunning():
            QMessageBox.warning(self, "Подождите", "Обработка ещё не завершена.")
            return

        self.btn_run.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.label.setText("Обработка...")

        self.thread = QThread(self)
        if self.tiled:
            self.worker = SwinIRWorkerTiled(str(self.selected_path), self.model, tile_size=256)
            self.worker.progress.connect(self.progress.setValue)
        else:
            self.worker = SwinIRWorkerFull(str(self.selected_path), self.model)

        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)

        # Сигналы результата
        self.worker.finished.connect(self._on_done)
        self.worker.error.connect(self._on_error)

        # Завершение потока безопасно
        self.worker.finished.connect(self._cleanup_thread)
        self.worker.error.connect(self._cleanup_thread)

        self.thread.start()

    def _on_done(self, result: str):
        QMessageBox.information(self, "Готово", f"Сохранено: {result}")
        self.progress.setVisible(False)
        self.label.setText("Готово!")
        self.btn_run.setEnabled(True)

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "Ошибка", msg)
        self.progress.setVisible(False)
        self.label.setText("Ошибка.")
        self.btn_run.setEnabled(True)

    def _cleanup_thread(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
            self.worker = None

