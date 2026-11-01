from __future__ import annotations

AI_PROVIDER_UNAVAILABLE = "ai_provider_unavailable"
AI_MODEL_NOT_ALLOWED = "ai_model_not_allowed"


class AiProviderUnavailableError(Exception):
    """Провайдер временно закрыт автоматом отказов и замены нет. HTTP: 503 `ai_provider_unavailable`."""

    def __init__(self, provider_name: str, retry_after_s: float | None = None) -> None:
        super().__init__(f"AI provider unavailable: {provider_name}")
        self.provider_name = provider_name
        self.retry_after_s = retry_after_s


class AiModelNotAllowedError(Exception):
    """Модель вне белого списка общего провайдера. HTTP: 403 `ai_model_not_allowed`."""

    def __init__(self, provider_name: str, model: str) -> None:
        super().__init__(f"model {model!r} is not allowed on {provider_name}")
        self.provider_name = provider_name
        self.model = model
