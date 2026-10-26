from __future__ import annotations

import pytest
from hse_doc_studio.api.config import GitConfig, Settings


def test__git_config__defaults__match_the_plan() -> None:
    config = Settings().git

    assert config.enabled is True
    assert config.ssh_binary == "ssh"
    assert config.git_min_version == "2.31"
    assert config.allow_insecure_http is False
    assert config.allow_local_remotes is True
    assert (config.probe_timeout_s, config.fetch_timeout_s, config.push_timeout_s, config.clone_timeout_s) == (
        20.0,
        120.0,
        300.0,
        900.0,
    )
    assert config.large_file_warn_bytes == 95_000_000


def test__git_config__env_overrides__are_read_with_the_studio_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HSE_STUDIO__GIT__ENABLED", "false")
    monkeypatch.setenv("HSE_STUDIO__GIT__ALLOW_INSECURE_HTTP", "true")
    monkeypatch.setenv("HSE_STUDIO__GIT__SSH_BINARY", "/opt/ssh")
    monkeypatch.setenv("HSE_STUDIO__GIT__PUSH_TIMEOUT_S", "42")

    config = Settings().git

    assert config.enabled is False
    assert config.allow_insecure_http is True
    assert config.ssh_binary == "/opt/ssh"
    assert config.push_timeout_s == 42.0


def test__git_config__fetch_concurrency__must_be_positive() -> None:
    with pytest.raises(ValueError, match="fetch_concurrency"):
        GitConfig(fetch_concurrency=0)


def test__secrets_config__defaults_to_a_file_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HSE_STUDIO__SECRETS__KEY", "HSE_STUDIO__SECRETS__KEY_FILE"):
        monkeypatch.delenv(name, raising=False)

    secrets = Settings().secrets

    assert secrets.key is None
    assert secrets.key_file is None


def test__secrets_config__env_overrides__are_read_and_the_key_is_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HSE_STUDIO__SECRETS__KEY", "a-very-secret-key-value")
    monkeypatch.setenv("HSE_STUDIO__SECRETS__KEY_FILE", "/run/secrets/hse-key")

    secrets = Settings().secrets

    assert secrets.key is not None
    assert secrets.key.get_secret_value() == "a-very-secret-key-value"
    assert "a-very-secret-key-value" not in repr(secrets)
    assert str(secrets.key_file) == "/run/secrets/hse-key"
