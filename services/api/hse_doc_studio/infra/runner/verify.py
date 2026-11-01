"""signature.verify_detached на раннере: связка ключей живёт одну задачу и собирается только из нагрузки.

Постоянная связка раннера общая для всех пользователей: ключ, импортированный одной задачей,
менял бы вердикт другой (доверие, отзыв). Поэтому OpenPGP-ключи берутся из `trust.openpgp.keys`,
а режим `runner_home` у раннера означает пустую связку: подпись без переданных ключей получит
`unknown_key`, но никогда не `valid`.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from hse_doc_studio.core.jobs.base import JobResultData
from hse_doc_studio.core.jobs.enums import JobErrorCategory
from hse_doc_studio.core.jobs.errors import JobFailure
from hse_doc_studio.core.jobs.protocols import JobContext
from hse_doc_studio.core.jobs.verify import (
    CODE_GPG_UNAVAILABLE,
    CODE_UNKNOWN_SIGNATURE_FORMAT,
    OpenPgpTrustMode,
    VerifyDetachedPayload,
    VerifyDetachedResult,
)
from hse_doc_studio.core.signatures.errors import GpgError, GpgUnavailableError, UnknownSignatureFormatError
from hse_doc_studio.infra.signatures.detached_verifier import DetachedSignatureVerifier
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring

CODE_PDF_MISSING = "pdf_missing"
CODE_OPENPGP_KEY_INVALID = "openpgp_key_invalid"

KeyringFactory = Callable[[Path], GpgKeyring]


class EphemeralVerifyHandler:
    """Проверка в потоке: ГОСТ и gpg тяжёлые, цикл событий они блокировать не должны."""

    def __init__(self, keyring_factory: KeyringFactory = GpgKeyring) -> None:
        self._keyring_factory = keyring_factory

    async def handle(self, payload: VerifyDetachedPayload, ctx: JobContext) -> JobResultData:
        pdf_path = ctx.path_of(payload.pdf)
        if not pdf_path.is_file():
            raise JobFailure.of(JobErrorCategory.invalid_input, CODE_PDF_MISSING, payload.pdf.path)
        return await asyncio.to_thread(self._verify, payload, pdf_path)

    def _verify(self, payload: VerifyDetachedPayload, pdf_path: Path) -> VerifyDetachedResult:
        scratch = Path(tempfile.mkdtemp(prefix="hds-verify-"))
        keyring = self._keyring_factory(scratch / "gnupg")
        try:
            openpgp = payload.trust.openpgp
            if openpgp.mode is OpenPgpTrustMode.inline:
                for key in openpgp.keys:
                    keyring.import_public_key(key.to_bytes())
            verifier = DetachedSignatureVerifier(keyring, scratch / "roots")
            verified = verifier.verify_with(
                pdf_path,
                payload.signature.to_bytes(),
                [blob.to_bytes() for blob in payload.trust.roots],
                [blob.to_bytes() for blob in payload.trust.intermediates],
            )
        except UnknownSignatureFormatError as exc:
            raise JobFailure.of(JobErrorCategory.invalid_input, CODE_UNKNOWN_SIGNATURE_FORMAT, str(exc)) from exc
        except GpgUnavailableError as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_GPG_UNAVAILABLE) from exc
        except GpgError as exc:
            raise JobFailure.of(JobErrorCategory.invalid_input, CODE_OPENPGP_KEY_INVALID, str(exc)) from exc
        finally:
            keyring.stop_agent()
            shutil.rmtree(scratch, ignore_errors=True)
        return VerifyDetachedResult(signature=verified)
