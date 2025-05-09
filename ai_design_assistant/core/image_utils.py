from __future__ import annotations

"""Image‑processing helpers: upscale + background removal.

Dependencies (add to requirements.txt):
    pillow>=10.0
    rembg>=2.0  # offline background removal
    realesrgan-ncnn-vulkan  # optional CLI for high‑quality upscaling

If *realesrgan-ncnn-vulkan* is unavailable, PIL resize fallback is used.
"""

import subprocess
from pathlib import Path
import base64
from PIL import Image
from rembg import remove  # type: ignore

from ai_design_assistant.core.logger import get_logger

log = get_logger("modules")


def image_to_base64(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext == "jpg":
        ext = "jpeg"
    mime = f"image/{ext}"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"

# ────────────────────────────────────────────────────────────
# 🔼 UPSCALE
# -----------------------------------------------------------------------------

def apply_upscale(
    image_path: str | Path,
    *,
    scale: int = 2,
    model: str = "realesrgan-x4plus",
    out_dir: str | Path | None = None,
) -> str:
    """Upscale *image_path* by *scale*.

    Returns path to upscaled image. Tries Real‑ESRGAN NCNN first,
    falls back to PIL‑resize if CLI not installed.
    """

    src = Path(image_path)
    if not src.exists():
        raise FileNotFoundError(src)

    out_dir = Path(out_dir or src.parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{src.stem}_up{scale}{src.suffix}"

    cmd = [
        "realesrgan-ncnn-vulkan",
        "-i",
        str(src),
        "-o",
        str(dst),
        "-s",
        str(scale),
        "-n",
        model,
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log.info("Upscaled %s → %s via Real‑ESRGAN", src, dst)
    except FileNotFoundError:
        log.warning("Real‑ESRGAN CLI not found — using PIL fallback")
        _pil_upscale(src, dst, scale)
    except subprocess.CalledProcessError as err:
        log.error("Real‑ESRGAN failed (%s) — using PIL fallback", err)
        _pil_upscale(src, dst, scale)

    return str(dst)


def _pil_upscale(src: Path, dst: Path, scale: int):
    dst = dst.with_stem(f"{dst.stem}_pil")
    img = Image.open(src)
    new_size = (img.width * scale, img.height * scale)
    img = img.resize(new_size, Image.LANCZOS)
    img.save(dst)
    log.info("Upscaled %s → %s via PIL", src, dst)


# ────────────────────────────────────────────────────────────
# 🧼 BACKGROUND REMOVAL
# -----------------------------------------------------------------------------

def remove_background(image_path: str | Path, *, out_dir: str | Path | None = None) -> str:
    """Remove background and return path to PNG with alpha channel."""

    src = Path(image_path)
    if not src.exists():
        raise FileNotFoundError(src)

    out_dir = Path(out_dir or src.parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{src.stem}_nobg.png"

    with open(src, "rb") as f:
        result = remove(f.read())

    with open(dst, "wb") as f:
        f.write(result)

    log.info("Removed background %s → %s", src, dst)
    return str(dst)

