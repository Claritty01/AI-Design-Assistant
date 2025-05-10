from __future__ import annotations
import json
import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Literal, Optional, Iterable

from platformdirs import user_data_dir
from ai_design_assistant.core.settings import get_chats_directory

logger = logging.getLogger(__name__)

_APP_NAME: Final = "AI Design Assistant"
_DEFAULT_TITLE: Final = "Untitled chat"
_CHAT_SCHEMA_VERSION: Final = 1


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Message:
    role: Literal["user", "assistant", "system"]
    content: str
    image: Optional[str] = None  # относительный путь
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    uuid: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class ChatSession:
    title: str = _DEFAULT_TITLE
    messages: list[Message] = field(default_factory=list)
    uuid: str = field(default_factory=lambda: uuid.uuid4().hex)
    schema_version: int = _CHAT_SCHEMA_VERSION

    _path: Path | None = field(default=None, init=False, repr=False, compare=False)

    # ──────────────── Message operations ────────────────

    def add_message(self, role: str, content: str) -> Message:
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        self.save()
        return msg

    def add_image_message(self, role: str, content: str, image_path: str) -> Message:
        from shutil import copy2

        image_name = f"image_{len(self.messages) + 1}{Path(image_path).suffix}"
        assert self._path is not None, "Chat path not initialized"
        target_path = self._path.parent / image_name
        copy2(image_path, target_path)

        relative_path = target_path.relative_to(self._chats_root())
        msg = Message(role=role, content=content, image=str(relative_path))
        self.messages.append(msg)
        self.save()
        return msg

    def __iter__(self) -> Iterable[Message]:
        return iter(self.messages)

    # ──────────────── File ops ────────────────

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "uuid": self.uuid,
            "schema_version": self.schema_version,
            "messages": [asdict(m) for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> ChatSession:
        version = data.get("schema_version", 1)
        if version != _CHAT_SCHEMA_VERSION:
            data = migrate_chat_data(data, from_version=version)

        return cls(
            title=data.get("title", _DEFAULT_TITLE),
            uuid=data.get("uuid", uuid.uuid4().hex),
            messages=[Message(**m) for m in data.get("messages", [])],
            schema_version=_CHAT_SCHEMA_VERSION
        )

    def save(self) -> Path:
        if self._path is None:
            self._path = self._generate_filename()
        payload = self.to_dict()
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Chat saved to: {self._path}")
        return self._path

    @classmethod
    def load(cls, path: str | Path) -> ChatSession:
        p = Path(path).expanduser().resolve()
        data = json.loads(p.read_text("utf-8"))
        session = cls.from_dict(data)
        session._path = p

        for msg in session.messages:
            if msg.image:
                img_path = (p.parent / msg.image).resolve()
                if not img_path.exists():
                    logger.warning(f"Image missing: {img_path}")
                    msg.image = None
        return session

    @classmethod
    def load_all(cls) -> list[ChatSession]:
        root = cls._chats_root()
        sessions = []
        for folder in sorted(root.iterdir()):
            if folder.is_dir():
                json_file = folder / f"{folder.name}.json"
                if json_file.exists():
                    try:
                        sessions.append(cls.load(json_file))
                    except Exception as e:
                        logger.warning("Ошибка загрузки чата %s: %s", json_file, e)
        return sessions

    @classmethod
    def purge_old(cls, days: int = 30) -> None:
        cutoff = datetime.now().timestamp() - days * 86400
        root = cls._chats_root()
        for chat_dir in root.glob("chat_*"):
            if chat_dir.is_dir():
                json_file = chat_dir / f"{chat_dir.name}.json"
                if json_file.exists() and json_file.stat().st_mtime < cutoff:
                    try:
                        for file in chat_dir.iterdir():
                            file.unlink()
                        chat_dir.rmdir()
                    except Exception as e:
                        logger.error(f"Failed to delete {chat_dir}: {e}")

    @classmethod
    def _chats_root(cls) -> Path:
        root = get_chats_directory()
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def _generate_filename(cls) -> Path:
        root = cls._chats_root()
        nums = [
            int(p.name.split("_")[1])
            for p in root.iterdir()
            if p.is_dir() and p.name.startswith("chat_") and p.name.split("_")[1].isdigit()
        ]
        next_num = max(nums, default=0) + 1
        chat_dir = root / f"chat_{next_num}"
        chat_dir.mkdir(parents=True, exist_ok=False)
        logger.info("Creating chat directory: %s", chat_dir)
        return chat_dir / f"chat_{next_num}.json"

    def short_summary(self, max_len: int = 60) -> str:
        if not self.messages:
            return "(empty)"
        last = self.messages[-1].content.replace("\n", " ")
        return last[:max_len] + ("…" if len(last) > max_len else "")


# ─────────────────────────────────────────────────────────────────────────────
# Migration logic
# ─────────────────────────────────────────────────────────────────────────────

def migrate_chat_data(data: dict, from_version: int) -> dict:
    logger.warning(f"Migrating chat from version {from_version} → {_CHAT_SCHEMA_VERSION}")
    if from_version == 1:
        return data  # пока изменений нет
    raise ValueError(f"Unsupported schema version: {from_version}")
