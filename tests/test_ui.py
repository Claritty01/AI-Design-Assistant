# tests/test_ui.py

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QPushButton
from ai_design_assistant.ui.main_window import MainWindow

@pytest.fixture
def main_window(qtbot):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    return window

def test_main_window_shows(main_window):
    assert main_window.isVisible(), "Окно не отображается"


def test_input_field_exists(main_window):
    field = main_window.input_bar.text_edit
    assert field.isEnabled(), "Поле ввода не активно"


def test_send_button_clickable(main_window):
    send_btn = main_window.input_bar.findChild(QPushButton, "send_button")
    assert send_btn is not None, "Кнопка отправки не найдена"
    assert send_btn.isEnabled(), "Кнопка отправки не активна"


def test_send_text_message(main_window, qtbot):
    field = main_window.input_bar.text_edit
    send_btn = main_window.input_bar.findChild(QPushButton, "send_button")

    field.setText("Привет")
    qtbot.mouseClick(send_btn, Qt.MouseButton.LeftButton)
    qtbot.wait(300)

    assert main_window.chat_view.message_layout.count() > 0, "Сообщение не появилось в chat_view"


def test_gallery_panel_accessible(main_window):
    main_window.gallery_panel.refresh()
    assert main_window.gallery_panel.gallery is not None


def test_tab_switching(main_window, qtbot):
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


from PyQt6.QtWidgets import QPushButton

def test_new_chat_button(main_window, qtbot):
    new_chat_btn = main_window.findChild(QPushButton, "new_chat_button")
    assert new_chat_btn is not None, "Кнопка 'New chat' не найдена"

    count_before = main_window.chat_list.count()

    qtbot.mouseClick(new_chat_btn, Qt.MouseButton.LeftButton)
    qtbot.wait(200)

    count_after = main_window.chat_list.count()
    assert count_after == count_before + 1, "Новый чат не добавился"

    current_item = main_window.chat_list.currentItem()
    assert current_item is not None, "Новый чат не активен"



