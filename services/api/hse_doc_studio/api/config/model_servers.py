"""Серверы ИИ-моделей, которые админ ставит из интерфейса (Ollama, vLLM, SGLang)."""

from pydantic import BaseModel, Field


class ModelServersConfig(BaseModel):
    local_enabled: bool = Field(
        default=True,
        description=(
            "Разрешена ли установка серверов моделей на машине со Студией (соседние контейнеры через docker.sock). "
            "В Kubernetes чарт выключает её по умолчанию: сокет узла равен root на узле."
        ),
    )
    ollama_image: str = Field(default="", description="Образ Ollama; пусто значит образ по умолчанию.")
    vllm_image: str = Field(
        default="", description="Образ vLLM (OpenAI-совместимый сервер); пусто значит по умолчанию."
    )
    sglang_image: str = Field(default="", description="Образ SGLang; пусто значит образ по умолчанию.")
    max_concurrent_installs: int = Field(
        default=1, ge=1, le=4, description="Сколько установок серверов моделей может идти одновременно."
    )
    startup_timeout_s: float = Field(
        default=120.0, gt=0, description="Сколько ждать адрес и готовность контейнера движка после запуска."
    )
    ready_timeout_s: float = Field(
        default=3600.0,
        gt=0,
        description="Сколько ждать готовности vLLM и SGLang: при первом запуске они скачивают веса модели.",
    )
