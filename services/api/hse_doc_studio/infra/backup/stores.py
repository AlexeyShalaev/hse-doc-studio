"""Хранилища назначений: S3 по параметрам админа и каталог внутри локального корня."""

from __future__ import annotations

import os
from pathlib import Path

from hse_doc_studio.api.config.backups import BackupsConfig
from hse_doc_studio.api.config.storage import StorageConfig
from hse_doc_studio.core.backup.entities import DestinationKind, DestinationSecrets, DestinationSpec
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.storage.ports import IObjectStore
from hse_doc_studio.infra.storage.fs import FsObjectStore


def _endpoint_key(endpoint: str | None) -> str:
    return (endpoint or "").rstrip("/").lower()


class BackupStoreFactory:
    def __init__(self, cfg: BackupsConfig, primary: StorageConfig, data_dir: Path) -> None:
        self._cfg = cfg
        self._primary = primary
        self._data_dir = data_dir

    @property
    def local_root(self) -> Path:
        return (self._cfg.local_root or self._data_dir / "backups").expanduser()

    def local_path(self, relative: str) -> Path:
        """Каталог локального назначения; путь, выходящий из корня (в том числе через симлинк), отвергается."""
        root = self.local_root.resolve()
        target = (root / relative).resolve()
        if target == root or not target.is_relative_to(root):
            raise BackupError(
                BackupErrorCode.invalid_input, "the local path must be inside the local root", field="local_path"
            )
        return target

    def open(self, spec: DestinationSpec, secrets: DestinationSecrets) -> IObjectStore:
        if spec.kind is DestinationKind.local:
            return FsObjectStore(self.local_path(spec.local_path or ""), max_object_bytes=self._cfg.max_object_bytes)
        import boto3  # noqa: PLC0415

        from hse_doc_studio.infra.storage.s3 import S3ObjectStore, build_client_config  # noqa: PLC0415

        client = boto3.client(
            "s3",
            endpoint_url=spec.endpoint,
            region_name=spec.region,
            aws_access_key_id=secrets.access_key,
            aws_secret_access_key=secrets.secret_key,
            config=build_client_config(path_style=spec.path_style),
        )
        return S3ObjectStore(
            client,
            spec.bucket or "",
            max_object_bytes=self._cfg.max_object_bytes,
            multipart_threshold_bytes=self._cfg.multipart_threshold_bytes,
        )

    def is_primary(self, spec: DestinationSpec) -> bool:
        if spec.kind is DestinationKind.s3:
            return (
                bool(self._primary.bucket)
                and spec.bucket == self._primary.bucket
                and _endpoint_key(spec.endpoint) == _endpoint_key(self._primary.endpoint)
            )
        try:
            root = self.local_root
            root.mkdir(parents=True, exist_ok=True)
            return os.stat(root).st_dev == os.stat(self._data_dir.expanduser()).st_dev
        except OSError:
            return False
