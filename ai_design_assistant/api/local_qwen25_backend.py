# ai_design_assistant/api/local_qwen25_backend.py
from __future__ import annotations
import os, threading, base64, logging
from pathlib import Path
from io import BytesIO
from typing import Iterator, List

from PIL import Image
import torch
from transformers import (
    Qwen2_5_VLForConditionalGeneration,
    AutoProcessor,
    TextIteratorStreamer,
)

from ai_design_assistant.core.settings import Settings
from ai_design_assistant.core.models import ModelBackend, normalize

_LOGGER = logging.getLogger(__name__)

# ───────────────────────────────────────────
_MODEL_NAME = os.getenv(
    "LOCAL_MODEL_NAME",               # можно переопределить переменной окружения
    "Qwen/Qwen2.5-VL-3B-Instruct",
)
_DEVICE     = "cuda" if torch.cuda.is_available() else "cpu"
_DTYPE      = torch.float16 if _DEVICE == "cuda" else torch.float32
_MAX_TOKENS = int(os.getenv("LOCAL_MAX_NEW_TOKENS", "1024"))
# ───────────────────────────────────────────


def _prepare_processor(proc, patch_size: int = 14):
    """У Qwen-VL уже есть patch_size, но оставим проверку."""
    if getattr(proc, "patch_size", None) is None:
        proc.patch_size = patch_size
    if getattr(proc.image_processor, "patch_size", None) is None:
        proc.image_processor.patch_size = patch_size


def _decode_data_url(data_url: str) -> Image.Image:
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    return Image.open(BytesIO(base64.b64decode(data_url))).convert("RGB")


def _collapse_messages(messages: List[dict]):
    """Возвращает history и последнюю картинку (если есть)."""
    image: Image.Image | None = None
    out = []
    for m in messages:
        content = m["content"]
        parts = []

        if isinstance(content, list):
            for chunk in content:
                if chunk["type"] == "text":
                    parts.append(chunk["text"])
                elif chunk["type"] == "image_url":
                    parts.append("<img>")    # картинка внутри текста
        else:
            # content — строка
            parts.append(content)
            if m.get("image"):
                parts.append("<img>")       # 👈 вставляем <img> если есть поле image

        content = " ".join(parts)
        out.append({"role": m["role"], "content": content})

    # Найти последнюю картинку в истории сообщений
    for m in reversed(messages):
        if isinstance(m["content"], list):
            for chunk in m["content"]:
                if chunk["type"] == "image_url":
                    image = _decode_data_url(chunk["image_url"]["url"])
                    break
        else:
            if m.get("image"):
                # путь к файлу
                image_path = Path(m["image"])
                if image_path.is_file():
                    with open(image_path, "rb") as f:
                        image = Image.open(f).convert("RGB")
                    break
    return out, image



def _build_inputs(self, messages):
    msgs, image = _collapse_messages(messages)
    prompt = self.tokenizer.apply_chat_template(
        msgs, tokenize=False, add_generation_prompt=True
    )
    if image is None:
        batch = self.tokenizer(prompt, return_tensors="pt")
    else:
        batch = self.processor(text=prompt, images=image, return_tensors="pt")
    return {k: v.to(_DEVICE) for k, v in batch.items()}


class _LocalQwenBackend(ModelBackend):
    name = "local_qwen25"

    def __init__(self) -> None:
        super().__init__()
        self.unload_mode = Settings.load().local_unload_mode  # 'none' | 'cpu' | 'full'
        self.model: Qwen2_5_VLForConditionalGeneration | None = None
        self.processor: AutoProcessor | None = None
        self.tokenizer = None

    # ---------------- helpers -----------------
    def _maybe_reload_model(self):
        if self.model is None:
            _LOGGER.info("⏳ Загружаю Qwen2.5-VL-3B …")
            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                _MODEL_NAME, torch_dtype=_DTYPE
            ).to(_DEVICE)
            self.processor = AutoProcessor.from_pretrained(_MODEL_NAME)
            self.tokenizer = self.processor.tokenizer
            self.model.resize_token_embeddings(len(self.tokenizer))
            _prepare_processor(self.processor)
            _LOGGER.info("✅ Qwen2.5-VL-3B загружена.")
        elif next(self.model.parameters()).device != torch.device(_DEVICE):
            _LOGGER.info(f"🔄 Перемещаю модель обратно на {_DEVICE}")
            self.model.to(_DEVICE)

    def unload_model(self):
        if self.model is None:
            return
        mode = Settings.load().local_unload_mode
        if mode == "none":
            return
        if torch.cuda.is_available():
            before = torch.cuda.memory_allocated() / 1024 ** 2
        if mode == "cpu":
            self.model.to("cpu")
        elif mode == "full":
            del self.model, self.processor, self.tokenizer
            self.model = self.processor = self.tokenizer = None
        import gc, torch as t
        gc.collect()
        t.cuda.empty_cache()
        if torch.cuda.is_available():
            after = torch.cuda.memory_allocated() / 1024 ** 2
            _LOGGER.info(f"🔋 VRAM: {before:.1f} MB → {after:.1f} MB")

    # -------------- sync --------------
    def generate(self, messages: List[dict], **kw) -> str:
        self._maybe_reload_model()
        batch = _build_inputs(self, normalize(messages))
        output = self.model.generate(**batch, max_new_tokens=_MAX_TOKENS)
        gen_ids = output[0][batch["input_ids"].shape[1]:]
        self.unload_model()
        return self.tokenizer.decode(gen_ids, skip_special_tokens=True)

    # -------------- stream --------------
    def stream(self, messages: List[dict], **kw) -> Iterator[str]:
        self._maybe_reload_model()
        batch = _build_inputs(self, normalize(messages))
        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )
        threading.Thread(
            target=self.model.generate,
            kwargs=dict(**batch, streamer=streamer, max_new_tokens=_MAX_TOKENS),
            daemon=True,
        ).start()
        for tok in streamer:
            yield tok
        self.unload_model()


# Экспортируем для регистратора
backend = _LocalQwenBackend()

def summarize_chat(prompt: str) -> str:
    """Суммаризация через локальный Qwen-VL."""
    return backend.generate([{"role": "user", "content": prompt}])
