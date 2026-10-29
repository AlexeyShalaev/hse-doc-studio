"""S3-совместимое хранилище."""

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr


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
        description="Адрес для подписанных ссылок, если клиенты видят S3 под другим именем, чем сервер.",
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
