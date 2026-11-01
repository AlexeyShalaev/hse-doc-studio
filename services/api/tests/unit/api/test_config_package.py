from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from hse_doc_studio.api import config
from hse_doc_studio.api.config import (
    AdminConfig,
    AuthConfig,
    DbConfig,
    JobsConfig,
    SecretsConfig,
    Settings,
    StorageConfig,
    settings,
)
from hse_doc_studio.api.config.auth import OidcEnvConfig
from pydantic import SecretStr

pytestmark = pytest.mark.unit

SERVER_ONLY_MODULES = ("sqlalchemy", "asyncpg", "alembic", "boto3", "botocore", "argon2", "aiosmtplib", "joserfc")


def test__config_package__public_import__keeps_legacy_names() -> None:
    assert isinstance(settings, Settings)
    assert all(hasattr(config, name) for name in config.__all__)


def test__settings__server_zone_sections__are_present_with_defaults() -> None:
    fresh = Settings()

    assert isinstance(fresh.auth, AuthConfig)
    assert isinstance(fresh.db, DbConfig)
    assert isinstance(fresh.s3, StorageConfig)
    assert isinstance(fresh.admin, AdminConfig)
    assert isinstance(fresh.secrets, SecretsConfig)
    assert isinstance(fresh.jobs, JobsConfig)


def test__settings__monorepo_packs_dir__resolves_from_the_package_location() -> None:
    assert Settings().packs_dir.name == "packs"
    assert Settings().release_notes_file.name == "release-notes.json"


def test__local_app__without_server_extra__imports_and_builds() -> None:
    script = textwrap.dedent(
        f"""
        import importlib.abc
        import sys

        BLOCKED = {SERVER_ONLY_MODULES!r}

        class Blocker(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in BLOCKED:
                    raise ImportError(f"{{name}} is a server-only dependency")
                return None

        sys.meta_path.insert(0, Blocker())
        from hse_doc_studio.api.entrypoint import create_app

        create_app()
        assert not any(m.split(".")[0] in BLOCKED for m in sys.modules)
        """
    )

    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False, timeout=25)

    assert result.returncode == 0, result.stderr


def test__oidc_env_config__needs_issuer_client_and_secret() -> None:
    assert not OidcEnvConfig().configured
    assert not OidcEnvConfig(issuer="https://idp", client_id="c").configured
    assert OidcEnvConfig(issuer="https://idp", client_id="c", client_secret=SecretStr("s")).configured


def test__oidc_env_config__reads_the_secret_from_a_file(tmp_path: Path) -> None:
    secret_file = tmp_path / "secret"
    secret_file.write_text("from-file\n", encoding="utf-8")

    config = OidcEnvConfig(issuer="https://idp", client_id="c", client_secret_file=secret_file)

    assert config.configured
    assert config.resolved_secret() == "from-file"
