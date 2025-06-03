# ai_design_assistant/api/local_qwen25_backend.py
from __future__ import annotations
import os, threading, base64, logging
from pathlib import Path
from io import BytesIO
from typing import Iterator, List

from PIL import Image
from qwen_vl_utils import process_vision_info
import torch
from transformers import (
    Qwen2_5_VLForConditionalGeneration,
    AutoProcessor,
    TextIteratorStreamer,
    BitsAndBytesConfig
)

from ai_design_assistant.core.settings import Settings
from ai_design_assistant.core.models import ModelBackend, normalize

logging.basicConfig(level=logging.DEBUG)

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


def _decode_data_url(data_url: str) -> str:
    # ничего не декодируем, просто возвращаем строку
    return data_url



def _collapse_messages(raw_messages: List[dict]):
    hf_msgs = []
    for m in raw_messages:
        role = m["role"]
        blocks = []
        content = m["content"]

        if isinstance(content, list):
            for chunk in content:
                if chunk["type"] == "image_url":
                    # ⬇️  Заменяем на блок type="image" со строкой-URL
                    blocks.append({
                        "type": "image",
                        "image": chunk["image_url"]["url"]    # ← строка URL
                    })
                else:         # {"type": "text", …}
                    blocks.append(chunk)
        else:
            blocks.append({"type": "text", "text": str(content)})
            if m.get("image"):          # локальный файл
                blocks.append({
                    "type": "image",
                    "image": str(Path(m["image"]))            # строковый путь
                })

        hf_msgs.append({"role": role, "content": blocks})

    # теперь все изображения — type="image"
    image_inputs, video_inputs = process_vision_info(hf_msgs)
    return hf_msgs, image_inputs, video_inputs




def _build_inputs(self, messages):
    hf_msgs, image_inputs, video_inputs = _collapse_messages(messages)

    # 1) текст с <img> токенами
    prompt = self.processor.apply_chat_template(
        hf_msgs, tokenize=False, add_generation_prompt=True
    )
    _LOGGER.debug(f"Prompt →\n{prompt}")

    # 2) в один вызов processor
    # --- КОНСТРУИРУЕМ kwargs только с тем, что реально есть ---
    proc_kwargs = {
        "text": [prompt],
        "padding": True,
        "return_tensors": "pt",
    }
    if image_inputs:  # есть хотя бы одна картинка
        proc_kwargs["images"] = image_inputs
    if video_inputs:  # есть хотя бы одно видео
        proc_kwargs["videos"] = video_inputs

    inputs = self.processor(**proc_kwargs)

    # 3) к тому же устройству
    device = next(self.model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}
    return inputs


def propagate_last_image(messages: list[dict]) -> list[dict]:
    """
    Пробегаем по сообщениям и добавляем картинку к каждому пользовательскому сообщению без картинки,
    используя последнее известное изображение.
    """
    last_image = None
    new_messages = []
    for msg in messages:
        # если в сообщении есть картинка — запоминаем её
        if msg.get("image"):
            last_image = msg["image"]

        # если сообщение от пользователя и без картинки — подставляем
        if msg["role"] == "user" and not msg.get("image") and last_image:
            msg = msg.copy()
            msg["image"] = last_image

        new_messages.append(msg)

    return new_messages


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
            _LOGGER.info("⏳ Загружаю Qwen2.5-VL-3B с 4-bit квантизацией…")

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )

            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                _MODEL_NAME,
                quantization_config=bnb_config,
                device_map="auto"
            )
            self.processor = AutoProcessor.from_pretrained(
                _MODEL_NAME,
                min_pixels=28 * 28,  # ≈ 1 визуальный токен
                max_pixels=1280 * 28 * 28,  # как в примере
            )

            self.tokenizer = self.processor.tokenizer
            self.model.resize_token_embeddings(len(self.tokenizer))
            _prepare_processor(self.processor)
            _LOGGER.info("✅ Qwen2.5-VL-3B загружена (4-bit).")
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
        messages = propagate_last_image(normalize(messages))
        # Добавляем system-подсказку:
        messages.insert(0, {
            "role": "system",
            "content": (
                "Ты — ИИ-ассистент по графическому дизайну. "
                "Если получаешь изображение с людьми, игнорируй лица и сосредоточься на UI/UX "
                "или на эстетике кадра. Отвечай кратко и по существу."
            )
        })
        batch = _build_inputs(self, messages)
        output = self.model.generate(
            **batch,
            max_new_tokens=_MAX_TOKENS,
            pad_token_id=self.tokenizer.pad_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
        )
        gen_ids = output[0][batch["input_ids"].shape[1]:]
        self.unload_model()
        return self.tokenizer.decode(gen_ids, skip_special_tokens=True)

    # -------------- stream --------------
    def stream(self, messages: List[dict], **kw) -> Iterator[str]:
        self._maybe_reload_model()
        messages = propagate_last_image(normalize(messages))
        # Добавляем system-подсказку:
        messages.insert(0, {
            "role": "system",
            "content": (
                "Ты — ИИ-ассистент по графическому дизайну. "
                "Если получаешь изображение с людьми, игнорируй лица и сосредоточься на UI/UX "
                "или на эстетике кадра. Отвечай кратко и по существу."
            )
        })
        batch = _build_inputs(self, messages)
        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )
        threading.Thread(
            target=self.model.generate,
            kwargs=dict(
                **batch,
                streamer=streamer,
                max_new_tokens=_MAX_TOKENS,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            ),
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
