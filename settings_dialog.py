# settings_dialog.py
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QFileDialog, QComboBox, QHBoxLayout, QCheckBox
)
from PyQt5.QtCore import Qt
from pathlib import Path
from settings import AppSettings
from settings import load_settings, save_settings


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setModal(True)
        self.setMinimumWidth(420)

        # ---------- UI ----------
        main_layout = QVBoxLayout(self)
        form = QFormLayout()

        # OpenAI-ключ (будет храниться в .env)
        self.key_edit = QLineEdit(AppSettings.openai_key(), self)
        self.key_edit.setEchoMode(QLineEdit.Password)
        form.addRow("OpenAI API‑ключ:", self.key_edit)

        # DeepSeek-ключ (будет храниться в .env)
        self.deepseek_edit = QLineEdit(AppSettings.deepseek_key(), self)
        self.deepseek_edit.setEchoMode(QLineEdit.Password)
        form.addRow("DeepSeek API-ключ:", self.deepseek_edit)

        # Папка chat_data
        h_dir = QHBoxLayout()
        self.dir_edit = QLineEdit(str(AppSettings.chat_data_dir()), self)
        browse_btn = QPushButton("…", self)
        browse_btn.setFixedWidth(28)
        browse_btn.clicked.connect(self.select_dir)
        h_dir.addWidget(self.dir_edit, 1)
        h_dir.addWidget(browse_btn)
        form.addRow("Папка данных:", h_dir)

        # Тема
        self.theme_combo = QComboBox(self)
        self.theme_combo.addItems(["System", "Light", "Dark"])
        idx = self.theme_combo.findText(AppSettings.theme(), Qt.MatchFixedString)
        self.theme_combo.setCurrentIndex(max(idx, 0))
        form.addRow("Тема интерфейса:", self.theme_combo)

        # Автопрокрутка
        self.autoscroll_chk = QCheckBox(self)
        self.autoscroll_chk.setChecked(load_settings().get("autoscroll", True))
        form.addRow("Автопрокрутка:", self.autoscroll_chk)

        # Включить плагины
        self.plugins_chk = QCheckBox(self)
        self.plugins_chk.setChecked(load_settings().get("enable_plugins", True))
        form.addRow("Включить плагины:", self.plugins_chk)

        main_layout.addLayout(form)

        # Кнопки
        btn_box = QHBoxLayout()
        save_btn = QPushButton("Сохранить", self)
        cancel_btn = QPushButton("Отмена", self)
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addStretch(1)
        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        main_layout.addLayout(btn_box)




    # ---------- helpers ----------
    def select_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Выбрать папку данных",
                                                str(AppSettings.chat_data_dir()))
        if path:
            self.dir_edit.setText(path)

    # ---------- QDialog overrides ----------
    def accept(self):
        # 1) сохраняем в QSettings
        AppSettings.set_openai_key(self.key_edit.text().strip())
        AppSettings.set_deepseek_key(self.deepseek_edit.text().strip())
        AppSettings.set_chat_data_dir(Path(self.dir_edit.text().strip()))
        AppSettings.set_theme(self.theme_combo.currentText())

        # 2) и дублируем/записываем в settings.json
        js = load_settings()
        js["chat_data_dir"] = self.dir_edit.text().strip()
        js["theme"] = self.theme_combo.currentText().lower()

        js["autoscroll"]      = self.autoscroll_chk.isChecked()
        js["enable_plugins"]  = self.plugins_chk.isChecked()
        save_settings(js)

        super().accept()

