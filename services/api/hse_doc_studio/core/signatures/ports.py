"""Порты подписей: то, что use cases получают от инфраструктуры (gpg, сеть, связка ключей)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.verify import TrustBundle
from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo

if TYPE_CHECKING:
    from hse_doc_studio.core.entities import Project


class IOpenPgpKeyImporter(Protocol):
    """Связка ключей OpenPGP в той части, что нужна при прикреплении подписи."""

    def looks_like_public_key(self, blob: bytes) -> bool: ...

    def import_public_key(self, blob: bytes) -> None:
        """Кладет открытый ключ в связку; бросает GpgUnavailableError (нет gpg) или GpgError (ключ не принят)."""
        ...


class IChainFetcher(Protocol):
    """Достройка цепочки сертификатов подписи по ссылкам AIA (единственное место, где Студия ходит в сеть)."""

    def complete(self, sig_bytes: bytes) -> list[str]:
        """Скачивает недостающие сертификаты издателей; бросает CmsParseError, если подпись не CMS."""
        ...


class ITrustMaterialProvider(Protocol):
    """Доверенный материал проверки подписи: корни, кеш цепочек и режим связки OpenPGP."""

    def snapshot(self, signature: bytes | None = None) -> TrustBundle:
        """Материал для проверки; `signature` подсказка: сертификаты OpenPGP-подписи не нужны, их можно не читать."""
        ...


class IPublicKeyExporter(Protocol):
    """Выгрузка открытого OpenPGP-ключа подписанта из связки ключей студии."""

    def export_public(self, fingerprint: str) -> bytes: ...


class ISignerScope(Protocol):
    """Чьи слоты подписывает смотрящий: его персоны в проекте (docs/design/signature-plan.md, раздел 5)."""

    async def personas(self, project: Project) -> frozenset[str]:
        """Слаги авторов и роли руководителей, к которым привязан актор; `author` у владельца solo-проекта.

        Локально человек один: персоны авторов проекта и персоны слотов, где на плашке указан его ключ из Студии.
        Пустое множество: своих слотов нет.
        """
        ...

    def single_user(self) -> bool:
        """Локальная Студия: человек один, персону из членства ему не назначить."""
        ...


class ISignerPlateData(Protocol):
    """Открытые данные плашки слота, известные о его подписанте (docs/design/signing-route.md, разделы 4.2 и 6.5).

    Маршрут подписания берёт их для расчёта L (плашка без данных меняет видимый слой на шаге подписанта) и для
    заполнения плашек перед фиксацией. Полная реализация смотрит `slot.signer` из состояния подписей, затем сертификат
    или открытый ключ из профиля подписанта, затем открытую часть его ключа по умолчанию; закрытые ключи чужих людей
    она не читает. До сценариев подписанта (срез R6) работает заглушка, которая читает только `slot.signer`.
    """

    async def plate_for(self, state: SignaturesState, slot_id: str, user_id: str | None) -> SignerInfo | None:
        """Данные плашки слота `slot_id` для подписанта `user_id` (None: участник ещё не принял приглашение)."""
        ...


class ISignatureAudit(Protocol):
    """Аудит действий с подписями: сервер пишет в журнал аудита, локально строка лога.

    В `details` только идентификаторы, способ, формат и вердикт: без паролей, ключей и содержимого файлов.
    """

    async def record(self, action: str, *, project_id: UUID | None, details: Mapping[str, object]) -> None: ...


@dataclass(frozen=True)
class PadesCheck:
    """Проверка одной встроенной подписи PDF без обращения к сети.

    `intact` дайджест и подпись сходятся; `covers` подпись покрывает свою ревизию целиком; `modifications_ok`
    всё, что дописано после неё, разрешено (только новые подписи и поля подписи); `revision_size` длина файла,
    которую подпись покрывает.
    """

    field_name: str
    intact: bool
    covers: bool
    modifications_ok: bool
    revision_size: int
    signer: str
    signer_id: str  # SHA-256 сертификата
    signed_at: str | None = None


class IPadesSigner(Protocol):
    """Встроенные подписи PAdES поверх зафиксированного PDF: только дописыванием, байты до подписи не меняются."""

    async def sign_incremental(self, source: Path, output: Path, field_name: str, key_dir: Path, reason: str) -> None:
        """Пишет в `output` байты `source` и одну ревизию с невидимым полем подписи `field_name`."""
        ...

    async def validate(self, pdf: Path) -> list[PadesCheck]:
        """Все встроенные подписи файла в порядке ревизий."""
        ...
