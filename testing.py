# import torch
#
# print("CUDA доступна:", torch.cuda.is_available())
# if torch.cuda.is_available():
#     print("Текущее устройство:", torch.cuda.get_device_name(0))
#     print("Количество устройств:", torch.cuda.device_count())
#     print("Текущее устройство ID:", torch.cuda.current_device())
# else:
#     print("CUDA не доступна. Используется CPU.")
#
# print(torch.cuda.get_device_capability(0))  # Например: (8, 9) для sm_89


# from pathlib import Path
# print("is_file:", Path("ai_design_assistant/data/chats").is_file())
# print("is_dir:", Path("ai_design_assistant/data/chats").is_dir())



# from transformers import LlavaNextForConditionalGeneration, AutoProcessor
# import torch
#
# model_name = "neulab/Pangea-7B-hf"
#
# model = LlavaNextForConditionalGeneration.from_pretrained(
#     model_name,
#     torch_dtype=torch.float16
# ).to("cuda")
#
# processor = AutoProcessor.from_pretrained(model_name)
# tokenizer = processor.tokenizer
# model.resize_token_embeddings(len(tokenizer))
#
# messages = [
#     {"role": "user", "content": "Привет! Расскажи мне интересный факт о космосе."}
# ]
#
# prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
# inputs = tokenizer(prompt, return_tensors="pt")
# inputs_cuda = {k: v.to("cuda") for k, v in inputs.items()}
#
# output = model.generate(**inputs_cuda, max_new_tokens=100)
# generated_ids = output[0]
# generated_only = generated_ids[inputs['input_ids'].shape[1]:]
# response = tokenizer.decode(generated_only, skip_special_tokens=True)
#
# print(response)


# from transformers import LlavaNextForConditionalGeneration, AutoProcessor
# from PIL import Image
# import torch
#
# model_name = "neulab/Pangea-7B-hf"
# device = "cuda"
# dtype  = torch.float16          # применяем ТОЛЬКО к float-тензорам
#
# model = LlavaNextForConditionalGeneration.from_pretrained(
#     model_name, torch_dtype=dtype
# ).to(device)
#
# proc = AutoProcessor.from_pretrained(model_name)
# tok  = proc.tokenizer
# model.resize_token_embeddings(len(tok))
#
# # ── патчим patch_size, если нужно ───────────────────────────
# DEFAULT_PS = 14
# for attr in ("patch_size", "image_processor.patch_size"):
#     obj, name = (proc, "patch_size") if "." not in attr else (proc.image_processor, "patch_size")
#     if getattr(obj, name, None) is None:
#         setattr(obj, name, DEFAULT_PS)
# # ────────────────────────────────────────────────────────────
#
# image = Image.open("test_image.png").convert("RGB")
#
# messages = [
#     {"role": "user", "content": "<image>\nЧто изображено на этом фото?"}
# ]
# prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
#
# # processor сам различает типы тензоров
# batch = proc(images=image, text=prompt, return_tensors="pt")
#
# # переносим на GPU ***без изменения dtype***
# batch = {k: v.to(device) for k, v in batch.items()}
#
# out = model.generate(**batch, max_new_tokens=150)
#
# gen_only = out[0][batch["input_ids"].shape[1]:]
# answer   = tok.decode(gen_only, skip_special_tokens=True)
# print(answer)



# multimodal_assistant.py
# from __future__ import annotations
# from pathlib import Path
# from typing import List, Dict, Union
# import torch
# from PIL import Image
# from transformers import (
#     LlavaNextForConditionalGeneration,
#     AutoProcessor,
#     TextIteratorStreamer,
# )
#
# class MultimodalAssistant:
#     def __init__(
#         self,
#         model_name: str = "neulab/Pangea-7B-hf",
#         device: str = "cuda",
#         dtype: torch.dtype = torch.float16,
#         max_new_tokens: int = 150,
#     ):
#         self.device = device
#         self.max_new_tokens = max_new_tokens
#
#         self.model = LlavaNextForConditionalGeneration.from_pretrained(
#             model_name, torch_dtype=dtype
#         ).to(device)
#
#         self.processor = AutoProcessor.from_pretrained(model_name)
#         self.tokenizer = self.processor.tokenizer
#         self.model.resize_token_embeddings(len(self.tokenizer))
#
#         # --- гарантируем patch_size ---
#         ps = 14
#         if getattr(self.processor, "patch_size", None) is None:
#             self.processor.patch_size = ps
#         if getattr(self.processor.image_processor, "patch_size", None) is None:
#             self.processor.image_processor.patch_size = ps
#
#     # ─────────────────────────────────────────────────────────────
#     def chat(
#         self,
#         messages: List[Dict[str, str]],
#         image_path: Union[str, Path, None] = None,
#         stream: bool = False,
#     ):
#         """
#         messages: [{"role": "user"/"assistant", "content": "..."}]
#         image_path: None => текстовый диалог; иначе путь к картинке
#         """
#         if image_path:
#             # вставляем <image> в последнее user-сообщение, если его ещё нет
#             if "<image>" not in messages[-1]["content"]:
#                 messages[-1]["content"] = "<image>\n" + messages[-1]["content"]
#
#             prompt = self.tokenizer.apply_chat_template(
#                 messages, tokenize=False, add_generation_prompt=True
#             )
#
#             image = Image.open(str(image_path)).convert("RGB")
#             batch = self.processor(
#                 images=image, text=prompt, return_tensors="pt"
#             )
#         else:
#             prompt = self.tokenizer.apply_chat_template(
#                 messages, tokenize=False, add_generation_prompt=True
#             )
#             batch = self.tokenizer(prompt, return_tensors="pt")
#
#         batch = {k: v.to(self.device) for k, v in batch.items()}
#
#         if stream:
#             streamer = TextIteratorStreamer(
#                 self.tokenizer, skip_prompt=True, skip_special_tokens=True
#             )
#             gen_kwargs = dict(
#                 **batch,
#                 streamer=streamer,
#                 max_new_tokens=self.max_new_tokens,
#             )
#             # запускаем генерацию в отдельном потоке, если нужно
#             import threading
#
#             threading.Thread(
#                 target=self.model.generate, kwargs=gen_kwargs, daemon=True
#             ).start()
#             return streamer  # итератор токенов
#         else:
#             output = self.model.generate(
#                 **batch, max_new_tokens=self.max_new_tokens
#             )
#             gen_ids = output[0][batch["input_ids"].shape[1] :]
#             return self.tokenizer.decode(gen_ids, skip_special_tokens=True)
#
# assistant = MultimodalAssistant()
#
# # 1) Текст-только
# history = [{"role": "user", "content": "Привет, расскажи факт о Луне"}]
# print(assistant.chat(history))
#
# # 2) Картинка + вопрос
# history = [{"role": "user", "content": "Что на фото? Можно ли его как-то улучшить?"}]
# print(assistant.chat(history, image_path="test_image.png"))

#
# from importlib import import_module
# from ai_design_assistant.core.models import LLMRouter
#
# # имитируем то, что делает MainWindow
# import_module("ai_design_assistant.api.local_backend")
# router = LLMRouter(default="local")
#
# print(router.backends.keys())        # dict_keys(['openai', 'deepseek', 'local'])
# print(router.generate(
#     [{"role": "user", "content": "Сколько цифр после запятой у числа π?"}]
# ))

import torch
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor

model_name = "Qwen/Qwen2.5-VL-3B-Instruct"
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(model_name, torch_dtype=torch.float16).to("cuda")
processor = AutoProcessor.from_pretrained(model_name)

print("✅ Модель успешно загружена!")
