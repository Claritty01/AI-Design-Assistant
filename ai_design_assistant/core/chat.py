"""Chat session data model (framework‑agnostic).

Core responsibilities
=====================
* hold a list of :class:`Message` objects (user ↔ assistant ↔ system)
* append messages with automatic timestamps
* save / load chat history in JSON (one file per chat)
* lightweight helper for generating new chat filenames

No PyQt imports allowed — UI layer will observe / mutate via public API.
"""
from __future__ import annotations
from ai_design_assistant.core.settings import get_chats_directory  # ← Добавить
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Iterable, Self
import logging

from platformdirs import user_data_dir

import logging
logger = logging.getLogger(__name__)  # ← Добавить

_APP_NAME: Final = "AI Design Assistant"
_CHAT_DIRNAME: Final = "chats"
_DEFAULT_TITLE: Final = "Untitled chat"

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Message:
    """Single chat turn."""
    role: str  # "user" | "assistant" | "system"
    content: str
    image: str | None = None  # Путь к изображению
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class ChatSession:
    """Container for chat messages and file persistence."""
    def __init__(self):
        self.uuid = str(uuid.uuid4())  # Генерация уникального идентификатора
        self.messages = []

    title: str = _DEFAULT_TITLE
    messages: list[Message] = field(default_factory=list)
    uuid: str = field(default_factory=lambda: uuid.uuid4().hex)

    # path is assigned on first save / load
    _path: Path | None = field(default=None, init=False, repr=False, compare=False)

    # ------------------------------------------------------------------
    # Message ops
    # ------------------------------------------------------------------
    def add_message(self, role: str, content: str) -> Message:
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        return msg

    def __iter__(self) -> Iterable[Message]:
        return iter(self.messages)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    @classmethod
    def _chats_root(cls) -> Path:
        root = get_chats_directory()
        root.mkdir(parents=True, exist_ok=True)
        return root  # Убрано добавление _CHAT_DIRNAME

    @classmethod
    def _generate_filename(cls) -> Path:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        chat_uuid = uuid.uuid4().hex
        chat_dir = cls._chats_root() / f"chat_{chat_uuid}"
        chat_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Creating chat directory: {chat_dir}")
        return chat_dir / "chat.json"

    @classmethod
    def load(cls, path: str | Path) -> "ChatSession":
        p = Path(path).expanduser().resolve()
        data = json.loads(p.read_text("utf-8"))

        session = cls(
            title=data.get("title", _DEFAULT_TITLE),
            messages=[Message(**m) for m in data.get("messages", [])],
            uuid=data.get("uuid", uuid.uuid4().hex),
        )
        session._path = p

        # Проверка изображений
        for msg in session.messages:
            if msg.image:
                img_path = (p.parent / msg.image).resolve()
                if not img_path.exists():
                    logger.warning(f"Image missing: {img_path}")
                    msg.image = None
        return session

    def save(self) -> Path:
        if self._path is None:
            self._path = self._generate_filename()

        logger.info(f"Saving chat to: {self._path}")
        payload = {
            "title": self.title,
            "uuid": self.uuid,
            "messages": [m.as_dict() for m in self.messages],
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._path

    # convenience: files older than *days* → delete (housekeeping)
    @classmethod
    def purge_old(cls, days: int = 30) -> None:
        cutoff = datetime.now().timestamp() - days * 86400
        root = cls._chats_root()

        for chat_dir in root.glob("chat_*"):
            if chat_dir.is_dir():
                json_file = chat_dir / "chat.json"
                if json_file.exists() and json_file.stat().st_mtime < cutoff:
                    try:
                        for file in chat_dir.iterdir():
                            file.unlink()
                        chat_dir.rmdir()
                    except Exception as e:
                        logger.error(f"Failed to delete {chat_dir}: {e}")

    # ------------------------------------------------------------------
    # Representation helpers
    # ------------------------------------------------------------------
    def short_summary(self, max_len: int = 60) -> str:
        if not self.messages:
            return "(empty)"
        last = self.messages[-1].content.replace("\n", " ")
        return last[:max_len] + ("…" if len(last) > max_len else "")

    def add_image_message(self, role: str, content: str, image_path: str) -> Message:
        from shutil import copy2

        # Генерация имени файла изображения
        image_name = f"image_{len(self.messages) + 1}{Path(image_path).suffix}"
        target_path = self._path.parent / image_name  # путь внутри папки чата
        copy2(image_path, target_path)

        # Сохраняем относительный путь в сообщении
        msg = Message(
            role=role,
            content=content,
            image=str(target_path.relative_to(self._chats_root()))
        )
        self.messages.append(msg)
        return msg