"""Modal dialog for editing user settings.

This is a lightweight wrapper over :class:`ai_design_assistant.core.settings.Settings`.
The dialog is *not* persisted by itself; caller must call ``exec()`` and after
``Accepted`` check *dialog.settings* and decide whether to save.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ai_design_assistant.core import Settings

_LOGGER = logging.getLogger(__name__)
_THEME_CHOICES: Final = ["auto", "light", "dark"]
_PROVIDER_CHOICES: Final = ["openai", "deepseek", "local"]


class SettingsDialog(QDialog):
    """Blocking dialog to edit high‑level app settings."""

    def __init__(self, parent: QWidget | None = None):  # noqa: D401
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.resize(420, 260)

        self.settings = Settings.load()

        self._build_ui()
        self._populate_from_settings()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        # General tab
        tab_general = QWidget()
        fgen = QFormLayout(tab_general)
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(_THEME_CHOICES)
        fgen.addRow("Theme", self.cmb_theme)
        self.cmb_provider = QComboBox()
        self.cmb_provider.addItems(_PROVIDER_CHOICES)
        fgen.addRow("Model provider", self.cmb_provider)
        tabs.addTab(tab_general, "General")

        # Keys tab
        tab_keys = QWidget()
        fkeys = QFormLayout(tab_keys)
        self.le_openai = QLineEdit()
        self.le_openai.setEchoMode(QLineEdit.EchoMode.Password)
        fkeys.addRow("OpenAI API key", self.le_openai)
        self.le_deepseek = QLineEdit()
        self.le_deepseek.setEchoMode(QLineEdit.EchoMode.Password)
        fkeys.addRow("DeepSeek API key", self.le_deepseek)
        tabs.addTab(tab_keys, "Keys")

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ------------------------------------------------------------------
    def _populate_from_settings(self) -> None:  # noqa: D401
        self.cmb_theme.setCurrentText(self.settings.theme)
        self.cmb_provider.setCurrentText(self.settings.model_provider)
        if self.settings.openai_api_key:
            self.le_openai.setText(self.settings.openai_api_key)
        if self.settings.deepseek_api_key:
            self.le_deepseek.setText(self.settings.deepseek_api_key)

    # ------------------------------------------------------------------
    def _on_accept(self) -> None:  # noqa: D401
        self.settings.theme = self.cmb_theme.currentText()
        self.settings.model_provider = self.cmb_provider.currentText()
        self.settings.openai_api_key = self.le_openai.text().strip() or None
        self.settings.deepseek_api_key = self.le_deepseek.text().strip() or None
        self.settings.save()
        _LOGGER.info("Settings saved")
        self.accept()


# Demo run
if __name__ == "__main__":  # pragma: no cover
    import sys

    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dlg = SettingsDialog()
    dlg.exec()
    print("Theme:", dlg.settings.theme)
