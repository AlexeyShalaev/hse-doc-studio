"""Каталог провайдеров OIDC: окружение побеждает таблицу, выключенные и нечитаемые секреты не попадают во вход."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.identity.entities import OidcProvider
from hse_doc_studio.core.identity.oidc import OidcProviderConfig
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.infra.identity.oidc.catalog import OidcProviderCatalog
from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.secrets.key_store import KeyFileStore

from tests.fakes.auth import InMemoryOidcProviderRepository

NOW = datetime(2026, 10, 30, tzinfo=UTC)


@pytest.fixture
def cipher(tmp_path: Path) -> FernetSecretCipher:
    return FernetSecretCipher(KeyFileStore(tmp_path / "master.keys.json"))


def _row(
    cipher: FernetSecretCipher, provider_id: str = "gitlab", *, enabled: bool = True, secret: str = "table-secret"
) -> OidcProvider:
    token = cipher.encrypt(Secret(secret), aad=column_aad("oidc_providers", "client_secret_enc", provider_id))
    return OidcProvider(provider_id, provider_id.title(), "https://gitlab.test", "cid", token, NOW, enabled=enabled)


async def test_table_provider_is_decrypted(cipher: FernetSecretCipher) -> None:
    repo = InMemoryOidcProviderRepository()
    await repo.save(_row(cipher))

    provider = await OidcProviderCatalog(repo, cipher).get("gitlab")

    assert provider is not None
    assert (provider.client_secret, provider.issuer) == ("table-secret", "https://gitlab.test")


async def test_disabled_and_unknown_providers_are_absent(cipher: FernetSecretCipher) -> None:
    repo = InMemoryOidcProviderRepository()
    await repo.save(_row(cipher, enabled=False))
    catalog = OidcProviderCatalog(repo, cipher)

    assert await catalog.get("gitlab") is None
    assert await catalog.get("nope") is None
    assert await catalog.list_enabled() == []


async def test_env_provider_wins_over_table_with_same_id(cipher: FernetSecretCipher) -> None:
    repo = InMemoryOidcProviderRepository()
    await repo.save(_row(cipher, "sso"))
    env = OidcProviderConfig("sso", "Corp SSO", "https://idp.corp", "env-client", "env-secret")
    await repo.save(_row(cipher, "gitlab"))
    catalog = OidcProviderCatalog(repo, cipher, env)

    assert await catalog.get("sso") == env
    assert await catalog.list_enabled() == [("sso", "Corp SSO"), ("gitlab", "Gitlab")]


async def test_secret_bound_to_another_row_is_unreadable_and_skipped(cipher: FernetSecretCipher) -> None:
    repo = InMemoryOidcProviderRepository()
    stolen = _row(cipher, "gitlab")
    await repo.save(OidcProvider("other", "Other", "https://o.test", "cid", stolen.client_secret_enc, NOW))

    assert await OidcProviderCatalog(repo, cipher).get("other") is None
