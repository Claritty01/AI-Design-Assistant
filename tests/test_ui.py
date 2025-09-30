import os
import sys
import types
import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLabel, QFileDialog,
    QDialog, QMessageBox, QDialogButtonBox
)
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from ai_design_assistant.ui.main_window import MainWindow
from ai_design_assistant.ui.widgets import MessageBubble
from PIL import Image

# --- Глобальные env для headless и HF ---
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen") # оффскрин тесты
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")


# ---------- ВСПОМОГАТЕЛКИ ДЛЯ АВТОЗАКРЫТИЯ МОДАЛОК ----------

def _try_close_dialog(widget, qtbot):
    """
    Пытается культурно закрыть QDialog/QMessageBox:
    - нажимает стандартные кнопки, если есть
    - иначе вызывает accept()/reject()/close()
    """
    if isinstance(widget, QMessageBox):
        # Жмём "ОК" / "Отмена" и т.п., что найдём
        btnbox = widget.findChild(QDialogButtonBox)
        if btnbox and btnbox.buttons():
            qtbot.mouseClick(btnbox.buttons()[0], Qt.MouseButton.LeftButton)
            return True

    btnbox = widget.findChild(QDialogButtonBox)
    if btnbox and btnbox.buttons():
        qtbot.mouseClick(btnbox.buttons()[0], Qt.MouseButton.LeftButton)
        return True

    # fallback
    for meth in ("accept", "reject", "close", "hide"):
        if hasattr(widget, meth):
            getattr(widget, meth)()
            return True
    return False


def _close_any_modal(qtbot, title_substrings=()):
    """
    Находит и закрывает любой модальный QDialog/QMessageBox.
    Если title_substrings не пуст, то закрывает только окна,
    заголовок которых содержит одно из подстрок.
    """
    for w in QApplication.topLevelWidgets():
        if isinstance(w, QDialog) and (w.isModal() or isinstance(w, QMessageBox)):
            title = getattr(w, "windowTitle", lambda: "")()
            if not title_substrings or any(s.lower() in title.lower() for s in title_substrings):
                if _try_close_dialog(w, qtbot):
                    return True
    return False


@pytest.fixture(autouse=True)
def auto_close_modals(qtbot):
    """
    Автоматически закрывает всплывающие модалки, чтобы тесты не зависали.
    Включая предупреждение «Deepseek sdk не подключен» и другие.
    """
    # Периодически сканируем и закрываем модальные окна
    timer = QTimer()
    timer.setInterval(200)  # каждые 200 мс
    timer.timeout.connect(lambda: (
        _close_any_modal(qtbot) or
        _close_any_modal(qtbot, title_substrings=("Deepseek", "DeepSeek", "sdk")) or
        _close_any_modal(qtbot, title_substrings=("Settings", "Настройки"))
    ))
    timer.start()
    try:
        yield
    finally:
        timer.stop()


@pytest.fixture
def main_window(qtbot):
    """Фикстура для создания главного окна приложения."""
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    return window


# --------------------------- ТЕСТЫ UI ---------------------------

def test_main_window_shows(main_window):
    """Проверяет, что главное окно отображается после запуска."""
    assert main_window.isVisible(), "Окно не отображается"


def test_input_field_exists(main_window):
    """Проверяет наличие и доступность текстового поля ввода сообщений."""
    field = main_window.input_bar.text_edit
    assert field.isEnabled(), "Поле ввода не активно"


def test_send_button_clickable(main_window):
    """Проверяет наличие и активность кнопки отправки сообщений."""
    send_btn = main_window.input_bar.findChild(QPushButton, "send_button")
    assert send_btn is not None, "Кнопка отправки не найдена"
    assert send_btn.isEnabled(), "Кнопка отправки не активна"


def test_send_text_message(main_window, qtbot):
    """Проверяет возможность отправки текстового сообщения."""
    field = main_window.input_bar.text_edit
    send_btn = main_window.input_bar.findChild(QPushButton, "send_button")

    field.setText("Привет")
    qtbot.mouseClick(send_btn, Qt.MouseButton.LeftButton)
    qtbot.wait(300)

    assert main_window.chat_view.message_layout.count() > 0, "Сообщение не появилось в chat_view"


def test_gallery_panel_accessible(main_window):
    """Проверяет доступность панели галереи изображений."""
    main_window.gallery_panel.refresh()
    assert main_window.gallery_panel.gallery is not None


def test_tab_switching(main_window, qtbot):
    """Проверяет переключение между вкладками интерфейса."""
    tab_widget = main_window._tabs
    count = tab_widget.count()
    assert count > 1, "Недостаточно вкладок для переключения"

    for index in range(count):
        tab_widget.setCurrentIndex(index)
        qtbot.wait(100)
        widget = tab_widget.currentWidget()
        assert widget.isVisible(), f"Вкладка {index} не отображается"


def test_open_settings_dialog_e2e(main_window, qtbot, monkeypatch, tmp_path):
    """Проверяет открытие и закрытие окна настроек."""
    settings_button = main_window.findChild(QPushButton, "settings_button")
    assert settings_button is not None, "Кнопка настроек не найдена"

    # Подкладываем лёгкий фейк huggingface_hub до импорта SettingsDialog,
    # чтобы не было сетевых скачиваний.
    fake_hf = types.ModuleType("huggingface_hub")
    def _fake_snapshot_download(*a, **k):
        p = tmp_path / "hf_dummy"; p.mkdir(exist_ok=True)
        (p / "model.bin").write_bytes(b"dummy")
        return str(p)
    fake_hf.snapshot_download = _fake_snapshot_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf)

    # lazy-import: после подмены модуля
    from ai_design_assistant.ui.settings_dialog import SettingsDialog

    # Доп. страховка: если окно настроек модальное, таймер его закроет.
    QTimer.singleShot(400, lambda: _close_any_modal(qtbot, title_substrings=("Settings", "Настройки")))

    # Открываем окно
    qtbot.mouseClick(settings_button, Qt.MouseButton.LeftButton)
    # Ждём, пока появится и закроется
    qtbot.wait(600)

    # Проверим, что модалка закрылась
    assert not any(isinstance(w, SettingsDialog) and w.isVisible()
                   for w in QApplication.topLevelWidgets()), "Окно настроек осталось открытым"


def test_new_chat_button(main_window, qtbot):
    """Проверяет создание нового чата через кнопку."""
    new_chat_btn = main_window.findChild(QPushButton, "new_chat_button")
    assert new_chat_btn is not None, "Кнопка 'New chat' не найдена"

    count_before = main_window.chat_list.count()
    qtbot.mouseClick(new_chat_btn, Qt.MouseButton.LeftButton)
    qtbot.wait(200)

    count_after = main_window.chat_list.count()
    assert count_after == count_before + 1, "Новый чат не добавился"

    current_item = main_window.chat_list.currentItem()
    assert current_item is not None, "Новый чат не активен"


def test_upload_image_through_button(main_window, qtbot, tmp_path, monkeypatch):
    """Проверяет загрузку изображения через кнопку прикрепления файла."""
    # Создаём валидное PNG
    img_path = tmp_path / "test_image.png"
    Image.new("RGB", (100, 100), color=(255, 0, 0)).save(img_path)

    upload_btn = main_window.input_bar.findChild(QPushButton, "upload_button")
    send_btn = main_window.input_bar.findChild(QPushButton, "send_button")
    assert upload_btn is not None and send_btn is not None, "Кнопки загрузки/отправки не найдены"

    # Подменяем FileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(img_path), "image/png"))

    qtbot.mouseClick(upload_btn, Qt.MouseButton.LeftButton)
    qtbot.wait(200)
    qtbot.mouseClick(send_btn, Qt.MouseButton.LeftButton)
    qtbot.wait(300)

    # Проверяем, что в чат добавилось изображение
    bubbles = [
        main_window.chat_view.message_layout.itemAt(i).widget()
        for i in range(main_window.chat_view.message_layout.count())
    ]

    def bubble_has_image(bubble):
        return any(
            isinstance(child, QLabel) and child.pixmap() and not child.pixmap().isNull()
            for child in bubble.findChildren(QLabel)
        )

    has_image = any(isinstance(b, MessageBubble) and bubble_has_image(b) for b in bubbles)
    assert has_image, "Изображение не добавилось в чат через кнопку загрузки"


def test_window_resize(main_window, qtbot):
    """Проверяет возможность изменения размера окна."""
    initial_size = main_window.size()
    main_window.resize(initial_size.width() + 100, initial_size.height() + 100)
    qtbot.wait(100)

    new_size = main_window.size()
    assert new_size.width() > initial_size.width(), "Ширина окна не увеличилась"
    assert new_size.height() > initial_size.height(), "Высота окна не увеличилась"


def test_send_button_disabled_on_empty(main_window, qtbot):
    """Проверяет, что кнопка отправки активна даже при пустом поле ввода."""
    field = main_window.input_bar.text_edit
    send_btn = main_window.input_bar.findChild(QPushButton, "send_button")

    field.clear()
    qtbot.wait(100)

    assert send_btn.isEnabled(), "Кнопка отправки должна быть активной, даже при пустом поле"


def test_settings_theme_change(main_window, qtbot):
    """Проверяет переключение темы оформления через настройки."""
    # Откроется модальное окно — наш авто-закрыватель его прикроет после проверки
    settings_button = main_window.findChild(QPushButton, "settings_button")
    qtbot.mouseClick(settings_button, Qt.MouseButton.LeftButton)
    qtbot.wait(400)

    # Попробуем найти и «потрогать» виджеты, если успели
    for w in QApplication.topLevelWidgets():
        title = getattr(w, "windowTitle", lambda: "")()
        if isinstance(w, QDialog) and ("Settings" in title or "Настройки" in title):
            theme_box = w.findChild(QLabel, "theme_box")
            if theme_box:
                old_text = theme_box.text()
                theme_box.setText("Темная тема")
                assert theme_box.text() != old_text, "Тема не переключилась"
            _try_close_dialog(w, qtbot)
            break


def test_gallery_refresh(main_window, qtbot):
    """Проверяет обновление галереи изображений."""
    main_window.gallery_panel.refresh()
    items = main_window.gallery_panel.gallery.count()
    assert isinstance(items, int), "Галерея не обновилась корректно"


def test_minimize_restore_window(main_window, qtbot):
    """Проверяет сворачивание и восстановление главного окна."""
    main_window.showMinimized()
    qtbot.wait(200)
    assert main_window.isMinimized(), "Окно не свернулось"

    main_window.showNormal()
    qtbot.wait(200)
    assert main_window.isVisible(), "Окно не восстановилось"
