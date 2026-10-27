"""S3 для тестов с маркером s3.

По умолчанию бакет живёт в moto внутри процесса. Если заданы `HSE_TEST_S3_ENDPOINT`,
`HSE_TEST_S3_ACCESS_KEY` и `HSE_TEST_S3_SECRET_KEY`, тесты идут в настоящий MinIO (CI-сервис).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

S3_ENDPOINT_ENV = "HSE_TEST_S3_ENDPOINT"
S3_ACCESS_KEY_ENV = "HSE_TEST_S3_ACCESS_KEY"
S3_SECRET_KEY_ENV = "HSE_TEST_S3_SECRET_KEY"  # noqa: S105 — имя переменной окружения, не секрет
_REGION = "us-east-1"


@dataclass(frozen=True)
class S3Target:
    client: Any
    bucket: str
    endpoint_url: str | None


def _empty_and_delete(client: Any, bucket: str) -> None:
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
    client.delete_bucket(Bucket=bucket)


@pytest.fixture
def s3_target(monkeypatch: pytest.MonkeyPatch) -> Iterator[S3Target]:
    """Клиент boto3 и пустой бакет на тест (moto или MinIO)."""
    boto3 = pytest.importorskip("boto3")
    bucket = f"hse-test-{uuid.uuid4().hex[:12]}"
    endpoint = os.environ.get(S3_ENDPOINT_ENV)
    if endpoint:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.environ[S3_ACCESS_KEY_ENV],
            aws_secret_access_key=os.environ[S3_SECRET_KEY_ENV],
            region_name=_REGION,
        )
        client.create_bucket(Bucket=bucket)
        try:
            yield S3Target(client=client, bucket=bucket, endpoint_url=endpoint)
        finally:
            _empty_and_delete(client, bucket)
        return

    moto = pytest.importorskip("moto")
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SECURITY_TOKEN", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)
    with moto.mock_aws():
        client = boto3.client("s3", region_name=_REGION)
        client.create_bucket(Bucket=bucket)
        yield S3Target(client=client, bucket=bucket, endpoint_url=None)


@pytest.fixture
def s3_client(s3_target: S3Target) -> Any:
    return s3_target.client


@pytest.fixture
def s3_bucket(s3_target: S3Target) -> str:
    return s3_target.bucket
