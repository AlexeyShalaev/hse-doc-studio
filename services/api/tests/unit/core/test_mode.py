import pytest
from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.entrypoint import ensure_supported_mode
from hse_doc_studio.core.mode import StudioMode
from pydantic import ValidationError


def test__settings__no_env__mode_is_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HSE_STUDIO__MODE", raising=False)

    assert Settings(_env_file=None).mode is StudioMode.local


def test__settings__env_server__parses_as_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HSE_STUDIO__MODE", "server")

    assert Settings(_env_file=None).mode is StudioMode.server


def test__settings__env_banana__raises_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HSE_STUDIO__MODE", "banana")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test__ensure_supported_mode__server_unconfigured__raises_with_variable_name_and_missing() -> None:
    with pytest.raises(RuntimeError, match=r"HSE_STUDIO__MODE=server.*HSE_STUDIO__DB__DSN"):
        ensure_supported_mode(Settings(_env_file=None, mode=StudioMode.server))


def test__ensure_supported_mode__local__returns_none() -> None:
    assert ensure_supported_mode(Settings(_env_file=None, mode=StudioMode.local)) is None
