"""Sidebar widget that lists available plugins and lets the user run them.

UI-only; relies on :pyfile:`ai_design_assistant.core.plugins` for discovery.

Each plugin is shown as a *QPushButton* with its icon and display name. When
clicked, the plugin’s :pycode:`run()` method is executed in a background
thread using :class:`QThreadPool` and :class:`QRunnable` so the GUI stays
responsive.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from PyQt6.QtCore import QRunnable, Qt, QThreadPool, pyqtSignal, QObject
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ai_design_assistant.core.plugins import PluginMeta, get_plugin_manager

_LOGGER = logging.getLogger(__name__)
_RES_FALLBACK_ICON: Final = QIcon.fromTheme("applications-system")


class _PluginJob(QRunnable):
    """Runs a single plugin in a worker pool."""

    def __init__(self, name: str):
        super().__init__()
        self._name = name
        self.setAutoDelete(True)
        self._manager = get_plugin_manager()

    def run(self) -> None:  # noqa: D401 (imperative)
        plugin = self._manager.get(self._name)
        _LOGGER.info("Running plugin '%s'", self._name)
        try:
            plugin.run()  # noqa: ASSIGN
        except Exception as exc:  # pragma: no cover
            _LOGGER.exception("Plugin '%s' failed: %s", self._name, exc)


class PluginPanel(QWidget):
    """Scrollable list of plugin buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:  # noqa: D401
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._manager = get_plugin_manager()
        self._init_ui()

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _init_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setAlignment(Qt.AlignmentFlag.AlignTop)

        for meta in self._manager.metadata().values():
            vbox.addWidget(self._create_button(meta))

        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def _create_button(self, meta: PluginMeta) -> QWidget:
        button = QPushButton()
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        icon = QIcon(meta.icon_path) if meta.icon_path and Path(meta.icon_path).exists() else _RES_FALLBACK_ICON
        button.setIcon(icon)
        button.setText(meta.display_name)
        button.clicked.connect(lambda _=False, name=meta.name: self._run_plugin(name))

        # wrap with description label
        wrapper = QWidget()
        h = QHBoxLayout(wrapper)
        h.setContentsMargins(4, 4, 4, 4)
        h.addWidget(button)
        h.addWidget(QLabel(meta.description), 1)
        return wrapper

    # ------------------------------------------------------------------
    # Slot
    # ------------------------------------------------------------------
    def _run_plugin(self, name: str) -> None:  # noqa: D401 (imperative)
        job = _PluginJob(name)
        self._pool.start(job)
