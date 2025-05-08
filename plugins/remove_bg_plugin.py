# plugins/remove_bg_plugin.py
from pathlib import Path
import subprocess, io
from plugin_manager import BaseImagePlugin
from logger import get_logger

log = get_logger("rembg")
display_name = "Remove BG"

def _cli(src: Path, dst: Path):
    cmd = ["rembg", "i", str(src), str(dst)]
    return subprocess.run(cmd, check=True, capture_output=True, text=True)

def _lib(src: Path, dst: Path):
    from rembg import remove
    from PIL import Image

    with Image.open(src) as img:
        out = remove(img)
        out.save(dst)

def process(image_path: str, **kwargs) -> str:
    src = Path(image_path)
    dst = src.with_stem(f"{src.stem}_nobg").with_suffix(".png")

    try:
        _cli(src, dst)
        log.info("rembg CLI → %s", dst)
    except Exception as e:
        log.warning("CLI failed (%s), trying rembg Lib", e)
        _lib(src, dst)
        log.info("rembg Lib → %s", dst)

    return str(dst)
