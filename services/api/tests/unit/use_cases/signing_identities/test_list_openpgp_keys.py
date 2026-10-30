from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.infra.signatures.openpgp import GpgKey
from hse_doc_studio.use_cases.signing_identities.openpgp_keys import ListOpenPgpKeysUC


def _key(fingerprint: str, *, secret: bool) -> GpgKey:
    return GpgKey(fingerprint, fingerprint[-8:], [fingerprint], secret, "ed25519", datetime.now(UTC), None)


class _Keyring:
    available = True

    def list_keys(self) -> list[GpgKey]:
        return [_key("AAAA1111", secret=True), _key("BBBB2222", secret=True), _key("CCCC3333", secret=False)]

    def version(self) -> str:
        return "2.4"


class _Repo:
    async def list_all(self) -> list[Any]:
        return [SimpleNamespace(kind=SigningIdentityKind.openpgp, fingerprint="AAAA1111")]


@pytest.fixture(autouse=True)
def _reset_actor() -> Any:
    yield
    set_current_actor(None)


@pytest.mark.unit
async def test__list_openpgp_keys__server_user__sees_public_keys_and_only_own_secret_ones() -> None:
    set_current_actor(Actor.user("alice"))

    out = await ListOpenPgpKeysUC(_Keyring(), _Repo()).execute()  # type: ignore[arg-type]

    assert [k.fingerprint for k in out.keys] == ["AAAA1111", "CCCC3333"]


@pytest.mark.unit
async def test__list_openpgp_keys__local_actor__sees_the_whole_keyring() -> None:
    set_current_actor(Actor.local())

    out = await ListOpenPgpKeysUC(_Keyring(), _Repo()).execute()  # type: ignore[arg-type]

    assert len(out.keys) == 3
