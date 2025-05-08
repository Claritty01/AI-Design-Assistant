"""Init: просто импортируем все реaльные backend-модули,
чтобы они сами зарегистрировались в глобальном роутере."""
from importlib import import_module
import logging

_LOGGER = logging.getLogger(__name__)

for _name in ("openai_backend", "deepseek_backend", "local_backend"):
    try:
        import_module(f"{__name__}.{_name}")
    except Exception as exc:            # noqa: BLE001
        # не фатально: ключа может не быть, сервер может быть недоступен
        _LOGGER.warning("Skip %s – %s", _name, exc)
