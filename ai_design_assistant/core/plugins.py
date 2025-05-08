"""Simple plugin infrastructure (core layer).

Plugins are Python packages that expose an entry point in the group
``ai_design_assistant.plugins``. Each entry point must provide a subclass of
:class:`BasePlugin`.

The **UI** layer queries :class:`PluginManager` for available plugins, shows
buttons, and calls :pycode:`plugin.run(**kwargs)` in a background thread.

Example *pyproject.toml* entry::

    [project.entry-points."ai_design_assistant.plugins"]
    remove_bg = "ada_remove_bg.plugin:RemoveBGPlugin"
"""
from __future__ import annotations

import importlib.metadata as importlib_metadata
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Final, Mapping, MutableMapping
import importlib
import pkgutil
import sys
import importlib
import importlib.metadata as importlib_metadata
import logging
import pkgutil
from typing import Final, Mapping, MutableMapping




_LOGGER = logging.getLogger(__name__)
_ENTRYPOINT_GROUP: Final = "ai_design_assistant.plugins"


@dataclass
class PluginMeta:
    """Lightweight metadata struct returned by manager to the UI."""

    name: str
    display_name: str
    description: str
    icon_path: str | None = None


class BasePlugin(ABC):
    """Base class all plugins must inherit."""

    #: human‑readable name (shown in UI)
    display_name: str = "Unnamed plugin"
    #: short description
    description: str = "No description"
    #: optional path to icon file (png/svg)
    icon_path: str | None = None

    @abstractmethod
    def run(self, **kwargs):  # noqa: D401 (imperative)
        """Entry point called by UI (may block)."""
        raise NotImplementedError

    # you may override if need per‑instance state
    def __init__(self):
        super().__init__()


class PluginManager:
    """Loads entry‑point plugins and provides access to them."""

    def __init__(self) -> None:
        self._plugins: MutableMapping[str, BasePlugin] = {}
        self._load_entrypoints()
        self._load_builtin()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def _load_entrypoints(self) -> None:
        for ep in importlib_metadata.entry_points(group=_ENTRYPOINT_GROUP):
            name = ep.name
            try:
                plugin_cls = ep.load()
                if not issubclass(plugin_cls, BasePlugin):  # type: ignore[arg-type]
                    raise TypeError("Plugin class must inherit BasePlugin")
                instance: BasePlugin = plugin_cls()
                self._plugins[name] = instance
                _LOGGER.info("Plugin '%s' loaded (%s)", name, plugin_cls)
            except Exception as exc:  # pragma: no cover
                _LOGGER.warning("Failed to load plugin '%s': %s", name, exc)

    # ------------------------------------------------------------------
    #  Fallback: плагины, лежащие в пакете ai_design_assistant.plugins
    # ------------------------------------------------------------------
    def _load_builtin(self) -> None:
        """Ищет встроенные плагины, если они не объявлены entry-point’ами."""
        try:
            import ai_design_assistant.plugins as _pkg
        except ModuleNotFoundError:
            return

        core_mod = f"{__name__}.BaseImagePlugin"
        for _, mod_name, _ in pkgutil.iter_modules(_pkg.__path__):
            if mod_name in self._plugins:        # уже загружен как entry-point
                continue

            full = f"{_pkg.__name__}.{mod_name}"
            try:
                module = importlib.import_module(full)
            except Exception as exc:
                _LOGGER.warning("Builtin plugin %s → %s", full, exc)
                continue

            # 1) новый стиль — класс-потомок BasePlugin
            cls = next(
                (
                    attr for attr in vars(module).values()
                    if isinstance(attr, type)
                    and issubclass(attr, BasePlugin)
                    and attr is not BasePlugin
                    and f"{attr.__module__}.{attr.__name__}" != core_mod
                ),
                None,
            )
            if cls:
                try:
                    self._plugins[mod_name] = cls()
                except Exception as exc:
                    _LOGGER.warning("Cannot init %s: %s", cls, exc)
                continue

            # 2) старый стиль — функция process()
            if hasattr(module, "process"):

                class _Adapter(BasePlugin):               # type: ignore
                    display_name = getattr(
                        module, "display_name", mod_name.capitalize()
                    )
                    description = (module.__doc__ or "").splitlines()[0]

                    def run(self, **kwargs):              # noqa: D401
                        return module.process(**kwargs)

                self._plugins[mod_name] = _Adapter()


    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._plugins)

    def get(self, name: str) -> BasePlugin:
        return self._plugins[name]

    def metadata(self) -> Mapping[str, PluginMeta]:
        return {
            name: PluginMeta(
                name=name,
                display_name=plugin.display_name,
                description=plugin.description,
                icon_path=plugin.icon_path,
            )
            for name, plugin in self._plugins.items()
        }


# global helper
_plugin_manager: PluginManager | None = None

def get_plugin_manager() -> PluginManager:  # noqa: D401 (imperative)
    global _plugin_manager  # noqa: PLW0603
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager

class BaseImagePlugin(BasePlugin):
    """Базовый класс для плагинов, работающих с изображениями."""
    def run(self, **kwargs):
        raise NotImplementedError

