"""Порты подписей: то, что use cases получают от инфраструктуры (gpg, сеть, связка ключей)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.verify import TrustBundle
from hse_doc_studio.core.signatures.pack_places import SourceAnchors
from hse_doc_studio.core.signatures.stamps import Stamp
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
    заполнения плашек перед фиксацией. Сервер смотрит `slot.signer` из состояния подписей, затем сертификат или
    открытый ключ из профиля подписанта (`ProfileSignerPlateData`); локальная Студия только `slot.signer`. Закрытые
    ключи никто не читает; открытую часть своего ключа Студии подписант кладёт в плашку сам на своём шаге.
    """

    async def plate_for(self, state: SignaturesState, slot_id: str, user_id: str | None) -> SignerInfo | None:
        """Данные плашки слота `slot_id` для подписанта `user_id` (None: участник ещё не принял приглашение)."""
        ...


class IMarkMeasure(Protocol):
    """Размер видимой метки на странице: странице подписи нужна рамка места подписи той же высоты, что у метки."""

    def mark_height_mm(self, stamp: Stamp) -> float:
        """Высота картинки по её пропорциям или плашки по вёрстке её строк, в миллиметрах."""
        ...


class IPdfPages(Protocol):
    """Страницы PDF: где можно поставить метку даты (signing-route.md, 14.7)."""

    def page_sizes_mm(self, pdf: Path) -> tuple[tuple[float, float], ...]:
        """Ширина и высота каждой страницы в мм по MediaBox, как их видит штамповщик; пусто, если не прочитать."""
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


class IBuildPlaces(Protocol):
    """Пересчёт мест подписей на якорях шаблона после публикации сборки (signing-route.md, 15.17.9)."""

    async def after_build(self, project_id: UUID, folder: Path, doc_id: str) -> int:
        """Места документа «из шаблона» на якоре по якорям новой сборки; на сервере ещё пары черновиков маршрута без
        места. Возвращает число размещений, которые изменились; 0, если пересчёта нет (версия на подписи, маршрут
        держит документ, ЭП над B, свой PDF, якоря неизвестны). Сбой пересчёта сборку не роняет: вызывающий ловит."""
        ...


class NoBuildPlaces:
    """`IBuildPlaces` там, где пересчёта нет (тесты сборки без состояния подписей)."""

    async def after_build(self, project_id: UUID, folder: Path, doc_id: str) -> int:
        return 0


class IRouteDraftPlaces(Protocol):
    """Маршруты в пересчёте мест после сборки (15.17.9): держит ли маршрут документ и места пар его черновиков."""

    async def apply(
        self, project_id: UUID, doc_id: str, state: SignaturesState, src: SourceAnchors
    ) -> SignaturesState | None:
        """None: документ держит маршрут (`HOLDING_STATUSES`), места не трогать. Иначе состояние, где пары черновиков
        маршрута на этом документе без места или с затравкой получили место пресета, как при создании черновика.
        Вызывается под `project_lock`: только читает маршруты."""
        ...


class NoRouteDraftPlaces:
    """`IRouteDraftPlaces` там, где маршрутов нет (локальная Студия): документ свободен, черновиков нет."""

    async def apply(
        self, project_id: UUID, doc_id: str, state: SignaturesState, src: SourceAnchors
    ) -> SignaturesState | None:
        return state
