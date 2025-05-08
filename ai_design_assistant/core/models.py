"""Unified access to multiple LLM back‑ends.

Supported today
---------------
* openai   – via existing openai_api.stream_chat_response
* deepseek – via deepseek_api.stream_chat_response (stub if unimplemented)

Configuration stored in settings.json under key "llm".
"""
from typing import Iterator, Tuple, Any, Dict, Callable
from ai_design_assistant.core.settings import load_settings, save_settings
from ai_design_assistant.core.settings import AppSettings
from ai_design_assistant.api import openai_api, deepseek_api
import openai

# If deepseek_api lacks stream_chat_response, stub it
def _get_deepseek_fn() -> Callable[..., Iterator[Tuple[str, Any]]]:
    if hasattr(deepseek_api, 'stream_chat_response'):
        return deepseek_api.stream_chat_response
    # stub that raises clear error when called
    def _stub(user_text: str, image_path: Any = None) -> Iterator[Tuple[str, Any]]:
        raise NotImplementedError("DeepSeek backend not implemented")
    return _stub

# Mapping model key to (Display Name, streaming function)
BACKENDS: Dict[str, Tuple[str, Callable[[str, Any], Iterator[Tuple[str, Any]]]]]
BACKENDS = {
    "openai":   ("OpenAI", openai_api.stream_chat_response),
    "deepseek": ("DeepSeek", _get_deepseek_fn()),
}

DEFAULT_MODEL = "openai"
MODEL_SETTING_KEY = "llm"


def list_models() -> list[str]:
    """Return list of available model keys."""
    return list(BACKENDS.keys())


def get_current_model() -> str:
    """Return the currently selected model key, default if unset."""
    settings = load_settings()
    return settings.get(MODEL_SETTING_KEY, DEFAULT_MODEL)


def set_current_model(model: str) -> None:
    """Set the current model key and persist to settings."""
    if model not in BACKENDS:
        raise ValueError(f"Unknown model '{model}'")
    settings = load_settings()
    settings[MODEL_SETTING_KEY] = model
    save_settings(settings)


def stream_chat_response(user_text: str, image_path: Any = None) -> Iterator[Tuple[str, Any]]:
    """Route the streaming call to the selected backend."""
    model = get_current_model()
    display_name, func = BACKENDS.get(model, BACKENDS[DEFAULT_MODEL])
    # Если работаем с OpenAI — подхватываем свежий ключ из .env/AppSettings
    if model == "openai":
        new_key = AppSettings.openai_key()
    if openai.api_key != new_key:
        openai.api_key = new_key

    yield from func(user_text, image_path=image_path)
