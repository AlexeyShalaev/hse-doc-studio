"""Очистка текстов исполнителя: секреты, адреса и пути не выходят в админку."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.server_update.redact import redact


@pytest.mark.parametrize(
    ("raw", "forbidden"),
    [
        ("Authorization: Bearer abc.DEF-123_xyz failed", "abc.DEF"),
        ("pull failed: token=ghp_1234567890abcdef denied", "ghp_1234567890abcdef"),
        ("connect postgresql://user:p@ss@db.internal:5432/app failed", "p@ss"),
        ("DATABASE_PASSWORD: hunter2 rejected", "hunter2"),
        ("dial tcp 10.0.12.7:5432: i/o timeout", "10.0.12.7"),
        ("api.hse.svc.cluster.local:8000 refused", "svc.cluster.local"),
        ("cannot open /var/lib/updater/journal.json: denied", "/var/lib"),
        ("read /home/ops/.kube/config failed", "/home/ops"),
    ],
)
def test__redact__removes_secrets_addresses_and_host_paths(raw: str, forbidden: str) -> None:
    out = redact(raw)
    assert forbidden not in out
    assert "[" in out


@pytest.mark.parametrize(
    "keep",
    [
        "the Job migrate did not start in 300 s: ErrImagePull",
        "image ghcr.io/alexeyshalaev/hse-doc-studio:0.3.2@sha256:abc123 will be pinned",
        "database revision up_01_server_updates",
        "GET https://github.com/org/repo/releases/download/v1/image-digest.json failed",
        "scaling the api to zero",
    ],
)
def test__redact__keeps_useful_diagnostics(keep: str) -> None:
    assert redact(keep) == keep
