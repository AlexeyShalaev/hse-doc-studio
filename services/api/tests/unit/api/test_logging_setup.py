from __future__ import annotations

from collections.abc import Iterator

import pytest
import structlog
from hse_doc_studio.api.logging_setup import configure_logging

_CANARY = "CorrectHorseBatteryStaple-CANARY"


@pytest.fixture
def restored_structlog() -> Iterator[None]:
    previous = structlog.get_config()
    yield
    structlog.configure(**previous)


def _decrypt(password: str) -> None:
    # Пароль лежит в локальной переменной кадра, как в bundle_crypto.decrypt_stream.
    secret_copy = password
    raise OSError(f"disk full {len(secret_copy)}")


def test__configure_logging__exception_traceback_has_no_local_variables(
    restored_structlog: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging()
    log = structlog.get_logger()

    try:
        _decrypt(_CANARY)
    except OSError:
        log.exception("bundle import failed")

    out = capsys.readouterr().out
    assert "bundle import failed" in out
    assert "disk full" in out
    assert "_decrypt" in out
    assert _CANARY not in out
