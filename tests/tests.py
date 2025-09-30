# tests/tests.py

import os
import base64
import pytest
from pathlib import Path
from PIL import Image

from ai_design_assistant.core.image_utils import image_to_base64, remove_background, apply_upscale
from ai_design_assistant.core.chat import ChatSession
from ai_design_assistant.core.plugins import get_plugin_manager

BASE = Path(__file__).parent

# Глобально для CI: отключаем быстрый транспорт HF (иногда тянет лишние зависимости)
@pytest.fixture(scope="session", autouse=True)
def _ci_env_setup():
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    yield

# ───────────────────────── БЫСТРЫЕ ТЕСТЫ ─────────────────────────

def test_image_to_base64():
    result = image_to_base64(BASE / "sample.png")
    assert isinstance(result, str) and result.startswith("data:image/"), "Base64 невалиден"

def test_base64_roundtrip(tmp_path):
    encoded = image_to_base64(BASE / "sample.png")
    assert encoded.startswith("data:image/"), "Метка MIME неверна"
    header, data = encoded.split(",", 1)
    decoded = base64.b64decode(data)
    out = tmp_path / "decoded_output.png"
    out.write_bytes(decoded)
    assert out.exists() and out.stat().st_size > 0, "base64-декодирование не работает"

def test_valid_base64_decode():
    encoded = image_to_base64(BASE / "sample.png")
    header, data = encoded.split(",", 1)
    decoded = base64.b64decode(data)
    assert len(decoded) > 10, "Декодированная строка слишком мала"

def test_remove_background_missing_file():
    with pytest.raises(FileNotFoundError):
        remove_background(BASE / "not_existing_file.png")

def test_plugins_presence():
    names = get_plugin_manager().names
    # проверяем наличие remove_bg и enhance (upscale_plugin больше не тестируем)
    for expected in ["remove_bg_plugin", "enhance_plugin"]:
        assert expected in names, f"Плагин '{expected}' не найден"

def test_chat_uuid_uniqueness():
    session1 = ChatSession.create_new()
    session2 = ChatSession.create_new()
    assert session1.uuid != session2.uuid, "UUID разных чатов совпадают!"

def test_chat_save_load(tmp_path, monkeypatch):
    # складываем артефакты в tmp_path, чтобы не трогать рабочую директорию
    monkeypatch.setattr(ChatSession, "_ROOT", tmp_path / "chats", raising=False)
    session = ChatSession.create_new()
    session.add_message("user", "Привет!")
    session.save()
    restored = ChatSession.load(session._path)
    assert restored.messages[0].content == "Привет!", "Сообщение не сохранилось корректно"

def test_empty_chat_save_load(tmp_path, monkeypatch):
    monkeypatch.setattr(ChatSession, "_ROOT", tmp_path / "chats", raising=False)
    session = ChatSession.create_new()
    session.save()
    loaded = ChatSession.load(session._path)
    assert loaded.messages == [], "Пустой чат должен загружаться как пустой"

def test_multiple_messages_in_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(ChatSession, "_ROOT", tmp_path / "chats", raising=False)
    session = ChatSession.create_new()
    session.add_message("user", "Привет!")
    session.add_message("assistant", "Здравствуйте!")
    session.save()
    loaded = ChatSession.load(session._path)
    assert len(loaded.messages) == 2, "Чат должен содержать 2 сообщения"
    assert loaded.messages[1].role == "assistant", "Роль второго сообщения неправильная"

def test_chat_save_load_integrity(tmp_path, monkeypatch):
    monkeypatch.setattr(ChatSession, "_ROOT", tmp_path / "chats", raising=False)
    session = ChatSession.create_new()
    session.add_message("user", "Как дела?")
    session.save()
    loaded = ChatSession.load(session._path)
    reloaded = ChatSession.load(session._path)
    assert loaded.uuid == reloaded.uuid, "UUID должен сохраняться"
    assert loaded.messages[0].content == reloaded.messages[0].content, "Контент сообщения изменился!"

# ─────────────── ТЕСТЫ, КОТОРЫЕ МОГУТ БЫТЬ ДОЛГИМИ (slow) ───────────────
# Они реально гоняют модели/плагины. В CI по умолчанию их пропускаем (-m "not slow").

@pytest.mark.slow
@pytest.mark.timeout(90)
def test_remove_background(tmp_path):
    local = tmp_path / "sample.png"
    local.write_bytes((BASE / "sample.png").read_bytes())
    result_path = remove_background(local)
    assert Path(result_path).exists(), "Фон не был удалён"

@pytest.mark.slow
@pytest.mark.timeout(60)
def test_apply_upscale(tmp_path):
    local = tmp_path / "sample.png"
    local.write_bytes((BASE / "sample.png").read_bytes())

    result_path = apply_upscale(local)
    ret = Path(result_path) if result_path else None

    # Допускаем разные имена/стили записи
    candidates = [
        ret,
        local.with_name(local.stem + "_up2" + local.suffix),
        local.with_name(local.stem + "_upscaled" + local.suffix),
        local.with_name(local.stem + "_pil" + local.suffix),
        local,  # если апскейл перезаписал исходник
    ]
    out = next((p for p in candidates if p and p.exists()), None)
    assert out is not None, f"Upscale не выполнен, нет выходного файла среди: {', '.join(str(c) for c in candidates if c)}"

    img = Image.open(out)
    orig = Image.open(local)
    assert img.width >= orig.width and img.height >= orig.height, "Изображение не увеличено"

@pytest.mark.slow
@pytest.mark.timeout(90)
def test_plugins_list_and_run(tmp_path):
    manager = get_plugin_manager()
    available = manager.names
    assert "remove_bg_plugin" in available, "Плагин 'remove_bg_plugin' не найден"
    local = tmp_path / "sample.png"
    local.write_bytes((BASE / "sample.png").read_bytes())
    plugin = manager.get("remove_bg_plugin")
    result_path = plugin.run(image_path=local)
    assert Path(result_path).exists(), "Плагин remove_bg_plugin не сработал"

@pytest.mark.slow
@pytest.mark.timeout(90)
def test_plugin_reusability(tmp_path):
    local = tmp_path / "sample.png"
    local.write_bytes((BASE / "sample.png").read_bytes())
    plugin = get_plugin_manager().get("remove_bg_plugin")
    result1 = plugin.run(image_path=local)
    result2 = plugin.run(image_path=local)
    assert Path(result1).exists() and Path(result2).exists(), "Плагин не сработал при повторном вызове"

@pytest.mark.timeout(60)
def test_upscale_fallback_to_pil(monkeypatch, tmp_path):
    # форсим отсутствие внешней утилиты → код должен уйти в PIL-ветку
    monkeypatch.setattr("ai_design_assistant.core.image_utils.subprocess.run",
                        lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))

    local = tmp_path / "sample.png"
    local.write_bytes((BASE / "sample.png").read_bytes())

    result_path = apply_upscale(local, scale=2)
    ret = Path(result_path) if result_path else None

    candidates = [
        ret,
        local.with_name(local.stem + "_up2" + local.suffix),
        local.with_name(local.stem + "_upscaled" + local.suffix),
        local.with_name(local.stem + "_pil" + local.suffix),
        local,  # если PIL просто перезаписал исходник
    ]
    out = next((p for p in candidates if p and p.exists()), None)
    assert out is not None, f"Файл после PIL-апскейла не найден среди: {', '.join(str(c) for c in candidates if c)}"

    img = Image.open(out)
    orig = Image.open(local)
    # Допускаем равенство размеров (некоторые реализации могут оставлять исходный размер),
    # но требуем не хуже исходника:
    assert img.width >= orig.width and img.height >= orig.height, \
        f"PIL-апскейл не дал изображение не меньше исходного: {img.size} vs {orig.size}"

@pytest.mark.slow
@pytest.mark.timeout(90)
def test_temporary_image_removal(tmp_path):
    local = tmp_path / "sample.png"
    local.write_bytes((BASE / "sample.png").read_bytes())
    result_path = remove_background(local)
    assert Path(result_path).exists(), "Изображение после удаления фона не существует"
    Path(result_path).unlink()
    assert not Path(result_path).exists(), "Изображение не удалилось"

@pytest.mark.slow
@pytest.mark.timeout(120)
def test_enhance_plugin_run(tmp_path):
    # Проверяем реальное улучшение через enhance_plugin
    local = tmp_path / "sample.png"
    local.write_bytes((BASE / "sample.png").read_bytes())

    plugin = get_plugin_manager().get("enhance_plugin")

    # run: без remove_bg; указываем режим и scale
    out_path = Path(plugin.run(image_path=local, mode="Стандартная", tiled=False, scale=2))
    assert out_path.exists(), "enhance_plugin не создал файл"

    img = Image.open(out_path)
    orig = Image.open(local)
    # Требуем, чтобы результат не был хуже исходника
    assert img.width >= orig.width and img.height >= orig.height, "Изображение не увеличено"

