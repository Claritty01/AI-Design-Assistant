# ai_design_assistant/api/local_backend.py
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Iterator, List

import torch
from transformers import (
    LlavaNextForConditionalGeneration,
    AutoProcessor,
    TextIteratorStreamer,
)

from ai_design_assistant.core.models import ModelBackend, normalize

# ──────────────────────────────────────────────────────────────────
_MODEL_NAME = os.getenv("LOCAL_MODEL_NAME", "neulab/Pangea-7B-hf")
_DEVICE     = "cuda" if torch.cuda.is_available() else "cpu"
_DTYPE      = torch.float16 if _DEVICE == "cuda" else torch.float32
_MAX_TOKENS = int(os.getenv("LOCAL_MAX_NEW_TOKENS", "150"))
# ──────────────────────────────────────────────────────────────────


def _prepare_processor(proc, patch_size: int = 14) -> None:
    """Гарантируем, что у процессора выставлен patch_size (некоторые версии HF опускают поле)."""
    if getattr(proc, "patch_size", None) is None:
        proc.patch_size = patch_size
    if getattr(proc.image_processor, "patch_size", None) is None:
        proc.image_processor.patch_size = patch_size


class _LocalBackend(ModelBackend):
    name = "local"

    def __init__(self) -> None:
        self.model = LlavaNextForConditionalGeneration.from_pretrained(
            _MODEL_NAME, torch_dtype=_DTYPE
        ).to(_DEVICE)

        self.processor = AutoProcessor.from_pretrained(_MODEL_NAME)
        self.tokenizer = self.processor.tokenizer
        self.model.resize_token_embeddings(len(self.tokenizer))

        _prepare_processor(self.processor)

    # --- базовый sync-режим (вернуть строку цельным куском) -----------------
    def generate(self, messages: List[dict[str, str]], **kw) -> str:  # noqa: D401
        msgs = normalize(messages)
        prompt = self.tokenizer.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=True
        )

        batch = self.tokenizer(prompt, return_tensors="pt")
        batch = {k: v.to(_DEVICE) for k, v in batch.items()}

        output = self.model.generate(**batch, max_new_tokens=_MAX_TOKENS)
        gen_ids = output[0][batch["input_ids"].shape[1] :]
        return self.tokenizer.decode(gen_ids, skip_special_tokens=True)

    # --- потоковая версия (вернёт итератор токенов) --------------------------
    def stream(self, messages: List[dict[str, str]], **kw) -> Iterator[str]:
        msgs = normalize(messages)
        prompt = self.tokenizer.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=True
        )
        batch = self.tokenizer(prompt, return_tensors="pt")
        batch = {k: v.to(_DEVICE) for k, v in batch.items()}

        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )
        gen_kwargs = dict(**batch, streamer=streamer, max_new_tokens=_MAX_TOKENS)

        threading.Thread(
            target=self.model.generate, kwargs=gen_kwargs, daemon=True
        ).start()
        return streamer  # UI уже умеет читать iterator<string>

# Экспортим объект, чтобы api.__init__ смог зарегистрировать бекенд
backend = _LocalBackend()
