from __future__ import annotations

import pytest

pytestmark = pytest.mark.s3


def test__s3_bucket__put_and_get_roundtrip(s3_client, s3_bucket) -> None:
    s3_client.put_object(Bucket=s3_bucket, Key="a/b.txt", Body=b"data")

    body = s3_client.get_object(Bucket=s3_bucket, Key="a/b.txt")["Body"].read()

    assert body == b"data"


def test__s3_bucket__two_tests_get_distinct_buckets(s3_client, s3_bucket) -> None:
    names = [b["Name"] for b in s3_client.list_buckets()["Buckets"]]

    assert names == [s3_bucket]
