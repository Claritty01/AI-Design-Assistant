"""Application‑wide settings (core layer — no PyQt dependency).

The settings live in a JSON file under the user configuration directory
(``~/.config/AI Design Assistant/settings.json`` or OS‑specific equivalent).
On top of that we support a classic ``.env`` for secrets during development.

Usage
-----
>>> Settings.load_dotenv()  # optional, only once
>>> s = Settings.load()
>>> s.model_provider = "deepseek"
>>> s.save()
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final, Self

from appdirs import user_config_dir
from dotenv import load_dotenv

_APP_NAME: Final = "AI Design Assistant"
_SETTINGS_FILE: Final = "settings.json"


@dataclass
class Settings:
    """Serializable user settings.

    *Do not* import PyQt classes here; keep this module framework‑agnostic.
    """

    # === Secrets ===
    openai_api_key: str | None = field(default=None, repr=False)
    deepseek_api_key: str | None = field(default=None, repr=False)

    # === General ===
    model_provider: str = "openai"  # openai | deepseek | local
    theme: str = "auto"  # light | dark | auto
    language: str = "en"

    # === Last session ===
    last_chat_path: str | None = None

    # path is not saved to file, set by load()
    _path: Path | None = field(default=None, init=False, repr=False, compare=False)

    # ---------------------------------------------------------------------
    # Persistence helpers
    # ---------------------------------------------------------------------
    @classmethod
    def _config_path(cls) -> Path:
        cfg_dir = Path(user_config_dir(_APP_NAME))
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return cfg_dir / _SETTINGS_FILE

    @classmethod
    def load(cls) -> "Settings":
        path = cls._config_path()
        if path.exists():
            try:
                data = json.loads(path.read_text("utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

        settings = cls(**data)  # type: ignore[arg-type]
        settings._path = path
        return settings

    def save(self) -> None:
        if self._path is None:
            self._path = self._config_path()
        with self._path.open("w", encoding="utf-8") as fp:
            json.dump(asdict(self, dict_factory=lambda x: {k: v for k, v in x if not k.startswith("_")}), fp, indent=2)

    # ------------------------------------------------------------------
    # .env support
    # ------------------------------------------------------------------
    @staticmethod
    def load_dotenv(dotenv_path: str | Path | None = None) -> None:  # noqa: D401 (imperative)
        """Load variables from .env (development only).

        Called once at application start‑up. Ignores if file missing.
        """
        load_dotenv(dotenv_path)

    # ------------------------------------------------------------------
    # Helper accessors
    # ------------------------------------------------------------------
    @property
    def active_api_key(self) -> str | None:
        match self.model_provider:
            case "openai":
                return self.openai_api_key or os.getenv("OPENAI_API_KEY")
            case "deepseek":
                return self.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY")
            case _:
                return None

    # Convenience: update from env once after load
    def sync_with_env(self) -> None:
        if not self.openai_api_key and (v := os.getenv("OPENAI_API_KEY")):
            self.openai_api_key = v
        if not self.deepseek_api_key and (v := os.getenv("DEEPSEEK_API_KEY")):
            self.deepseek_api_key = v
