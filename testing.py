from ai_design_assistant.core import get_global_router
router = get_global_router()
print("Registered providers:", router.providers)