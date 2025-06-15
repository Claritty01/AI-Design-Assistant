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



import base64

def test_base64_roundtrip():
    encoded = image_to_base64(BASE / "sample.png")
    assert encoded.startswith("data:image/"), "Метка MIME неверна"

    # Отрежем префикс и декодируем
    header, data = encoded.split(",", 1)
    decoded = base64.b64decode(data)

    # Сохраним временно
    tmp_path = BASE / "decoded_output.png"
    tmp_path.write_bytes(decoded)
    assert tmp_path.exists() and tmp_path.stat().st_size > 0, "base64-декодирование не работает"

def test_empty_chat_save_load():
    session = ChatSession.create_new()
    session.save()
    loaded = ChatSession.load(session._path)
    assert loaded.messages == [], "Пустой чат должен загружаться как пустой"

def test_plugin_reusability():
    plugin = get_plugin_manager().get("remove_bg_plugin")
    result1 = plugin.run(image_path=BASE / "sample.png")
    result2 = plugin.run(image_path=BASE / "sample.png")
    assert Path(result1).exists() and Path(result2).exists(), "Плагин не сработал при повторном вызове"


def test_remove_background_missing_file():
    with pytest.raises(FileNotFoundError):
        remove_background(BASE / "not_existing_file.png")

def test_plugins_presence():
    names = get_plugin_manager().names
    for expected in ["remove_bg_plugin", "upscale_plugin"]:
        assert expected in names, f"Плагин '{expected}' не найден"


# Тест 11: Проверка создания нескольких сообщений
def test_multiple_messages_in_chat():
    session = ChatSession.create_new()
    session.add_message("user", "Привет!")
    session.add_message("assistant", "Здравствуйте!")
    session.save()

    loaded = ChatSession.load(session._path)
    assert len(loaded.messages) == 2, "Чат должен содержать 2 сообщения"
    assert loaded.messages[1].role == "assistant", "Роль второго сообщения неправильная"


# Тест 12: Проверка UUID уникальности чатов
def test_chat_uuid_uniqueness():
    session1 = ChatSession.create_new()
    session2 = ChatSession.create_new()
    assert session1.uuid != session2.uuid, "UUID разных чатов совпадают!"


# Тест 13: Проверка применения PIL апскейла при отсутствии RealESRGAN
from PIL import Image
def test_upscale_fallback_to_pil(monkeypatch, tmp_path):
    # Эмулируем отсутствие внешней утилиты
    monkeypatch.setattr("ai_design_assistant.core.image_utils.subprocess.run",
                        lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))

    src_image = BASE / "sample.png"
    result_path = apply_upscale(src_image)
    path = Path(result_path)

    assert path.exists(), "Файл после PIL-апскейла не существует"

    # Проверяем, что размер увеличился в 2 раза
    img = Image.open(path)
    orig = Image.open(src_image)

    expected_size = (orig.width * 2, orig.height * 2)
    assert img.size == expected_size, f"Размер изображения после PIL-апскейла неверный: {img.size}, ожидалось {expected_size}"


# Тест 14: Проверка удаления изображения после обработки
def test_temporary_image_removal(tmp_path):
    src = BASE / "sample.png"
    result_path = remove_background(src)
    assert Path(result_path).exists(), "Изображение после удаления фона не существует"

    # Удаляем файл после теста
    Path(result_path).unlink()
    assert not Path(result_path).exists(), "Изображение не удалилось"


# Тест 15: Проверка валидности base64 строки после декодирования
def test_valid_base64_decode():
    encoded = image_to_base64(BASE / "sample.png")
    header, data = encoded.split(",", 1)
    decoded = base64.b64decode(data)
    assert len(decoded) > 10, "Декодированная строка слишком мала"


# Тест 16: Проверка ошибок плагина на несуществующем файле
def test_plugin_fail_on_invalid_file():
    plugin = get_plugin_manager().get("remove_bg_plugin")
    with pytest.raises(Exception):
        plugin.run(image_path=BASE / "not_existing_file.png")


# Тест 17: Проверка повторной загрузки сессии без изменений
def test_chat_save_load_integrity():
    session = ChatSession.create_new()
    session.add_message("user", "Как дела?")
    session.save()

    loaded = ChatSession.load(session._path)
    reloaded = ChatSession.load(session._path)
    assert loaded.uuid == reloaded.uuid, "UUID должен сохраняться"
    assert loaded.messages[0].content == reloaded.messages[0].content, "Контент сообщения изменился!"


# Тест 18: Проверка наличия плагина upscale
def test_upscale_plugin_presence():
    names = get_plugin_manager().names
    assert "upscale_plugin" in names, "Плагин 'upscale_plugin' отсутствует в списке"


# Тест 19: Проверка вызова upscale_plugin
def test_upscale_plugin_run():
    plugin = get_plugin_manager().get("upscale_plugin")
    result_path = plugin.run(image_path=BASE / "sample.png")
    assert Path(result_path).exists(), "Плагин upscale_plugin не создал файл"


# Тест 20: Проверка MIME типа base64
def test_base64_mime_type():
    encoded = image_to_base64(BASE / "sample.png")
    header = encoded.split(",", 1)[0]
    assert "image" in header, "Base64 MIME header не содержит 'image'"

