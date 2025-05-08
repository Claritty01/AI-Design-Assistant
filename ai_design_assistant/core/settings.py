import json
import os
from pathlib import Path
from PyQt5.QtCore import QSettings
from dotenv import load_dotenv, set_key, find_dotenv


APP_ID = "AI-Assistant"
ORG    = "MyCompany"


SETTINGS_FILE = "../data/settings.json"

default_settings = {
    "chat_data_dir": str(Path.cwd() / "chat_data"),
    "theme": "dark"
}

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        save_settings(default_settings)
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)


class AppSettings:
    _q = QSettings(ORG, APP_ID)

    # ----- getters ---------------------------------------------------------
    # OpenAI
    @classmethod
    def openai_key(cls) -> str:
        # Загружаем из .env с перезаписью, чтобы os.environ всегда был актуален
        dotenv_path = find_dotenv()
        if dotenv_path:
            load_dotenv(dotenv_path, override=True)
        return os.getenv("OPENAI_API_KEY", "")

    # DeepSeek
    @ classmethod
    def deepseek_key(cls) -> str:
        dotenv_path = find_dotenv()
        if dotenv_path:
            load_dotenv(dotenv_path, override=True)
        return os.getenv("DEEPSEEK_API_KEY", "")



    @classmethod
    def chat_data_dir(cls) -> Path:
        default = Path.cwd() / "chat_data"
        return Path(cls._q.value("app/chat_data_dir", str(default)))

    @classmethod
    def theme(cls) -> str:
        return cls._q.value("ui/theme", "System", type=str)

    # ----- setters ---------------------------------------------------------
    # OpenAI API-ключ
    @classmethod
    def set_openai_key(cls, value: str):
        dotenv_path = find_dotenv() or ".env"
        # 1) Обновляем файл
        set_key(dotenv_path, "OPENAI_API_KEY", value)
        # 2) И одновременно обновляем os.environ
        os.environ["OPENAI_API_KEY"] = value

    # DeepSeek API-ключ
    @ classmethod
    def set_deepseek_key(cls, value: str):
        dotenv_path = find_dotenv() or ".env"
        set_key(dotenv_path, "DEEPSEEK_API_KEY", value)
        os.environ["DEEPSEEK_API_KEY"] = value


    @classmethod
    def set_chat_data_dir(cls, value: Path):
        cls._q.setValue("app/chat_data_dir", str(value))

    @classmethod
    def set_theme(cls, value: str):
        cls._q.setValue("ui/theme", value)
