"""Обработчик signature.verify_detached поверх DetachedSignatureVerifier."""

from __future__ import annotations

import asyncio

from hse_doc_studio.core.jobs.base import JobResultData
from hse_doc_studio.core.jobs.enums import JobErrorCategory
from hse_doc_studio.core.jobs.errors import JobFailure
from hse_doc_studio.core.jobs.protocols import JobContext
from hse_doc_studio.core.jobs.verify import (
    CODE_GPG_UNAVAILABLE,
    CODE_UNKNOWN_SIGNATURE_FORMAT,
    VerifyDetachedPayload,
    VerifyDetachedResult,
)
from hse_doc_studio.core.signatures.errors import GpgUnavailableError, UnknownSignatureFormatError
from hse_doc_studio.infra.signatures.detached_verifier import DetachedSignatureVerifier


class VerifyDetachedHandler:
    """Проверка в потоке: ГОСТ и gpg тяжелые, цикл событий они блокировать не должны.

    Отвечает кодами, текст для пользователя собирает use case. Подписи с вердиктом
    invalid и unknown_key штатный результат, а не сбой.

    Встроенный раннер живет в процессе api, поэтому OpenPGP сверяет с постоянной связкой
    `data_dir/gnupg` в обоих режимах: ключи `inline` api выгрузил из этой же связки, она их
    надмножество, и вердикт совпадает с вердиктом удаленного раннера.
    """

    def __init__(self, verifier: DetachedSignatureVerifier) -> None:
        self._verifier = verifier

    async def handle(self, payload: VerifyDetachedPayload, ctx: JobContext) -> JobResultData:
        pdf_path = ctx.path_of(payload.pdf)
        roots = [blob.to_bytes() for blob in payload.trust.roots]
        intermediates = [blob.to_bytes() for blob in payload.trust.intermediates]
        try:
            verified = await asyncio.to_thread(
                self._verifier.verify_with, pdf_path, payload.signature.to_bytes(), roots, intermediates
            )
        except UnknownSignatureFormatError as exc:
            raise JobFailure.of(JobErrorCategory.invalid_input, CODE_UNKNOWN_SIGNATURE_FORMAT, str(exc)) from exc
        except GpgUnavailableError as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_GPG_UNAVAILABLE) from exc
        return VerifyDetachedResult(signature=verified)
