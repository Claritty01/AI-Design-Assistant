from ai_design_assistant.core import get_global_router, ChatSession

router = get_global_router()
print("Known providers:", router.providers)  # должно вывести хотя бы openai

chat = ChatSession(title="Router test")
chat.add_message("user", "Привет!")
try:
    result = router.complete(chat.messages)
except Exception as exc:
    print("As expected, backend not yet implemented:", exc)