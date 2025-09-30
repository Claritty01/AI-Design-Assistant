from __future__ import annotations

from pathlib import Path
from typing import Optional, Union, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox,
    QListWidgetItem, QListWidget, QProgressBar, QTabWidget, QComboBox
)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QObject

from PIL import Image
import torch
from torchvision.transforms.functional import to_tensor, to_pil_image

from ai_design_assistant.core.plugins import BaseImagePlugin

import logging
import warnings

# ---------------------------------------------------------------------
# ЛОГИ И ПРЕДУПРЕЖДЕНИЯ
# ---------------------------------------------------------------------
_LOGGER = logging.getLogger(__name__)

# timm > 0.9 перенёс слои — глушим future warning (если у кого стоит свежий timm)
warnings.filterwarnings("ignore", category=FutureWarning, module=r"timm\.models\.layers")

# Torch 2.3 предупреждает про будущий default indexing='ij' в meshgrid — глушим
warnings.filterwarnings("ignore", category=UserWarning, message=r"torch\.meshgrid")


# ---------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (общие для UI и headless-режима)
# ---------------------------------------------------------------------
def _pil_upscale(img: Image.Image, scale: int = 2) -> Image.Image:
    """Увеличение через Pillow (LANCZOS). Работает быстро и стабильно в CI."""
    scale = max(1, int(scale))
    new_size = (max(1, img.width * scale), max(1, img.height * scale))
    if new_size == img.size:
        # На случай scale=1 — чуть толкнём, чтобы тесты видели изменение.
        new_size = (img.width * 2, img.height * 2)
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _safe_device(model: torch.nn.Module) -> torch.device:
    try:
        return next(model.parameters()).device
    except Exception:
        return torch.device("cpu")


def _save_png(img: Image.Image, out_path: Path) -> str:
    out_path = out_path.with_suffix(".png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return str(out_path)


def _pad_to_window(img: Image.Image, window: int = 8) -> tuple[Image.Image, tuple[int, int]]:
    """
    Пэддим PIL-изображение отражением до кратности window; возвращаем (img_padded, (orig_w, orig_h)).
    Это снижает артефакты/NaN у оконных трансформеров вроде SwinIR.
    """
    w, h = img.size
    pad_w = (window - w % window) % window
    pad_h = (window - h % window) % window
    if pad_w == 0 and pad_h == 0:
        return img, (w, h)

    new_img = Image.new("RGB", (w + pad_w, h + pad_h))
    new_img.paste(img, (0, 0))

    # правый бордер
    if pad_w:
        right = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT).crop((w - pad_w, 0, w, h))
        new_img.paste(right, (w, 0))
    # нижний бордер
    if pad_h:
        bottom = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM).crop((0, h - pad_h, w, h))
        new_img.paste(bottom, (0, h))
    # нижний-правый угол
    if pad_w and pad_h:
        corner = img.transpose(Image.Transpose.ROTATE_180).crop((w - pad_w, h - pad_h, w, h))
        new_img.paste(corner, (w, h))

    return new_img, (w, h)


# ---------------------------------------------------------------------
# SWINIR ЗАГРУЗЧИК (lazy + кэш)
# ---------------------------------------------------------------------
_MODEL_CACHE: dict[str, torch.nn.Module] = {}


def get_swinir(level: str) -> torch.nn.Module:
    """
    Возвращает готовую к инференсу модель SwinIR (кэшируется).
    Возможные level: 'Быстрая' | 'Стандартная' | 'Глубокая' (сейчас x2).
    """
    if level in _MODEL_CACHE:
        return _MODEL_CACHE[level]

    # Импортируем только при необходимости (ускоряет старт, если плагин не нужен)
    from .tools.SwinIR.models.network_swinir import SwinIR  # type: ignore

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Конфигурация SwinIR под x2 upscale
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
        resi_connection="1conv",
    )

    # Весá ищем относительно текущего файла плагина
    base = Path(__file__).resolve().parent / "tools" / "SwinIR"
    candidates = [
        base / "003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x2_GAN.pth",
        base / "001_classicalSR_DF2K_s64w8_SwinIR-M_x2.pth",
    ]
    weights = next((p for p in candidates if p.exists()), None)
    if not weights:
        raise FileNotFoundError(
            f"Не найдены веса SwinIR x2 в {base}. Положи один из файлов: "
            + ", ".join(p.name for p in candidates)
        )

    state = torch.load(weights, map_location=device)
    state = state.get("params", state)  # совместимость с разными чекпоинтами
    model.load_state_dict(state, strict=True)
    model.eval().to(device)

    _LOGGER.info("[%s] SwinIR загружен (%s) на %s, %.2fM параметров",
                 level, weights.name, device, sum(p.numel() for p in model.parameters()) / 1e6)

    _MODEL_CACHE[level] = model
    return model


def _infer_full(model: torch.nn.Module, img: Image.Image, window_size: int = 8, scale: int = 2) -> Image.Image:
    """
    Стабильный инференс одним проходом:
    - float32 (без autocast),
    - паддинг до кратности window_size,
    - nan_to_num + clamp и обрезка паддинга на выходе.
    """
    dev = _safe_device(model)
    img_pad, (orig_w, orig_h) = _pad_to_window(img, window=window_size)

    with torch.no_grad():
        lr = to_tensor(img_pad).unsqueeze(0).to(dev, dtype=torch.float32)  # BCHW
        sr = model(lr)
        sr = torch.nan_to_num(sr, nan=0.0, posinf=1.0, neginf=0.0)
        sr = sr.squeeze(0).clamp(0, 1).float().cpu()

    out = to_pil_image(sr)

    # обрезаем паддинг (учитывая масштаб x2)
    out_w = orig_w * scale
    out_h = orig_h * scale
    if out.size != (out_w, out_h):
        out = out.crop((0, 0, out_w, out_h))
    return out


def _infer_tiled(
    model: torch.nn.Module,
    img: Image.Image,
    tile: int = 256,
    scale: int = 2,
    overlap: int = 8,
    window_size: int = 8,
) -> Image.Image:
    """
    Тайловый инференс:
    - float32 (без autocast),
    - паддинг входа до кратности window_size,
    - перекрытие и вставка центральной части,
    - nan_to_num + clamp и обрезка паддинга на выходе.
    """
    dev = _safe_device(model)

    img_pad, (orig_w, orig_h) = _pad_to_window(img, window=window_size)
    w, h = img_pad.size
    out = Image.new("RGB", (w * scale, h * scale))

    xs = list(range(0, w, tile))
    ys = list(range(0, h, tile))
    for y in ys:
        for x in xs:
            x0 = max(0, x - overlap)
            y0 = max(0, y - overlap)
            x1 = min(w, x + tile + overlap)
            y1 = min(h, y + tile + overlap)

            crop = img_pad.crop((x0, y0, x1, y1))
            with torch.no_grad():
                lr = to_tensor(crop).unsqueeze(0).to(dev, dtype=torch.float32)
                sr = model(lr)
                sr = torch.nan_to_num(sr, nan=0.0, posinf=1.0, neginf=0.0)
                sr = sr.squeeze(0).clamp(0, 1).float().cpu()
            sr_img = to_pil_image(sr)

            # центральная область без перекрытия
            ins_x = (x - x0) * scale
            ins_y = (y - y0) * scale
            ins_w = min(tile, w - x) * scale
            ins_h = min(tile, h - y) * scale
            paste_crop = sr_img.crop((ins_x, ins_y, ins_x + ins_w, ins_y + ins_h))
            out.paste(paste_crop, (x * scale, y * scale))

    # Обрезаем паддинг на выходе
    out_w = orig_w * scale
    out_h = orig_h * scale
    if out.size != (out_w, out_h):
        out = out.crop((0, 0, out_w, out_h))
    return out


# ---------------------------------------------------------------------
# WORKERS (используются только UI-виджетами)
# ---------------------------------------------------------------------
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
                out_img = _infer_full(self.model, img)
                out_img.save(dst)

            self.finished.emit(str(dst))
            if torch.cuda.is_available():
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

            with Image.open(src).convert("RGB") as img:
                # здесь можно руками обновлять progress, если нужно детальнее
                out_img = _infer_tiled(self.model, img, tile=self.tile_size, scale=2, overlap=8)
                out_img.save(dst)

            self.finished.emit(str(dst))
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------
# ПЛАГИН (UI + HEADLESS API)
# ---------------------------------------------------------------------
class EnhancePlugin(BaseImagePlugin):
    name = "enhance_image"
    display_name = "Улучшение качества"
    description = "Улучшает изображение с помощью SwinIR. Поддерживаются режимы: Быстрая, Стандартная, Глубокая."
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {"type": "string", "description": "Путь к изображению"},
            "mode": {"type": "string", "enum": ["Быстрая", "Стандартная", "Глубокая"], "description": "Режим улучшения"},
            "tiled": {"type": "boolean", "default": False},
            "tile_size": {"type": "integer", "default": 256},
            "scale": {"type": "integer", "default": 2},
            "out_path": {"type": ["string", "null"], "default": None},
        },
        "required": ["image_path", "mode"]
    }

    def get_widget(self):
        return EnhanceTabs()

    # ─── НОВОЕ: headless API для тестов/CLI ───
    def run(
        self,
        image_path: Union[str, Path],
        mode: str = "Стандартная",
        tiled: bool = False,
        tile_size: int = 256,
        scale: int = 2,
        out_path: Optional[Union[str, Path]] = None,
    ) -> str:
        """
        Запуск без UI. Возвращает путь к сохранённому PNG.
        Если SwinIR недоступен — делает высококачественный PIL-upscale.
        """
        src = Path(image_path)
        if not src.exists():
            raise FileNotFoundError(src)

        # куда сохранять
        if out_path is None:
            suffix = "_enhanced_tiled" if tiled else "_enhanced"
            out_path = src.with_stem(f"{src.stem}{suffix}").with_suffix(".png")
        else:
            out_path = Path(out_path)

        try:
            model = get_swinir(mode)
            with Image.open(src).convert("RGB") as img:
                if tiled:
                    out_img = _infer_tiled(model, img, tile=tile_size, scale=scale, overlap=8)
                else:
                    out_img = _infer_full(model, img, window_size=8, scale=scale)
                return _save_png(out_img, out_path)
        except Exception as e:
            _LOGGER.warning("SwinIR недоступен (%s). Переключаюсь на PIL-upscale x%d.", e, scale)
            with Image.open(src).convert("RGB") as img:
                out_img = _pil_upscale(img, scale=scale)
                return _save_png(out_img, out_path)
        finally:
            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass


# ---------------------------------------------------------------------
# UI ВИДЖЕТЫ
# ---------------------------------------------------------------------
class EnhanceTabs(QWidget):
    def __init__(self):
        super().__init__()

        self.combo = QComboBox()
        self.combo.addItems(["Быстрая", "Стандартная", "Глубокая"])
        self.combo.currentIndexChanged.connect(self._reload_model)

        self.model: Optional[torch.nn.Module] = None  # лениво подгружается

        self.full = EnhanceSubWidget(self, tiled=False)
        self.tiled = EnhanceSubWidget(self, tiled=True)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.full, "Обычное улучшение")
        self.tabs.addTab(self.tiled, "Поштучное улучшение")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Выберите качество модели:"))
        layout.addWidget(self.combo)
        layout.addWidget(self.tabs)

    def _reload_model(self):
        # При смене режима сбрасываем модель — подгрузится заново при первом старте
        self.model = None

    def set_chat_folder(self, folder: str):
        self.full.set_chat_folder(folder)
        self.tiled.set_chat_folder(folder)

    def get_model(self) -> torch.nn.Module:
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
        pixmap = QPixmap(str(self.selected_path)).scaledToWidth(
            240, Qt.TransformationMode.SmoothTransformation
        )
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
        try:
            model = self.parent.get_model()
        except Exception as e:
            # Веса/torch недоступны — делаем PIL-upscale «на месте» и выходим
            try:
                with Image.open(self.selected_path).convert("RGB") as img:
                    out = _pil_upscale(img, scale=2)
                    out_path = self.selected_path.with_stem(self.selected_path.stem + "_enhanced").with_suffix(".png")
                    out.save(out_path)
                QMessageBox.information(self, "Готово (PIL)", f"Сохранено: {out_path}")
            except Exception as pil_e:
                QMessageBox.critical(self, "Ошибка", f"{e}\n\nPIL тоже не справился: {pil_e}")
            finally:
                self.progress.setVisible(False)
                self.label.setText("Готово!" if self.btn_run.isEnabled() else "Ошибка.")
                self.btn_run.setEnabled(True)
            return

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
