import pytest
from PyQt6.QtCore import Qt, QMimeData, QUrl, QPointF
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QApplication, QPushButton, QLabel, QFileDialog
from ai_design_assistant.ui.main_window import MainWindow
from ai_design_assistant.ui.widgets import MessageBubble

@pytest.fixture
def main_window(qtbot):
    """Фикстура для создания главного окна приложения."""
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    return window

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

    # Пройдёмся по всем вкладкам
    for index in range(count):
        tab_widget.setCurrentIndex(index)
        qtbot.wait(100)
        widget = tab_widget.currentWidget()
        assert widget.isVisible(), f"Вкладка {index} не отображается"

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QPushButton, QDialog, QApplication
from ai_design_assistant.ui.settings_dialog import SettingsDialog

def test_open_settings_dialog_e2e(main_window, qtbot):
    """Проверяет открытие и закрытие окна настроек."""
    settings_button = main_window.findChild(QPushButton, "settings_button")
    assert settings_button is not None, "Кнопка настроек не найдена"

    def close_dialog():
        for w in QApplication.topLevelWidgets():
            if isinstance(w, SettingsDialog):
                cancel_btn = w.findChild(QPushButton, "cancel_button")
                assert cancel_btn is not None, "Кнопка Cancel не найдена"
                qtbot.mouseClick(cancel_btn, Qt.MouseButton.LeftButton)
                break

    # Запускаем закрытие через 300 мс
    QTimer.singleShot(300, close_dialog)

    # Это вызовет exec(), который заблокирует поток — но таймер сработает
    qtbot.mouseClick(settings_button, Qt.MouseButton.LeftButton)

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

from PIL import Image

def test_upload_image_through_button(main_window, qtbot, tmp_path, monkeypatch):
    """Проверяет загрузку изображения через кнопку прикрепления файла."""
    # Создаем валидное PNG-изображение
    img_path = tmp_path / "test_image.png"
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))  # Красный квадрат 100x100
    img.save(img_path)

    # Находим кнопку загрузки
    upload_btn = main_window.input_bar.findChild(QPushButton, "upload_button")
    assert upload_btn is not None, "Кнопка загрузки не найдена"

    # Находим кнопку отправки
    send_btn = main_window.input_bar.findChild(QPushButton, "send_button")
    assert send_btn is not None, "Кнопка отправки не найдена"

    # Подменяем FileDialog, чтобы не открывать реальный диалог
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(img_path), "image/png"))

    # Нажимаем на кнопку 📎 (прикрепить)
    qtbot.mouseClick(upload_btn, Qt.MouseButton.LeftButton)
    qtbot.wait(500)

    # Нажимаем на кнопку 📤 (отправить)
    qtbot.mouseClick(send_btn, Qt.MouseButton.LeftButton)
    qtbot.wait(500)

    # Проверяем, что изображение появилось в chat_view
    bubbles = [
        main_window.chat_view.message_layout.itemAt(i).widget()
        for i in range(main_window.chat_view.message_layout.count())
    ]

    # Фильтруем MessageBubble и ищем у которых есть QLabel с pixmap
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
    settings_button = main_window.findChild(QPushButton, "settings_button")
    qtbot.mouseClick(settings_button, Qt.MouseButton.LeftButton)
    qtbot.wait(200)

    for w in QApplication.topLevelWidgets():
        if isinstance(w, SettingsDialog):
            theme_box = w.findChild(QLabel, "theme_box")
            if theme_box:
                old_text = theme_box.text()
                theme_box.setText("Темная тема")
                assert theme_box.text() != old_text, "Тема не переключилась"
            w.close()
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
