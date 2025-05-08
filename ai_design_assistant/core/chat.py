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

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Iterable, Self

from appdirs import user_data_dir

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
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def as_dict(self) -> dict[str, str]:  # helper for json dump
        return asdict(self)


@dataclass
class ChatSession:
    """Container for chat messages and file persistence."""

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
        root = Path(user_data_dir(_APP_NAME)) / _CHAT_DIRNAME
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def _generate_filename(cls) -> Path:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        return cls._chats_root() / f"chat_{ts}.json"

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
        return session

    def save(self) -> Path:
        if self._path is None:
            self._path = self._generate_filename()
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
        for file in cls._chats_root().glob("chat_*.json"):
            if file.stat().st_mtime < cutoff:
                try:
                    file.unlink()
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Representation helpers
    # ------------------------------------------------------------------
    def short_summary(self, max_len: int = 60) -> str:
        if not self.messages:
            return "(empty)"
        last = self.messages[-1].content.replace("\n", " ")
        return last[:max_len] + ("…" if len(last) > max_len else "")
