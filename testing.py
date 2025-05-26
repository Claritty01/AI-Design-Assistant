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


from pathlib import Path
print("is_file:", Path("ai_design_assistant/data/chats").is_file())
print("is_dir:", Path("ai_design_assistant/data/chats").is_dir())
