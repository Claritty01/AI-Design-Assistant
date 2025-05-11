"""Upscale plugin – full‑featured editor dialog.

Features
--------
* Shows **side‑by‑side preview**: original vs. quick bicubic upscale.
* Slider ×1‒×4 sets the final Real‑ESRGAN scale.
* Checkbox «PNG» to output with alpha.
* When user presses **Apply**, heavy upscale runs (Real‑ESRGAN → fallback PIL) and file is saved next to source.
* Returns resulting path so host app can refresh gallery.

Usage
-----
`plugin_manager.get_plugins()` picks up this module automatically.
`ChatWindow.run_plugin()` already supports the optional `configure()` flow.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Dict, Any

from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QSlider,
    QPushButton,
    QCheckBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from logger import get_logger

from PIL import Image, ImageOps

log = get_logger("upscale_plugin")

display_name = "Upscale…"

# ---------------------------------------------------------------------------
# Helper: light‑weight upscale preview (PIL bicubic)
# ---------------------------------------------------------------------------

def _pil_preview(src: Path, scale: int) -> QPixmap:
    # Лёгкий preview с PIL → QPixmap через in-memory PNG
    img = Image.open(src)
    img_up = ImageOps.scale(img, scale, resample=Image.BICUBIC)
    img_up.thumbnail((420, 420), resample=Image.BICUBIC)

    # конвертация PIL → байты PNG
    from io import BytesIO
    buf = BytesIO()
    img_up.save(buf, format="PNG")
    data = buf.getvalue()

    # загружаем в QPixmap
    pix = QPixmap()
    pix.loadFromData(data)
    return pix


# ---------------------------------------------------------------------------
#   Configuration dialog — returns kwargs for process()
# ---------------------------------------------------------------------------

def configure(parent, image_path: str) -> Dict[str, Any] | None:  # noqa: D401
    src = Path(image_path)

    dlg = QDialog(parent)
    dlg.setWindowTitle("Upscale – параметры")
    vbox = QVBoxLayout(dlg)

    # previews ---------------------------------------------------------------
    h = QHBoxLayout()
    lbl_orig = QLabel(alignment=Qt.AlignCenter)
    pix_orig = QPixmap(image_path).scaledToWidth(420, Qt.SmoothTransformation)
    lbl_orig.setPixmap(pix_orig)
    h.addWidget(lbl_orig)

    lbl_prev = QLabel(alignment=Qt.AlignCenter)
    prev_pix = _pil_preview(src, 2)
    lbl_prev.setPixmap(prev_pix)
    h.addWidget(lbl_prev)
    vbox.addLayout(h)

    # controls ---------------------------------------------------------------
    slider = QSlider(Qt.Horizontal, minimum=1, maximum=4, value=2, tickInterval=1,
                     tickPosition=QSlider.TicksBelow)
    vbox.addWidget(slider)
    chk_png = QCheckBox("PNG выход")
    vbox.addWidget(chk_png)

    # update preview live
    def _on_slide(val):
        lbl_prev.setPixmap(_pil_preview(src, val))
    slider.valueChanged.connect(_on_slide)

    # buttons ----------------------------------------------------------------
    btn_apply = QPushButton("Применить")
    btn_cancel = QPushButton("Отмена")
    btn_apply.clicked.connect(dlg.accept)
    btn_cancel.clicked.connect(dlg.reject)
    hb = QHBoxLayout(); hb.addStretch(); hb.addWidget(btn_cancel); hb.addWidget(btn_apply)
    vbox.addLayout(hb)

    if dlg.exec_() == QDialog.Accepted:
        return {
            "scale": slider.value(),
            "png": chk_png.isChecked(),
        }
    return None

# ---------------------------------------------------------------------------
#   Heavy processing
# ---------------------------------------------------------------------------

def process(image_path: str, *, scale: int = 2, png: bool = False, **_) -> str:
    """Upscale *image_path* by *scale*.

    1. Try Real‑ESRGAN‑NCNN‑Vulkan.
    2. Fallback to PIL bicubic.
    """

    src = Path(image_path)
    out = src.with_stem(f"{src.stem}_up{scale}")
    out = out.with_suffix(".png" if png else src.suffix)

    # ---- Real‑ESRGAN CLI ---------------------------------------------------
    cmd = [
        "realesrgan-ncnn-vulkan",
        "-i", str(src),
        "-o", str(out),
        "-s", str(scale),
        "-n", "realesrgan-x4plus",
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log.info("Upscaled via Real‑ESRGAN → %s", out)
        return str(out)
    except (FileNotFoundError, subprocess.CalledProcessError):
        log.warning("Real‑ESRGAN CLI unavailable, fallback to PIL")

    # ---- PIL fallback ------------------------------------------------------
    img = Image.open(src)
    img_up = ImageOps.scale(img, scale, resample=Image.BICUBIC)
    img_up.save(out)
    log.info("Upscaled via PIL → %s", out)
    return str(out)
