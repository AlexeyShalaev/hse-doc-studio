"""Нагрузка и результат задачи signature.verify_detached: проверка открепленной подписи замороженного PDF.

Исходник PDF едет ссылкой (`ManifestFile` с хешем замороженной копии), подпись и
доверенный материал внутри нагрузки. Для OpenPGP-подписи api выгружает из связки
`data_dir/gnupg` открытые ключи ее издателей (`OpenPgpTrustMode.inline`): удаленный
раннер строит из них временную связку, встроенный сверяет с той же связкой Студии.
`runner_home` остается для CMS и для api без gpg: удаленный раннер в этом режиме
проверяет по пустой связке и отвечает `unknown_key`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.jobs.base import JobPayload, JobResultData
from hse_doc_studio.core.jobs.files import InlineBlob, ManifestFile
from hse_doc_studio.core.signatures.verification import VerifiedSignature

# Коды сбоев JobError; текст для пользователя собирает use case по коду.
CODE_UNKNOWN_SIGNATURE_FORMAT = "unknown_signature_format"
CODE_GPG_UNAVAILABLE = "gpg_unavailable"


class OpenPgpTrustMode(StrEnum):
    # Встроенный раннер сверяет подпись с постоянной связкой Студии (data_dir/gnupg),
    # удаленный с пустой: ключей у него нет.
    runner_home = "runner_home"
    # Открытые ключи едут в `OpenPgpTrust.keys`; раннер строит временную связку.
    inline = "inline"


@dataclass(frozen=True)
class OpenPgpTrust:
    mode: OpenPgpTrustMode = OpenPgpTrustMode.runner_home
    # Armored-блоки открытых ключей; только при mode=inline.
    keys: tuple[InlineBlob, ...] = ()
    # Адрес содержимого `keys` (sha256 от sha256 блоков по порядку) для кеша временных связок у раннера.
    digest: str = ""


@dataclass(frozen=True)
class TrustBundle:
    """Доверенный материал проверки, собранный на стороне api; только открытые данные."""

    # Корни, которым доверяет пользователь (data_dir/trusted_roots), DER или PEM.
    roots: tuple[InlineBlob, ...] = ()
    # Сертификаты издателей из кеша цепочек: строят цепочку, доверия не дают.
    intermediates: tuple[InlineBlob, ...] = ()
    openpgp: OpenPgpTrust = OpenPgpTrust()


@dataclass(frozen=True)
class VerifyDetachedPayload(JobPayload):
    # Замороженный PDF; sha256 это хеш из записи заморозки.
    pdf: ManifestFile
    signature: InlineBlob
    trust: TrustBundle


@dataclass(frozen=True)
class VerifyDetachedResult(JobResultData):
    signature: VerifiedSignature
