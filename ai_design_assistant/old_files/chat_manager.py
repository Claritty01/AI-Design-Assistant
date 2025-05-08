import os
import json
from datetime import datetime

CHAT_DIR = "chat_data"
CHATS_INDEX = os.path.join(CHAT_DIR, "chats.json")

# Убедиться, что папка существует
os.makedirs(CHAT_DIR, exist_ok=True)


def load_chats():
    if not os.path.exists(CHATS_INDEX):
        save_chats([])
    with open(CHATS_INDEX, "r", encoding="utf-8") as f:
        return json.load(f)


def save_chats(chats):
    with open(CHATS_INDEX, "w", encoding="utf-8") as f:
        json.dump(chats, f, indent=2, ensure_ascii=False)


def create_new_chat():
    chats = load_chats()
    new_id = len(chats) + 1
    chat_filename = f"chat_{new_id}.json"
    title = f"Новый диалог {new_id}"

    chats.append({"id": new_id, "title": title, "file": chat_filename})
    save_chats(chats)

    # Создаём файл истории
    path = os.path.join(CHAT_DIR, chat_filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([], f)

    # 🎯 Создаём поддиректорию chat_data/chat_N/
    folder_name = chat_filename.replace(".json", "")
    folder_path = os.path.join(CHAT_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    return chats[-1]

