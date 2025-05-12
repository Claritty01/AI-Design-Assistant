"""Modal Preferences dialog (Qt-side).

Редактирует:
    • пути к чатам
    • модель (openai / deepseek / local)
    • тему (auto / light / dark)
    • список плагинов (checkbox)
    • два API-ключа (OpenAI / DeepSeek)  — пишутся в .env

Caller обязан вызвать `dlg.exec()` и, получив Accepted, уже ничего делать не
нужно: диалог сам сохраняет Settings и обновляет .env.  Возвращает экземпляр
через атрибут `settings`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Final

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QTabWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai_design_assistant.core.settings import Settings

_THEME_CHOICES: Final = ["auto", "light", "dark"]
_PROVIDER_CHOICES: Final = ["openai", "deepseek", "local"]


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:  # noqa: D401
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(420)
        self._settings = Settings.load()

        # ──────────────────────────────────────────────────────────────#
        #  Layout scaffolding                                           #
        # ──────────────────────────────────────────────────────────────#
        root = QVBoxLayout(self)

        # === General tab === #
        general_w = QWidget()
        g_form = QFormLayout(general_w)

        # chats_path
        chats_le = QLineEdit(self._settings.chats_path)
        browse_btn = QPushButton("…")
        browse_btn.setFixedWidth(28)

        def _browse():
            p = QFileDialog.getExistingDirectory(self, "Select chat folder", self._settings.chats_path)
            if p:
                chats_le.setText(p)

        browse_btn.clicked.connect(_browse)
        path_row = QHBoxLayout()
        path_row.addWidget(chats_le, 1)
        path_row.addWidget(browse_btn)
        g_form.addRow("Chats folder:", path_row)

        # model / theme
        model_cb = QComboBox()
        model_cb.addItems(_PROVIDER_CHOICES)
        model_cb.setCurrentText(self._settings.model_provider)
        g_form.addRow("Model provider:", model_cb)

        theme_cb = QComboBox()
        theme_cb.addItems(_THEME_CHOICES)
        theme_cb.setCurrentText(self._settings.theme)
        g_form.addRow("Theme:", theme_cb)

        # === API-keys tab === #
        api_w = QWidget()
        api_form = QFormLayout(api_w)
        openai_le = QLineEdit(self._settings.openai_api_key or "")
        deepseek_le = QLineEdit(self._settings.deepseek_api_key or "")
        openai_le.setEchoMode(QLineEdit.EchoMode.Password)
        deepseek_le.setEchoMode(QLineEdit.EchoMode.Password)
        api_form.addRow("OpenAI API key:", openai_le)
        api_form.addRow("DeepSeek API key:", deepseek_le)

        # === Plugins tab === #
        plugins_w = QWidget()
        p_lay = QVBoxLayout(plugins_w)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)

        checkboxes: dict[str, QCheckBox] = {}
        for name, enabled in self._settings.plugins_enabled.items():
            cb = QCheckBox(name)
            cb.setChecked(enabled)
            checkboxes[name] = cb
            inner_lay.addWidget(cb)
        inner_lay.addStretch(1)
        scroll.setWidget(inner)
        p_lay.addWidget(scroll)

        # tabs
        tabs = QTabWidget()
        tabs.addTab(general_w, "General")
        tabs.addTab(api_w, "API keys")
        tabs.addTab(plugins_w, "Plugins")
        root.addWidget(tabs, 1)

        # buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("ok_button")
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setObjectName("cancel_button")
        root.addWidget(buttons)

        # keep refs
        self._chats_le = chats_le
        self._model_cb = model_cb
        self._theme_cb = theme_cb
        self._openai_le = openai_le
        self._deepseek_le = deepseek_le
        self._plugin_cbs = checkboxes

    # ------------------------------------------------------------------#
    #  Accept / save                                                    #
    # ------------------------------------------------------------------#
    def accept(self) -> None:  # noqa: D401
        # non-secret settings → JSON
        self._settings.chats_path = self._chats_le.text().strip()
        self._settings.model_provider = self._model_cb.currentText()
        self._settings.theme = self._theme_cb.currentText()
        self._settings.plugins_enabled = {n: cb.isChecked() for n, cb in self._plugin_cbs.items()}
        self._settings.save()

        # secrets → .env
        Settings.set_env_var("OPENAI_API_KEY", self._openai_le.text().strip() or None)
        Settings.set_env_var("DEEPSEEK_API_KEY", self._deepseek_le.text().strip() or None)

        super().accept()

    # expose read-only for caller (rarely needed)
    @property
    def settings(self) -> Settings:
        return self._settings


# ──────────────────────────────────────────────────────────────────────#
#  Demo                                                                #
# ──────────────────────────────────────────────────────────────────────#
if __name__ == "__main__":  # pragma: no cover
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dlg = SettingsDialog()
    dlg.exec()
    print("Settings saved to:", Settings._cfg_path())  # type: ignore[attr-defined]
