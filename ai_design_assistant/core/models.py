"""
Безопасный слой абстракции над LLM-бекендами.

* Никогда не падает при импорте: все необязательные зависимости ловятся.
* Даже если бекендов нет, класс `LLMRouter` объявляется,
  чтобы UI не схлопнулся.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Protocol, runtime_checkable

_LOGGER = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────
#  Контракт бекенда
# ────────────────────────────────────────────────────────────────────
@runtime_checkable
class ModelBackend(Protocol):
    """Минимальный интерфейс LLM-бекенда."""

    name: str

    def generate(self, messages: List[dict[str, str]], **kwargs) -> str: ...


_BACKENDS: Dict[str, ModelBackend] = {}


def register_backend(backend: ModelBackend) -> None:
    """Добавить реализованный бекенд в реестр."""
    if backend.name in _BACKENDS:
        _LOGGER.debug("Backend %s already зарегистрирован — пропускаю", backend.name)
        return
    _BACKENDS[backend.name] = backend
    _LOGGER.info("Backend %s зарегистрирован", backend.name)


# ai_design_assistant/core/models.py  ─────────────────────────────────
def _to_dict(m):                                  # new helper
    return {"role": m.role, "content": m.content} if hasattr(m, "role") else m

def normalize(messages: list) -> list[dict[str, str]]:   # noqa: D401
    """Преобразовать список Message|dict → список dict."""
    return [_to_dict(m) for m in messages]


# ────────────────────────────────────────────────────────────────────
#  Пытаемся подхватить встроенные/необязательные бекенды
# ────────────────────────────────────────────────────────────────────
for _module in (
    "ai_design_assistant.api.openai_backend",
    "ai_design_assistant.api.deepseek_backend",
):
    try:
        mod = __import__(_module, fromlist=["backend"])
        register_backend(mod.backend)  # каждый модуль обязан экспонировать .backend
    except ModuleNotFoundError:
        _LOGGER.info("Optional backend %s не найден — пропускаю", _module)
    except Exception as exc:  # pragma: no cover
        _LOGGER.warning("Не удалось инициализировать %s: %s", _module, exc)


# ────────────────────────────────────────────────────────────────────
#  Роутер, который UI вызывает для общения с LLM
# ────────────────────────────────────────────────────────────────────
class LLMRouter:
    """Простой диспетчер запросов к LLM-бекендам."""

    def __init__(self, default: str | None = None) -> None:
        self._default = default or (next(iter(_BACKENDS)) if _BACKENDS else None)

    @property
    def backends(self) -> list[str]:
        return list(_BACKENDS)

    # основной режим – получить весь ответ целиком
    def chat(self, messages: list[dict[str, str]], backend: str | None = None, **kw) -> str:
        if not _BACKENDS:
            raise RuntimeError("Нет доступных LLM-бекендов")
        name = backend or self._default
        if name not in _BACKENDS:
            raise ValueError(f"Бекенд «{name}» не зарегистрирован")
        return _BACKENDS[name].generate(messages, **kw)

    # потоковая версия; если бекенд не умеет стриминг – возвращаем всё сразу
    def stream(self, messages: list[dict[str, str]], backend: str | None = None, **kw):
        if not _BACKENDS:
            raise RuntimeError("Нет доступных LLM-бекендов")
        name = backend or self._default
        if name not in _BACKENDS:
            raise ValueError(f"Бекенд «{name}» не зарегистрирован")

        gen = getattr(_BACKENDS[name], "stream", None)
        if callable(gen):
            yield from gen(messages, **kw)          # настоящий стрим
        else:
            yield self._BACKENDS[name].generate(messages, **kw)  # one-shot

