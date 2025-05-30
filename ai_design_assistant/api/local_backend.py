# ai_design_assistant/api/local_backend.py
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Iterator, List

import base64
from io import BytesIO
from PIL import Image

import torch
from transformers import (
    LlavaNextForConditionalGeneration,
    AutoProcessor,
    TextIteratorStreamer,
)

import logging

_LOGGER = logging.getLogger(__name__)

from ai_design_assistant.core.models import ModelBackend, normalize

# ──────────────────────────────────────────────────────────────────
_MODEL_NAME = os.getenv("LOCAL_MODEL_NAME", "neulab/Pangea-7B-hf")
_DEVICE     = "cuda" if torch.cuda.is_available() else "cpu"
_DTYPE      = torch.float16 if _DEVICE == "cuda" else torch.float32
_MAX_TOKENS = int(os.getenv("LOCAL_MAX_NEW_TOKENS", "512"))
# ──────────────────────────────────────────────────────────────────


def _prepare_processor(proc, patch_size: int = 14) -> None:
    """Гарантируем, что у процессора выставлен patch_size (некоторые версии HF опускают поле)."""
    if getattr(proc, "patch_size", None) is None:
        proc.patch_size = patch_size
    if getattr(proc.image_processor, "patch_size", None) is None:
        proc.image_processor.patch_size = patch_size

def _decode_data_url(data_url: str) -> Image.Image:
    """data:image/...;base64,.... → PIL.Image"""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    img_bytes = base64.b64decode(data_url)
    return Image.open(BytesIO(img_bytes)).convert("RGB")

def _collapse_messages(messages: List[dict]):
    """Возвращает ([messages], image | None) — и берёт картинку только из последнего user-сообщения."""
    image: Image.Image | None = None
    out = []

    for m in messages:
        content = m["content"]

        if isinstance(content, list):
            parts = []
            for chunk in content:
                if chunk["type"] == "text":
                    parts.append(chunk["text"])
                elif chunk["type"] == "image_url":
                    parts.append("<image>")   # всегда добавляем <image>
            content = " ".join(parts)

        out.append({"role": m["role"], "content": content})

    # Найти последнюю картинку в истории сообщений
    for m in reversed(messages):
        content = m["content"]
        if isinstance(content, list):
            for chunk in content:
                if chunk["type"] == "image_url":
                    image = _decode_data_url(chunk["image_url"]["url"])
                    break
        if image:
            break

    return out, image


def _build_inputs(self, messages):
    msgs, image = _collapse_messages(messages)
    prompt = self.tokenizer.apply_chat_template(
        msgs, tokenize=False, add_generation_prompt=True
    )
    if image is None:          # старый путь (text-only)
        batch = self.tokenizer(prompt, return_tensors="pt")
    else:                      # текст + картинка
        batch = self.processor(text=prompt, images=image, return_tensors="pt")
    return {k: v.to(_DEVICE) for k, v in batch.items()}


class _LocalBackend(ModelBackend):
    name = "local"

    def __init__(self) -> None:
        super().__init__()

        # ── загружаем модель уже после регистрации (можно и до) ──
        self.model = LlavaNextForConditionalGeneration.from_pretrained(
            _MODEL_NAME, torch_dtype=_DTYPE
        ).to(_DEVICE)

        self.processor = AutoProcessor.from_pretrained(_MODEL_NAME)
        self.tokenizer = self.processor.tokenizer
        self.model.resize_token_embeddings(len(self.tokenizer))

        _prepare_processor(self.processor)

    # --- базовый sync-режим (вернуть строку цельным куском) -----------------
    def generate(self, messages: List[dict[str, str]], **kw) -> str:
        batch = _build_inputs(self, messages)
        output = self.model.generate(**batch, max_new_tokens=_MAX_TOKENS)
        gen_ids = output[0][batch["input_ids"].shape[1]:]
        return self.tokenizer.decode(gen_ids, skip_special_tokens=True)

    # --- потоковая версия (вернёт итератор токенов) --------------------------
    def stream(self, messages: List[dict[str, str]], **kw) -> Iterator[str]:
        batch = _build_inputs(self, messages)

        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )
        gen_kwargs = dict(**batch, streamer=streamer, max_new_tokens=_MAX_TOKENS)

        threading.Thread(
            target=self.model.generate, kwargs=gen_kwargs, daemon=True
        ).start()
        return streamer


# Экспортим объект, чтобы api.__init__ смог зарегистрировать бекенд
backend = _LocalBackend()
