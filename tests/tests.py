# tests/tests.py

import pytest
#пример путей до файлов
#from ai_design_assistant.ui.main_window import MainWindow

import os
from pathlib import Path

from ai_design_assistant.core.image_utils import image_to_base64, remove_background, apply_upscale
from ai_design_assistant.core.chat import ChatSession
from ai_design_assistant.core.plugins import get_plugin_manager


BASE = Path(__file__).parent

# 🔹 Тест 1: base64 кодирование изображения
def test_image_to_base64():
    result = image_to_base64(BASE / "sample.png")
    assert isinstance(result, str) and result.startswith("data:image/"), "Base64 невалиден"


# 🔹 Тест 2: удаление фона
def test_remove_background():
    result_path = remove_background(BASE / "sample.png")
    assert Path(result_path).exists(), "Фон не был удалён"


# 🔹 Тест 3: апскейл изображения
def test_apply_upscale():
    result_path = apply_upscale(BASE / "sample.png")
    path = Path(result_path)
    print("Upscale result:", result_path)

    # Допустим оба пути: realesrgan или PIL
    assert path.exists() or path.with_stem(path.stem + "_pil").exists(), "Upscale не выполнен"



# 🔹 Тест 4: создание, сохранение и загрузка чата
def test_chat_save_load():
    session = ChatSession.create_new()
    session.add_message("user", "Привет!")
    session.save()

    restored = ChatSession.load(session._path)
    assert restored.messages[0].content == "Привет!", "Сообщение не сохранилось корректно"


# 🔹 Тест 5: проверка списка плагинов и запуск remove_bg
def test_plugins_list_and_run():
    manager = get_plugin_manager()
    available = manager.names
    assert "remove_bg_plugin" in available, "Плагин 'remove_bg_plugin' не найден"

    plugin = manager.get("remove_bg_plugin")
    result_path = plugin.run(image_path=BASE / "sample.png")
    assert Path(result_path).exists(), "Плагин remove_bg_plugin не сработал"




