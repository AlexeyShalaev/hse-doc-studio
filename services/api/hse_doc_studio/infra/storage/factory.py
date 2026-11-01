"""Выбор реализации хранилища по настройкам."""

from __future__ import annotations

from pathlib import Path

from hse_doc_studio.api.config.storage import StorageConfig
from hse_doc_studio.core.storage.ports import IObjectStore
from hse_doc_studio.infra.storage.fs import FsObjectStore


def create_object_store(cfg: StorageConfig, data_dir: Path) -> IObjectStore:
    """S3, когда задан bucket, иначе каталог. boto3 подключается только для S3."""
    if not cfg.bucket:
        root = (cfg.fs_root or data_dir / "objects").expanduser()
        return FsObjectStore(root, max_object_bytes=cfg.max_object_bytes)

    import boto3  # noqa: PLC0415

    from hse_doc_studio.infra.storage.s3 import S3ObjectStore, build_client_config  # noqa: PLC0415

    def client(endpoint: str | None) -> object:
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=cfg.region,
            aws_access_key_id=cfg.access_key.get_secret_value() if cfg.access_key else None,
            aws_secret_access_key=cfg.secret_key.get_secret_value() if cfg.secret_key else None,
            config=build_client_config(path_style=cfg.path_style),
        )

    return S3ObjectStore(
        client(cfg.endpoint),
        cfg.bucket,
        max_object_bytes=cfg.max_object_bytes,
        multipart_threshold_bytes=cfg.multipart_threshold_bytes,
        presign_client=client(cfg.public_endpoint) if cfg.public_endpoint else None,
    )
