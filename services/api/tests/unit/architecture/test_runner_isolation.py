"""Храповик раннера: контейнер процесса раннера не тянет репозитории, базу, хранилище и слой use_cases.

Образ раннера не содержит репозиториев проектов и доступа к Postgres/S3: всё нужное приходит
по протоколу. Проверка динамическая, по реально загруженным модулям, поэтому ловит и косвенные импорты.
"""

from __future__ import annotations

import json
import subprocess
import sys

_FORBIDDEN_PREFIXES = (
    "hse_doc_studio.api",
    "hse_doc_studio.use_cases",
    "hse_doc_studio.infra.db",
    "hse_doc_studio.infra.repositories",
    "hse_doc_studio.infra.persistence",
    "hse_doc_studio.infra.identity",
    "hse_doc_studio.core.repositories",
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "fastapi",
    "boto3",
    "aiobotocore",
)

_PROBE = """
import json, sys
import hse_doc_studio.infra.di.containers.runner
print(json.dumps(sorted(sys.modules)))
"""


def test_runner_container_imports_no_repositories_or_server_stack() -> None:
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _PROBE], capture_output=True, text=True, check=True, timeout=60
    )
    loaded = json.loads(out.stdout.splitlines()[-1])

    offenders = sorted(
        name for name in loaded if any(name == p or name.startswith(p + ".") for p in _FORBIDDEN_PREFIXES)
    )

    assert offenders == []
