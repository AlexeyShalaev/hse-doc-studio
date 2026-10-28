from __future__ import annotations

import time
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


def test__configure_logging__output_has_no_ansi_codes_when_stdout_is_not_a_terminal(
    restored_structlog: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging()

    structlog.get_logger().info("plain line")

    out = capsys.readouterr().out
    assert "plain line" in out
    assert "\x1b" not in out


def test__configure_logging__timestamp_is_local_time_as_before(
    restored_structlog: None, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    try:
        configure_logging()
        before = time.strftime("%Y-%m-%d %H")

        structlog.get_logger().info("stamped")

        out = capsys.readouterr().out
        after = time.strftime("%Y-%m-%d %H")
        assert out.startswith(before) or out.startswith(after)
    finally:
        monkeypatch.undo()
        time.tzset()


def test__configure_logging__use_json_writes_one_json_object_without_locals(
    restored_structlog: None, capsys: pytest.CaptureFixture[str]
) -> None:
    import json  # noqa: PLC0415

    configure_logging(use_json=True)

    try:
        _decrypt(_CANARY)
    except OSError:
        structlog.get_logger().exception("bundle import failed")

    out = capsys.readouterr().out.strip()
    record = json.loads(out)
    assert record["event"] == "bundle import failed"
    assert record["level"] == "error"
    assert "disk full" in record["exception"]
    assert _CANARY not in out
