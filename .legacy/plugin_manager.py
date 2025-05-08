"""
Plugin architecture for image‑processing modules.

Directory layout
----------------
project_root/
│
├── plugins/                       # each plugin = separate .py
│   ├── __init__.py
│   ├── upscale_plugin.py
│   └── remove_bg_plugin.py
│
├── plugin_manager.py              # loads plugins dynamically
└── ...

Usage in ui_layout.py:
    from ai_design_assistant.core.plugins import get_plugins
    plugins = get_plugins()
    for p in plugins.values():
        button = QPushButton(p.display_name)
        button.clicked.connect(lambda _, pl=p: run_plugin(pl))

Each plugin implements BaseImagePlugin defined below.
"""

import importlib
import pkgutil
from pathlib import Path
from typing import Protocol, runtime_checkable, Dict, List

PLUGIN_PACKAGE = "plugins"


@runtime_checkable
class BaseImagePlugin(Protocol):
    """Interface that every image plugin must implement."""

    display_name: str  # Caption for UI button

    @staticmethod
    def process(image_path: str, **kwargs) -> str:  # noqa: D401
        """Process *image_path* and return path to the resulting image."""
        ...

    # OPTIONAL: show a config dialog → return kwargs or None
    @ staticmethod
    def configure(parent, image_path: str) -> dict | None: ...

def _iter_module_names() -> List[str]:
    package = importlib.import_module(PLUGIN_PACKAGE)
    return [
        f"{PLUGIN_PACKAGE}.{name}"
        for _, name, _ in pkgutil.iter_modules(package.__path__)
    ]


def load_plugins() -> Dict[str, BaseImagePlugin]:
    """Import all modules in *plugins/* and return mapping {display_name: plugin}."""
    plugins: Dict[str, BaseImagePlugin] = {}
    for mod_name in _iter_module_names():
        module = importlib.import_module(mod_name)
        # Possible forms: whole module is plugin; module exposes Plugin class; simple funcs
        if isinstance(module, BaseImagePlugin):
            plugins[module.display_name] = module  # type: ignore[arg-type]
        elif hasattr(module, "Plugin"):
            plugin_cls = getattr(module, "Plugin")
            plugin = plugin_cls()
            plugins[plugin.display_name] = plugin
        elif hasattr(module, "process") and hasattr(module, "display_name"):
            plugins[module.display_name] = module  # type: ignore[arg-type]
    return plugins


# cache to avoid re‑loading every time
_PLUGINS_CACHE: Dict[str, BaseImagePlugin] | None = None


def get_plugins(refresh: bool = False) -> Dict[str, BaseImagePlugin]:
    """Public accessor with simple caching."""
    global _PLUGINS_CACHE
    if refresh or _PLUGINS_CACHE is None:
        _PLUGINS_CACHE = load_plugins()
    return _PLUGINS_CACHE


# ---------------- Example plugin skeletons ---------------- #

# File: plugins/upscale_plugin.py
"""
display_name = "Upscale ×2"

from modules import apply_upscale

def process(image_path: str, **kwargs):
    return apply_upscale(image_path, scale=2)
"""

# File: plugins/remove_bg_plugin.py
"""
display_name = "Remove BG"

from modules import remove_background

def process(image_path: str, **kwargs):
    return remove_background(image_path)
"""
