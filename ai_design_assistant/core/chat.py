from __future__ import annotations
import json
import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Literal, Optional, Iterable


import tempfile

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

        assert self._path is not None, "Chat path not initialized"

        # 1. Создаём папку `images/`, если нет
        images_dir = self._path.parent / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        # 2. Генерируем имя и копируем изображение
        ext = Path(image_path).suffix or ".png"
        image_name = f"image_{len(self.messages) + 1}{ext}"
        new_path = images_dir / image_name
        copy2(image_path, new_path)

        # 3. Относительный путь внутри чата
        relative_path = Path("images") / image_name

        msg = Message(
            role=role,
            content=content,
            image=str(relative_path)  # например: "images/image_3.png"
        )
        self.messages.append(msg)
        self.save()
        return msg

    def __iter__(self) -> Iterable[Message]:
        return iter(self.messages)

    @classmethod
    def create_new(cls) -> ChatSession:
        session = cls()
        chats_dir = get_chats_directory()

        # Папка конкретного чата
        chat_dir = chats_dir / session.uuid
        chat_dir.mkdir(parents=True, exist_ok=True)

        # Путь к JSON-файлу внутри chat_N/chat_N.json
        session._path = chat_dir / f"{session.uuid}.json"
        return session

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
        if self._path is None or not self._path.name.endswith(".json"):
            logger.warning(f"Генерируется путь, старый _path: {self._path}")
            self._path = self._generate_filename()

        try:
            logger.debug(f"Сохраняю чат в: {self._path}")
            self._path.parent.mkdir(parents=True, exist_ok=True)

            payload = self.to_dict()
            logger.debug(f"Сообщений в чате: {len(payload['messages'])}")

            # Безопасная атомарная перезапись через временный файл
            with tempfile.NamedTemporaryFile("w", dir=self._path.parent, delete=False, encoding="utf-8") as tmp:
                json.dump(payload, tmp, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp.name)

            tmp_path.replace(self._path)

            logger.info(f"Чат успешно сохранён: {self._path}")
            return self._path

        except Exception as e:
            logger.exception(f"Ошибка при сохранении чата: {e}")
            raise

    @classmethod
    def load(cls, path: str | Path) -> ChatSession:
        p = Path(path).expanduser().resolve()
        if p.is_dir():
            raise ValueError(f"Нельзя загрузить чат: путь {p} — это папка, а не JSON-файл.")
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

        # Если по пути внезапно файл – переименуем и создадим папку
        if root.exists() and root.is_file():
            backup = root.with_suffix(".bak")
            root.rename(backup)
            logger.warning(f"Файл {root} переименован в {backup}; создаю папку.")
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def _generate_filename(cls) -> Path:
        root = cls._chats_root()
        next_num = 1

        while True:
            chat_dir = root / f"chat_{next_num}"
            json_path = chat_dir / f"chat_{next_num}.json"

            # 🛡 если по пути chat_dir — файл, а не папка → удалим
            if chat_dir.exists() and not chat_dir.is_dir():
                try:
                    chat_dir.unlink()
                    logger.warning(f"Удалён конфликтный файл по пути: {chat_dir}")
                except Exception as e:
                    logger.error(f"Не удалось удалить конфликтный файл {chat_dir}: {e}")
                    next_num += 1
                    continue

            try:
                chat_dir.mkdir(parents=True, exist_ok=False)
                logger.info(f"Создана директория чата: {chat_dir}")
                return json_path
            except (FileExistsError, PermissionError) as e:
                logger.warning(f"Проблема с {chat_dir}: {e}")
                next_num += 1


# ─────────────────────────────────────────────────────────────────────────────
# Migration logic
# ─────────────────────────────────────────────────────────────────────────────

def migrate_chat_data(data: dict, from_version: int) -> dict:
    logger.warning(f"Migrating chat from version {from_version} → {_CHAT_SCHEMA_VERSION}")
    if from_version == 1:
        return data  # пока изменений нет
    raise ValueError(f"Unsupported schema version: {from_version}")

def handle_tool_calls(tool_calls: list[dict], chat: ChatSession) -> list[Message]:
    """Обрабатывает tool_calls от OpenAI и вызывает соответствующие плагины."""
    from ai_design_assistant.core.plugins import get_plugin_by_name

    results = []
    for call in tool_calls:
        try:
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])

            plugin = get_plugin_by_name(name)
            if plugin is None:
                logger.warning(f"Плагин не найден: {name}")
                continue

            result_path = plugin.run(**args)

            # Добавляем результат как сообщение ассистента
            msg = chat.add_image_message("assistant", f"[{plugin.display_name}] Готово!", result_path)
            results.append(msg)
        except Exception as e:
            logger.exception(f"Ошибка при выполнении tool_call: {e}")
            msg = chat.add_message("assistant", f"❌ Ошибка при вызове плагина: {e}")
            results.append(msg)
    return results

def atomic_write_json(path: Path, data: dict) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        temp_path = Path(tmp.name)
    temp_path.replace(path)
