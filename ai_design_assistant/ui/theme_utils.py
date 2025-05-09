"""Utilities for loading QSS themes and detecting system colour scheme.

The helper gracefully degrades for older Qt versions that do **not** expose
QPalette.colorScheme() (e.g. Qt 6.2 shipped on many Linux distros). In that
case we approximate the scheme from window background luminance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from PyQt6.QtGui import QGuiApplication, QPalette, QColor

_THEMES = Path(__file__).with_suffix("").parent.parent / "resources" / "themes"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def load_stylesheet(theme: Literal["light", "dark", "auto", ""] = "auto") -> str:
    """Return concatenated QSS for *theme*.

    Parameters
    ----------
    theme
        "light", "dark", or "auto" (autodetect). Empty string → treated as
        "auto" for backward-compat.
    """

    if not theme or theme == "auto":
        theme = _detect_system_theme()

    base_qss = (_THEMES / f"{theme}.qss").read_text(encoding="utf-8")
    chat_qss = (_THEMES / "chat.qss").read_text(encoding="utf-8")
    return base_qss + "\n" + chat_qss


# ---------------------------------------------------------------------------
# Internal: system-theme heuristics
# ---------------------------------------------------------------------------

def _detect_system_theme() -> str:
    """Best-effort detection of current colour scheme (light/dark)."""
    palette = QGuiApplication.palette()

    # Qt 6.5+: QPalette.colorScheme() exists
    scheme_attr = getattr(palette, "colorScheme", None)
    if callable(scheme_attr):
        scheme = scheme_attr()
        # names are e.g. "ColorScheme.Dark" → we only need last part
        return "dark" if "dark" in scheme.name.lower() else "light"

    # Fallback: compute luminance of window background
    bg: QColor = palette.color(QPalette.ColorRole.Window)
    luminance = (0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()) / 255
    return "dark" if luminance < 0.5 else "light"
