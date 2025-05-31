"""Framework-agnostic user settings.

* JSON*-часть (data/settings.json) хранит **не-секретные** параметры:
    • chats_path            – где лежат .chat-файлы
    • model_provider        – openai | deepseek | local
    • theme                 – light | dark | auto
    • language              – 'en', 'ru', …
    • plugins_enabled       – {plugin_name: bool}

* .env (в корне репозитория) хранит только API-ключи, установлен­ные
  через SettingsDialog.  Файл создаётся при первом сохранении ключа.

Все высокоуровневые методы сведены к:
    Settings.load()   → экземпляр
    s.save()          → записывает JSON
    Settings.set_env_var("OPENAI_API_KEY", "...")  → правит .env
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final, Self
from dataclasses import fields

from dotenv import load_dotenv

# ---------------------------------------------------------------------------#
#  Файлы                                                                      #
# ---------------------------------------------------------------------------#
_BASE_DIR: Final = Path(__file__).resolve().parent.parent.parent
JSON_PATH: Final = Path(__file__).with_suffix("").parent.parent / "data" / "settings.json"
JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

DOTENV_PATH: Final = _BASE_DIR / ".env"          # secrets
load_dotenv(dotenv_path=DOTENV_PATH, override=False)   # не падаем, если .env нет


_SETTINGS_FILE = Path("data/settings.json")
def get_chats_directory() -> Path:
    if not _SETTINGS_FILE.exists():
        return Path("data/chats").resolve()  # Абсолютный путь по умолчанию

    with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
        settings = json.load(f)
    chats_path = settings.get("chats_path", "data/chats")

    # Если путь относительный, приведите его к абсолютному
    if not Path(chats_path).is_absolute():
        return (Path(__file__).parent.parent / chats_path).resolve()
    else:
        return Path(chats_path).resolve()

    p = Path(chats_path).expanduser()

    # Пользователь мог сохранить путь до файла → отходим на каталог
    if p.suffix.lower() == ".json" or p.is_file():
        p = p.parent

    if not p.is_absolute():
        p = (Path(__file__).parent.parent / p).resolve()

    return p

# ---------------------------------------------------------------------------#
#  Dataclass                                                                  #
# ---------------------------------------------------------------------------#

@dataclass
class Settings:
    # ========= General ========= #
    chats_path: str = "chats"
    model_provider: str = "openai"          # openai | deepseek | local
    theme: str = "auto"                     # light | dark | auto
    language: str = "en"

    # ========= LLM Options ========= #
    local_unload_mode: str = "cpu"           # cpu | full

    # ========= Plugins ========= #
    plugins_enabled: dict[str, bool] = field(default_factory=dict)

    # --- internal (не сериализуем) --- #
    _path: Path | None = field(default=None, init=False, repr=False, compare=False)

    # ------------------------------------------------------------------#
    #  Persistence helpers                                              #
    # ------------------------------------------------------------------#
    @classmethod
    def _cfg_path(cls) -> Path:
        return JSON_PATH

    @classmethod
    def load(cls) -> Self:
        path = cls._cfg_path()
        try:
            data = json.loads(path.read_text("utf-8")) if path.exists() else {}
        except json.JSONDecodeError:
            data = {}

        # ── отбрасываем поля, которых нет в dataclass ── #
        allowed = {f.name for f in fields(cls)}
        data = {k: v for k, v in data.items() if k in allowed}

        inst = cls(**data)
        inst._path = path
        inst._ensure_plugins_dict()
        return inst

    # ------------------------------------------------------------------#
    # .env convenience (back-compat for __main__)                      #
    # ------------------------------------------------------------------#
    @ staticmethod
    def load_dotenv(dotenv_path: str | Path | None = None) -> None:  # noqa: D401
        """Load variables from a .env file (noop if already done)."""
        load_dotenv(dotenv_path or DOTENV_PATH, override=False)

    def save(self) -> None:
        if self._path is None:
            self._path = self._cfg_path()
        self._path.write_text(
            json.dumps(
                asdict(
                    self,
                    dict_factory=lambda items: {k: v for k, v in items if not k.startswith("_")},
                ),
                indent=2,
            ),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------#
    #  .env helpers (static)                                            #
    # ------------------------------------------------------------------#
    @staticmethod
    def set_env_var(key: str, value: str | None) -> None:
        """Write **key=value** into .env (create if missing)."""
        key = key.upper()
        env_lines: list[str] = []
        if DOTENV_PATH.exists():
            env_lines = DOTENV_PATH.read_text("utf-8").splitlines()

        # перезаписываем или добавляем
        filtered = [ln for ln in env_lines if not ln.startswith(f"{key}=")]
        if value:
            filtered.append(f"{key}={value}")

        DOTENV_PATH.write_text("\n".join(filtered) + "\n", encoding="utf-8")
        os.environ[key] = value or ""

    # ------------------------------------------------------------------#
    #  Convenience getters                                              #
    # ------------------------------------------------------------------#
    @property
    def openai_api_key(self) -> str | None:
        return os.getenv("OPENAI_API_KEY")

    @property
    def deepseek_api_key(self) -> str | None:
        return os.getenv("DEEPSEEK_API_KEY")

    # ------------------------------------------------------------------#
    #  Internals                                                        #
    # ------------------------------------------------------------------#
    def _ensure_plugins_dict(self) -> None:
        """Если первый запуск — включаем все плагины, найденные в /plugins."""
        if self.plugins_enabled:
            return
        plugins_dir = Path(__file__).with_suffix("").parent.parent / "plugins"
        self.plugins_enabled = {
            p.stem: True
            for p in plugins_dir.glob("*.py")
            if p.name not in {"__init__.py", ""}
        }
