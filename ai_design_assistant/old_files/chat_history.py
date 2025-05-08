import json
import os

CHAT_DIR = "chat_data"
current_chat_file = os.path.join(CHAT_DIR, "chat_1.json")  # по умолчанию

def set_current_chat(path):
    global current_chat_file
    current_chat_file = path

def load_history():
    if not os.path.exists(current_chat_file):
        save_history([])
    with open(current_chat_file, "r", encoding="utf-8") as f:
        return json.load(f)

def save_history(history):
    with open(current_chat_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def append_message(history, role, content, image=None):
    message = {"role": role, "content": content}
    if image:
        message["image"] = image  # ⬅️ сохраняем путь к изображению
    history.append(message)
    save_history(history)


