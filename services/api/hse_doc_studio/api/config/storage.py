"""S3-совместимое хранилище."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator


class StorageConfig(BaseModel):
    """Объектное хранилище серверного режима (HSE_STUDIO__S3__*).

    Без ``bucket`` объекты лежат в каталоге (``fs_root``, по умолчанию ``data_dir/objects``): так живут
    установки без S3. Ключи доступа только из окружения или файла секретов.
    """

    bucket: str | None = Field(default=None, description="Имя закрытого бакета; пусто означает хранение в каталоге.")
    endpoint: str | None = Field(
        default=None, description="Внутренний адрес S3 (MinIO, Ceph); пусто означает AWS по региону."
    )
    public_endpoint: str | None = Field(
        default=None,
        description="Публичный адрес S3 для подписанных ссылок тем, кто вне сети сервера: браузеры, личные раннеры "
        "и локальные Студии. Ссылка подписывается сразу для этого хоста; раннеры в сети сервера по-прежнему "
        "ходят по внутреннему адресу. Пусто означает, что внешние клиенты получают внутренний адрес.",
    )
    outside_runner_access: Literal["presigned", "proxy"] = Field(
        default="presigned",
        description="Как раннеры вне сети сервера обмениваются файлами с хранилищем: presigned это подписанные "
        "ссылки на публичный адрес; proxy это поток через api без ссылок (запасной вариант, когда хранилище нельзя "
        "опубликовать; нагрузка идёт через api).",
    )
    shared_runners_outside: bool = Field(
        default=False,
        description="Считать общие (установочные) раннеры тоже внешними: им выдаются ссылки на публичный адрес "
        "или поток через api. По умолчанию внешними считаются только личные раннеры.",
    )
    region: str = Field(default="us-east-1", description="Регион подписи.")
    access_key: SecretStr | None = Field(default=None, description="Ключ доступа; пусто означает цепочку boto3.")
    secret_key: SecretStr | None = Field(default=None, description="Секретный ключ доступа.")
    path_style: bool = Field(default=True, description="Адресация bucket в пути (MinIO, Ceph); false для виртуальной.")
    fs_root: Path | None = Field(default=None, description="Каталог объектов, когда bucket не задан.")
    max_object_bytes: int = Field(default=2 * 1024**3, ge=1, description="Предел размера одного объекта.")
    multipart_threshold_bytes: int = Field(
        default=64 * 1024**2, ge=5 * 1024**2, description="С какого размера загрузка идёт частями."
    )
    cors_origins: list[str] = Field(
        default_factory=list,
        description="Источники, которым бакет разрешает читать подписанные ссылки (pdf.js ходит туда с Range); "
        "пусто означает не трогать CORS бакета.",
    )
    presign_ttl_s: int = Field(default=300, ge=1, le=3600, description="Срок подписанной ссылки по умолчанию.")

    @field_validator("public_endpoint")
    @classmethod
    def _public_endpoint_is_origin(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parts = urlsplit(value.strip())
        if parts.scheme not in ("http", "https") or not parts.hostname:
            msg = "public_endpoint должен быть адресом http(s)://хост[:порт]"
            raise ValueError(msg)
        if parts.username or parts.password or parts.query or parts.fragment or parts.path.strip("/"):
            msg = "public_endpoint задаёт только схему, хост и порт: без логина, пути, query и fragment"
            raise ValueError(msg)
        return f"{parts.scheme}://{parts.netloc}"
