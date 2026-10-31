"""Сервер как git-remote: git по HTTPS на `/git/<project_id>.git` (HSE_STUDIO__GIT_REMOTE__*)."""

from pydantic import BaseModel, Field


class GitRemoteConfig(BaseModel):
    """Только серверный режим; локальная Студия маршрутов git по HTTPS не отдаёт."""

    enabled: bool = Field(default=True, description="Отдавать проекты по git (clone, fetch, push) на /git/<id>.git.")
    max_push_bytes: int = Field(
        default=268_435_456, ge=1_048_576, description="Предел тела одного push в байтах (и receive.maxInputSize)."
    )
    max_concurrent_per_user: int = Field(
        default=4, ge=1, description="Сколько запросов git одного человека выполняются одновременно."
    )
    timeout_s: int = Field(default=600, ge=10, description="Предел одного процесса git upload-pack или receive-pack.")
    lock_wait_s: int = Field(default=30, ge=1, description="Сколько push ждёт замок папки проекта.")
