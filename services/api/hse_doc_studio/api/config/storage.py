"""S3-совместимое хранилище."""

from pydantic import BaseModel


class StorageConfig(BaseModel):
    """S3 серверного режима (HSE_STUDIO__S3__*). Поля добавляет срез хранилища."""
