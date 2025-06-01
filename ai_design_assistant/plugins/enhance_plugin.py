from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox, QListWidgetItem, \
    QListWidget, QProgressBar, QTabWidget, QComboBox
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QObject
from PIL import Image
import torch
from torchvision.transforms.functional import to_tensor, to_pil_image
from datetime import datetime

from ai_design_assistant.core.plugins import BaseImagePlugin

import logging, warnings

# -----------------------------------------------------------------------------
# ЛОГИ И ПРЕДУПРЕЖДЕНИЯ
# -----------------------------------------------------------------------------
_LOGGER = logging.getLogger(__name__)

# timm > 0.9 переехал; глушим FutureWarning “please import via timm.layers”
warnings.filterwarnings("ignore",
                        category=FutureWarning,
                        module=r"timm\.models\.layers")

# Torch 2.3 ругается, что скоро meshgrid потребует indexing='ij'
warnings.filterwarnings("ignore",
                        category=UserWarning,
                        message=r"torch\.meshgrid")


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
    name = "enhance_image"
    display_name = "Улучшение качества"
    description = "Улучшает изображение с помощью SwinIR. Поддерживаются режимы: Быстрая, Стандартная, Глубокая."
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Путь к изображению"
            },
            "mode": {
                "type": "string",
                "enum": ["Быстрая", "Стандартная", "Глубокая"],
                "description": "Режим улучшения"
            }
        },
        "required": ["image_path", "mode"]
    }

    def get_widget(self):
        return EnhanceTabs()


# -----------------------------------------------------------------------------
# LAZY-LOADER ДЛЯ SWINIR
# -----------------------------------------------------------------------------
_MODEL_CACHE: dict[str, torch.nn.Module] = {}

def get_swinir(level: str) -> torch.nn.Module:
    """
    Возвращает готовую к инференсу модель SwinIR.
    Повторные вызовы отдают кэш — веса грузятся один раз за сессию.
    """
    if level in _MODEL_CACHE:
        return _MODEL_CACHE[level]

    from .tools.SwinIR.models.network_swinir import SwinIR  # импорт внутри функции
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if level == "Быстрая":
        from .tools.SwinIR.models.network_swinir import SwinIR
        model = SwinIR(
            upscale=2,
            in_chans=3,
            img_size=64,
            window_size=8,
            img_range=1.0,
            # depths=[6, 6, 6, 6],
            depths=[6, 6, 6, 6, 6, 6],
            embed_dim=180,
            # embed_dim=60,
            # num_heads=[6, 6, 6, 6],
            num_heads=[6, 6, 6, 6, 6, 6],
            mlp_ratio=2,
            # upsampler="pixelshuffledirect",
            upsampler="nearest+conv",
            resi_connection="1conv"
        )
        # weights = Path("plugins/tools/SwinIR/003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x2_GAN.pth")
        weights = Path("plugins/tools/SwinIR/003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x2_GAN.pth")

    elif level == "Глубокая":
        from .tools.SwinIR.models.network_swinir import SwinIR
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

    else:  # Стандартная
        from .tools.SwinIR.models.network_swinir import SwinIR
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
            # upsampler="pixelshuffle",
            resi_connection="1conv"
        )
        # weights = Path("plugins/tools/SwinIR/001_classicalSR_DF2K_s64w8_SwinIR-M_x2.pth")
        weights = Path("plugins/tools/SwinIR/003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x2_GAN.pth")

    state = torch.load(weights, map_location=device)
    model.load_state_dict(state["params"] if "params" in state else state, strict=True)
    model.eval().to(device)

    _LOGGER.info("[%s] Загружено параметров: %.2f M", level,
                 sum(p.numel() for p in model.parameters()) / 1e6)

    _MODEL_CACHE[level] = model            # кладём в кэш
    return model



# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────

# ────────── EnhanceTabs ──────────
class EnhanceTabs(QWidget):
    def __init__(self):
        super().__init__()

        self.combo = QComboBox()
        self.combo.addItems(["Быстрая", "Стандартная", "Глубокая"])
        self.combo.currentIndexChanged.connect(self._reload_model)

        self.model = None  # ← пока модели нет

        self.full  = EnhanceSubWidget(self, tiled=False)
        self.tiled = EnhanceSubWidget(self, tiled=True)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.full,  "Обычное улучшение")
        self.tabs.addTab(self.tiled, "Поштучное улучшение")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Выберите качество модели:"))
        layout.addWidget(self.combo)
        layout.addWidget(self.tabs)

    def _reload_model(self):
        self.model = None  # сбрасываем модель — при следующем запуске подгрузится свежая

    def set_chat_folder(self, folder: str):
        self.full.set_chat_folder(folder)
        self.tiled.set_chat_folder(folder)

    def get_model(self):
        if self.model is None:
            level = self.combo.currentText()
            self.model = get_swinir(level)
        return self.model


class EnhanceSubWidget(QWidget):
    THUMB_SIZE = QSize(80, 80)

    def __init__(self, parent: EnhanceTabs, tiled: bool):
        super().__init__()
        self.parent = parent
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
        model = self.parent.get_model()
        if self.tiled:
            self.worker = SwinIRWorkerTiled(str(self.selected_path), model, tile_size=256)
        else:
            self.worker = SwinIRWorkerFull(str(self.selected_path), model)

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

    # ────────── EnhanceSubWidget._on_error ──────────
    def _on_error(self, msg: str) -> None:
        _LOGGER.error("Ошибка в потоке: %s", msg)
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

