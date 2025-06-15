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

from huggingface_hub import snapshot_download
from PyQt6.QtWidgets import QMessageBox
import os


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
_PROVIDER_CHOICES: Final = ["openai", "deepseek", "local", "local_qwen25"]
_UNLOAD_CHOICES: Final = {
    "none": "Не выгружать (максимальная скорость)",
    "cpu": "Выгружать в RAM (экономия VRAM)",
    "full": "Полная выгрузка (экономия VRAM и RAM)",
}




class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:  # noqa: D401
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(420)
        self._settings = Settings.load()
        self._download_button = None

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

        model_cb.currentTextChanged.connect(self._update_download_button)
        g_form.addRow("Model provider:", model_cb)
        self._model_cb = model_cb  # нужно для доступа внутри update
        self._model_form = g_form  # нужно для динамического добавления кнопки
        self._update_download_button(model_cb.currentText())

        theme_cb = QComboBox()
        theme_cb.addItems(_THEME_CHOICES)
        theme_cb.setCurrentText(self._settings.theme)
        g_form.addRow("Theme:", theme_cb)

        # unload mode
        unload_cb = QComboBox()
        for key, label in _UNLOAD_CHOICES.items():
            unload_cb.addItem(label, userData=key)

        current_mode = self._settings.local_unload_mode
        index = list(_UNLOAD_CHOICES.keys()).index(current_mode)
        unload_cb.setCurrentIndex(index)
        g_form.addRow("Unload mode:", unload_cb)


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
        self._unload_cb = unload_cb

    # ------------------------------------------------------------------#
    #  Accept / save                                                    #
    # ------------------------------------------------------------------#
    def accept(self) -> None:  # noqa: D401
        # non-secret settings → JSON
        raw_path = Path(self._chats_le.text().strip())

        # Если пользователь по ошибке указал файл – берём родительскую папку
        if raw_path.suffix.lower() == ".json" or raw_path.is_file():
            raw_path = raw_path.parent

        self._settings.chats_path = str(raw_path)
        self._settings.local_unload_mode = self._unload_cb.currentData()
        self._settings.chats_path = self._chats_le.text().strip()
        self._settings.model_provider = self._model_cb.currentText()
        self._settings.theme = self._theme_cb.currentText()
        self._settings.plugins_enabled = {n: cb.isChecked() for n, cb in self._plugin_cbs.items()}
        self._settings.save()

        # secrets → .env
        Settings.set_env_var("OPENAI_API_KEY", self._openai_le.text().strip() or None)
        Settings.set_env_var("DEEPSEEK_API_KEY", self._deepseek_le.text().strip() or None)

        super().accept()

        from ai_design_assistant.ui.main_window import get_main_window

        main_win = get_main_window()
        if main_win is not None:
            main_win.reload_settings()

    # expose read-only for caller (rarely needed)
    @property
    def settings(self) -> Settings:
        return self._settings

    def _is_model_downloaded(self, model_id: str) -> bool:
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        return any(p.name.startswith(model_id.replace('/', '--')) for p in hf_cache.glob("models--*"))

    def _download_model(self, model_id: str) -> None:
        try:
            snapshot_download(repo_id=model_id, local_dir=None)
            QMessageBox.information(self, "Model downloaded", f"{model_id} successfully downloaded.")
            self.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to download {model_id}:\n{e}")

    def _update_download_button(self, provider: str) -> None:
        model_id_map = {
            "local": "neulab/Pangea-7B-hf",
            "local_qwen25": "Qwen/Qwen2.5-VL-3B-Instruct"
        }

        # Удаляем старую кнопку, если есть
        if self._download_button:
            self._download_button.setParent(None)
            self._download_button.deleteLater()
            self._download_button = None

        # Если выбрана локальная модель и она не скачана — создаём кнопку
        if provider in model_id_map:
            model_id = model_id_map[provider]
            if not self._is_model_downloaded(model_id):
                btn = QPushButton(f"📥 Download {model_id}")
                btn.clicked.connect(lambda: self._download_model(model_id))
                self._download_button = btn
                self._model_form.addRow("Model download:", btn)


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
