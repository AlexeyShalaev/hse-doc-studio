"""Прикрепление и достройка цепочки ходят в gpg и сеть только через порты ядра.

Use cases видят IOpenPgpKeyImporter и IChainFetcher, а не GpgKeyring и ChainFetcher. Тесты
подменяют методы реализаций, на которые указывает порт, и проверяют, что ответы API те же:
коды, дословные тексты на ru и en, перепроверка после достройки.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.signatures.errors import CmsParseError, GpgError, GpgUnavailableError
from hse_doc_studio.infra.signatures.chain_fetcher import ChainFetcher
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from httpx import AsyncClient
from pytest_mock import MockerFixture

from tests.integration.api.signatures.test_error_contracts import (
    _ISSUER_URL,
    _NO_GPG,
    _NOT_A_KEY,
    _PGP_PUBLIC_KEY,
    _frozen_project,
    _post_attach,
    _post_complete_chain,
    _rsa_chain,
    _signature_state,
    _text,
)
from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity


@pytest.mark.parametrize("lang", ["ru", "en"])
async def test__attach__public_key_not_pgp_block__same_localized_400(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture, lang: str
) -> None:
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")
    imported = mocker.patch.object(GpgKeyring, "import_public_key")

    resp = await _post_attach(
        test_app, project_id, make_detached_cms(make_identity(), frozen), lang, public_key=b"not a key"
    )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == _text(_NOT_A_KEY, lang)
    imported.assert_not_called()
    assert await _signature_state(test_app, project_id) == {}


async def test__attach__public_key__goes_through_importer_before_verification(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")
    imported = mocker.patch.object(GpgKeyring, "import_public_key")

    resp = await _post_attach(
        test_app, project_id, make_detached_cms(make_identity(), frozen), public_key=_PGP_PUBLIC_KEY
    )

    assert resp.status_code == 200, resp.text
    imported.assert_called_once_with(_PGP_PUBLIC_KEY)


@pytest.mark.parametrize("lang", ["ru", "en"])
async def test__attach__importer_unavailable__no_gpg_text(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture, lang: str
) -> None:
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")
    mocker.patch.object(GpgKeyring, "import_public_key", side_effect=GpgUnavailableError("no gpg"))

    resp = await _post_attach(
        test_app, project_id, make_detached_cms(make_identity(), frozen), lang, public_key=_PGP_PUBLIC_KEY
    )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == _text(_NO_GPG, lang)


async def test__attach__importer_refuses_key__400_with_gpg_message(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")
    mocker.patch.object(GpgKeyring, "import_public_key", side_effect=GpgError("no OpenPGP key found in the file"))

    resp = await _post_attach(
        test_app, project_id, make_detached_cms(make_identity(), frozen), public_key=_PGP_PUBLIC_KEY
    )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "no OpenPGP key found in the file"


async def test__complete_chain__fake_fetcher__rechecks(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")
    sig, _ = _rsa_chain(_ISSUER_URL, frozen)
    assert (await _post_attach(test_app, project_id, sig)).status_code == 200
    complete = mocker.patch.object(ChainFetcher, "complete", return_value=[])

    resp = await _post_complete_chain(test_app, project_id)

    assert resp.status_code == 200, resp.text
    # Цепочку достраивает порт на сохраненной подписи, а затем подпись проверяется заново.
    complete.assert_called_once_with(sig)
    assert resp.json()["signature"]["verdict"] == "valid"
    assert resp.json()["signature"]["current"] is True


@pytest.mark.parametrize("lang", ["ru", "en"])
async def test__complete_chain__fetcher_rejects_blob__400_with_localized_text(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture, lang: str
) -> None:
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")
    sig, _ = _rsa_chain(_ISSUER_URL, frozen)
    assert (await _post_attach(test_app, project_id, sig)).status_code == 200
    mocker.patch.object(ChainFetcher, "complete", side_effect=CmsParseError("not a SignedData structure"))

    resp = await _post_complete_chain(test_app, project_id, lang)

    assert resp.status_code == 400, resp.text
    expected = ("Цепочку можно достраивать только для подписи CMS/CAdES", "Only CMS/CAdES signatures have a chain")
    assert resp.json()["detail"] == _text(expected, lang)
