"""Application entry point for AI Design Assistant.

Responsible for:
* loading environment variables (via Settings.load_dotenv)
* configuring global logging
* boot‑strapping the Qt application and showing the main window

To run during development:
    poetry run ada
or
    python -m ai_design_assistant
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication

from ai_design_assistant.ui.main_window import MainWindow
from ai_design_assistant.core.settings import Settings
from ai_design_assistant.core.logger import configure_logging



def main() -> None:
    """Launch the Qt GUI application."""
    # When packaged with PyInstaller, change cwd so relative resource paths work
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).parent)

    # 1️⃣  Environment & settings
    Settings.load_dotenv()  # picks up .env or system variables

    # 2️⃣  Logging (console + rotating file handler)
    configure_logging()

    # 3️⃣  Qt application boot‑strap
    QCoreApplication.setOrganizationName("AI Design Assistant")
    app = QApplication(sys.argv)

    # 5️⃣  Применяем тему до создания MainWindow
    from ai_design_assistant.ui.theme_utils import load_stylesheet
    style = load_stylesheet(Settings.load().theme)
    app.setStyleSheet(style)

    # 6️⃣ Main UI
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
