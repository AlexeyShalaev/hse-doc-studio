"""План подписей документа: слоты, способ, подписант, статус и проверка (docs/design/signature-plan.md).

Чистые данные и чистый расчёт. Состояние подписей (`SignaturesState`) хранит то, что сделано: картинки,
размещения, зафиксированный PDF, файлы открепленных подписей и встроенные PAdES. План отвечает на вопрос
«кто, каким способом и чего не хватает» и одинаково считается для счётчика, сдачи и MCP.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.access.entities import Grant, Role
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import DetachedVerdict, ProjectStaffing, SignMode
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.invitations.entities import SUPERVISOR_PERSONAS
from hse_doc_studio.core.team import split_instance_id
from hse_doc_studio.core.value_objects import (
    DetachedSignature,
    EmbeddedSignature,
    FrozenPdf,
    PinnedPdf,
    SignatureSlot,
    SignaturesState,
    SkippedSlot,
)

# Персона одиночного автора: в solo у автора нет слага, слот `author` принадлежит владельцу проекта.
AUTHOR_PERSONA = "author"


class SignMethod(StrEnum):
    """Способ подписи слота. Картинка не ЭП: она графическая и в счётчике, и в комплекте."""

    image = "image"  # графическая подпись: картинка на странице
    detached = "detached"  # открепленная ЭП: отдельный файл к зафиксированному PDF
    pades = "pades"  # встроенная ЭП PAdES: инкрементальное обновление поверх зафиксированного PDF


CRYPTO_METHODS = frozenset({SignMethod.detached, SignMethod.pades})


class VisibleMark(StrEnum):
    """Что видно на странице. Всё видимое ставится до фиксации и входит в подписанные байты."""

    png = "png"
    plate = "plate"  # плашка «Подписано с помощью открепленной электронной подписи»
    none = "none"


class SlotStatus(StrEnum):
    pending = "pending"  # ждёт
    signed = "signed"  # подписано
    invalid = "invalid"  # недействительно
    stale = "stale"  # устарело: подпись относится к прежней версии документа
    skipped = "skipped"  # не требуется: маршрут пропустил подписанта (signing-route.md, 13.3)


class PlanReason(StrEnum):
    """Чего не хватает слоту; клиент показывает подсказку `hint`, MCP отдаёт код как есть."""

    placement_off = "placement_off"
    # Видимая метка придержана маршрутом подписания до согласия подписанта (docs/design/signing-route.md, 6.1).
    awaiting_approval = "awaiting_approval"
    no_image = "no_image"
    not_built = "not_built"
    not_frozen = "not_frozen"
    rebuilt = "rebuilt"
    marks_changed = "marks_changed"
    no_signature_file = "no_signature_file"
    no_embedded = "no_embedded"
    other_pdf = "other_pdf"
    invalid_signature = "invalid_signature"
    unknown_key = "unknown_key"
    method_not_allowed = "method_not_allowed"


def method_of(mode: SignMode) -> SignMethod:
    if mode in (SignMode.detached, SignMode.detached_text):
        return SignMethod.detached
    if mode in (SignMode.image_crypto, SignMode.crypto_invisible):
        return SignMethod.pades
    return SignMethod.image


def mark_of(slot: SignatureSlot | None) -> VisibleMark:
    mode = slot.sign_mode if slot is not None else SignMode.image
    if mode is SignMode.detached_text:
        return VisibleMark.plate
    if mode is SignMode.crypto_invisible:
        return VisibleMark.none
    return VisibleMark.png


def slot_persona(slot_id: str) -> str:
    """Персона, которой принадлежит слот: слаг автора, роль руководителя или одиночный автор."""
    base, owner = split_instance_id(slot_id)
    if owner:
        return owner
    if base in SUPERVISOR_PERSONAS:
        return base
    return AUTHOR_PERSONA


def author_personas(project: Project) -> frozenset[str]:
    """Персоны авторов: в solo одна `author`, в команде слаги авторов, чей комплект ведёт этот проект."""
    if project.staffing != ProjectStaffing.team:
        return frozenset({AUTHOR_PERSONA})
    return frozenset(a.slug for a in project.authors if a.slug and a.managed)


def grant_personas(project: Project, grant: Grant | None) -> frozenset[str]:
    """Персоны участника по его праву: привязка из приглашения, а владелец solo-проекта ещё и автор."""
    if grant is None:
        return frozenset()
    personas = {grant.persona_slug} if grant.persona_slug else set()
    if grant.role is Role.owner and project.staffing != ProjectStaffing.team:
        personas.add(AUTHOR_PERSONA)
    return frozenset(personas)


@dataclass(frozen=True)
class DocFacts:
    """Что известно о документе вне состояния подписей.

    `compiled_sha256` хэш источника подписи (signing-route.md, 12.4): версии на подписи, если она есть, иначе
    текущей сборки; None, если файла нет. Это «что подписывают»: по нему сверяется фиксация и считается отпечаток
    согласия маршрута. `working_sha256` хэш текущей сборки (None, если PDF не собран); он нужен только для показа
    «есть изменения после отправки на подпись». `marks_digest` отпечаток видимого слоя, который поставила бы
    фиксация сейчас; `legacy_marks_digest` тот же слой по прежней формуле с абсолютными путями
    (`legacy_stamps_digest`), им сверяются фиксации, сделанные до её замены; `png_exists` проверяет картинку
    слота на диске.
    """

    compiled_sha256: str | None
    marks_digest: str
    png_exists: Callable[[str], bool] = lambda _path: True
    legacy_marks_digest: str = ""
    working_sha256: str | None = None

    @property
    def working_differs(self) -> bool:
        """Рабочая сборка разошлась с источником подписи: собрана и не равна ему (12.4)."""
        return self.working_sha256 is not None and self.working_sha256 != self.compiled_sha256

    def marks_match(self, stored: str) -> bool:
        """Отпечаток фиксации совпадает с текущим видимым слоем; пустой (старые фиксации) совпадает всегда."""
        if not stored or stored == self.marks_digest:
            return True
        return bool(self.legacy_marks_digest) and stored == self.legacy_marks_digest


@dataclass(frozen=True)
class SlotCheck:
    """Проверка подписи слота: вердикт и подписант из самой подписи, а не из плашки."""

    format: str  # "openpgp" | "cms" | "pades"
    verdict: DetachedVerdict
    signer: str
    signer_id: str
    signed_at: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SlotState:
    method: SignMethod
    mark: VisibleMark
    status: SlotStatus
    reason: PlanReason | None = None
    check: SlotCheck | None = None

    @property
    def crypto(self) -> bool:
        return self.method in CRYPTO_METHODS


def _detached_check(sig: DetachedSignature) -> SlotCheck:
    return SlotCheck(
        format=sig.format.value,
        verdict=sig.verdict,
        signer=sig.signer,
        signer_id=sig.signer_id,
        signed_at=sig.signed_at,
        notes=sig.notes,
    )


def _embedded_check(sig: EmbeddedSignature) -> SlotCheck:
    return SlotCheck(
        format="pades",
        verdict=sig.verdict,
        signer=sig.signer,
        signer_id=sig.signer_id,
        signed_at=sig.signed_at,
        notes=sig.notes,
    )


def frozen_is_current(frozen: FrozenPdf, facts: DocFacts) -> PlanReason | None:
    """Почему зафиксированный PDF уже не та версия, что видят сейчас; None, если та."""
    if facts.compiled_sha256 is not None and facts.compiled_sha256 != frozen.source_sha256:
        return PlanReason.rebuilt
    if not facts.marks_match(frozen.stamps_digest):
        return PlanReason.marks_changed
    return None


def slot_state(  # noqa: C901, PLR0911, PLR0912 — таблица статусов из дизайна, разбитая на ветки
    state: SignaturesState,
    doc_id: str,
    slot_id: str,
    facts: DocFacts,
    *,
    allowed: Sequence[str] = (),
    uses_frozen: bool = False,
    profile_id: str | None = None,
) -> SlotState:
    """Статус одного слота на одном документе.

    `allowed` способы, которые разрешает профиль сдачи (пусто: любой). `uses_frozen` документ сдаётся из
    зафиксированного файла (на нём есть криптоподпись): тогда картинка, поставленная после фиксации, в
    сдаваемом файле не видна и считается устаревшей. `profile_id` точка, на которой смотрят слот: пропуск
    другой точки слот не пропускает (signing-route.md, 13.3); без точки считается любой пропуск.
    """
    slot = state.slots.get(slot_id)
    placement = state.placements.get(doc_id, {}).get(slot_id)
    method = method_of(slot.sign_mode if slot is not None else SignMode.image)
    mark = mark_of(slot)
    if state.skip_of(doc_id, slot_id, profile_id) is not None:
        return SlotState(method, mark, SlotStatus.skipped)
    if allowed and method.value not in allowed:
        return SlotState(method, mark, SlotStatus.pending, PlanReason.method_not_allowed)
    if mark is not VisibleMark.none and (placement is None or not placement.enabled):
        return SlotState(method, mark, SlotStatus.pending, PlanReason.placement_off)
    # Размещение остаётся включённым: слот не выпадает из плана, пока метка ждёт согласия.
    if mark is not VisibleMark.none and state.is_withheld(doc_id, slot_id):
        return SlotState(method, mark, SlotStatus.pending, PlanReason.awaiting_approval)
    if mark is VisibleMark.png and (slot is None or slot.png_path is None or not facts.png_exists(slot.png_path)):
        return SlotState(method, mark, SlotStatus.pending, PlanReason.no_image)

    frozen = state.frozen.get(doc_id)
    if method is SignMethod.image:
        if uses_frozen and frozen is not None and (outdated := frozen_is_current(frozen, facts)) is not None:
            return SlotState(method, mark, SlotStatus.stale, outdated)
        return SlotState(method, mark, SlotStatus.signed)

    detached = state.detached.get(doc_id, {}).get(slot_id) if method is SignMethod.detached else None
    embedded = state.embedded.get(doc_id, {}).get(slot_id) if method is SignMethod.pades else None
    check = _detached_check(detached) if detached else _embedded_check(embedded) if embedded else None
    if frozen is None:
        reason = PlanReason.not_built if facts.compiled_sha256 is None else PlanReason.not_frozen
        return SlotState(method, mark, SlotStatus.pending, reason, check)
    outdated = frozen_is_current(frozen, facts)
    if outdated is not None:
        return SlotState(method, mark, SlotStatus.stale if check else SlotStatus.pending, outdated, check)
    if method is SignMethod.detached:
        if detached is None:
            return SlotState(method, mark, SlotStatus.pending, PlanReason.no_signature_file)
        if detached.pdf_sha256 != frozen.sha256:
            return SlotState(method, mark, SlotStatus.stale, PlanReason.other_pdf, check)
    else:
        if embedded is None:
            return SlotState(method, mark, SlotStatus.pending, PlanReason.no_embedded)
        if embedded.base_sha256 != frozen.sha256:
            return SlotState(method, mark, SlotStatus.stale, PlanReason.other_pdf, check)
    assert check is not None  # noqa: S101 — одна из подписей выше найдена
    if check.verdict is DetachedVerdict.invalid:
        return SlotState(method, mark, SlotStatus.invalid, PlanReason.invalid_signature, check)
    if check.verdict is DetachedVerdict.unknown_key:
        return SlotState(method, mark, SlotStatus.pending, PlanReason.unknown_key, check)
    return SlotState(method, mark, SlotStatus.signed, None, check)


_HINTS: dict[PlanReason, tuple[str, str]] = {
    PlanReason.method_not_allowed: (
        "Этот способ подписи не принимается на этой контрольной точке: выберите другой в настройках слота",
        "This signing method is not accepted at this checkpoint: pick another one in the slot settings",
    ),
    PlanReason.placement_off: (
        "Подпись не размещена на документе: включите её в панели «Подписи»",
        "The signature is not placed on the document: turn it on in the Signatures panel",
    ),
    PlanReason.awaiting_approval: (
        "Ждёт согласования подписанта по маршруту",
        "Waiting for the signer's approval in the signing route",
    ),
    PlanReason.no_image: ("Загрузите картинку подписи", "Upload the signature image"),
    PlanReason.not_built: ("Документ не собран: соберите его", "The document is not built: build it"),
    PlanReason.not_frozen: (
        "PDF не зафиксирован на подпись: зафиксируйте его или нажмите «Подписать комплект»",
        "The PDF is not frozen for signing: freeze it or press “Sign the submission”",
    ),
    PlanReason.rebuilt: (
        "Документ пересобран после фиксации: зафиксируйте PDF заново и подпишите новую версию",
        "The document was rebuilt after freezing: freeze the PDF again and sign the new version",
    ),
    PlanReason.marks_changed: (
        "Картинки или плашки изменились после фиксации: зафиксируйте PDF заново",
        "Images or plates changed after freezing: freeze the PDF again",
    ),
    PlanReason.no_signature_file: (
        "PDF зафиксирован, нет файла подписи: подпишите в Студии или загрузите .asc/.sig",
        "The PDF is frozen but has no signature file: sign in the Studio or upload an .asc/.sig",
    ),
    PlanReason.no_embedded: (
        "PDF зафиксирован, встроенной подписи нет: подпишите в Студии ключом с сертификатом X.509",
        "The PDF is frozen but not signed: sign in the Studio with an X.509 certificate key",
    ),
    PlanReason.other_pdf: (
        "Подпись относится к другой фиксации PDF: подпишите текущую",
        "The signature belongs to another frozen PDF: sign the current one",
    ),
    PlanReason.invalid_signature: (
        "Подпись не сходится с PDF: подпишите заново",
        "The signature does not match the PDF: sign again",
    ),
    PlanReason.unknown_key: (
        "Подпись не проверить: загрузите открытый ключ подписанта",
        "The signature cannot be checked: upload the signer's public key",
    ),
}


# Подсказки документа с версией на подписи (signing-route.md, 12.9): `rebuilt` там значит, что отправлена новая
# версия, а зафиксированный PDF сделан из прежней.
_PINNED_HINTS: dict[PlanReason, tuple[str, str]] = {
    PlanReason.rebuilt: ("Ждёт фиксации новой версии", "Waiting for the new version to be frozen"),
}


def reason_hint(reason: PlanReason | None, *, pinned: bool = False) -> str:
    """Что сделать человеку, на языке интерфейса. `pinned` у документа есть версия на подписи."""
    if reason is None:
        return ""
    ru, en = (_PINNED_HINTS.get(reason) if pinned else None) or _HINTS[reason]
    return localized_error(ru, en)


@dataclass(frozen=True)
class SignerRef:
    """Подписант слота: персона проекта и её имя из карточки проекта."""

    persona: str
    name: str = ""


def signer_for(project: Project, slot_id: str) -> SignerRef:
    """Персона слота и имя человека из карточки проекта."""
    persona = slot_persona(slot_id)
    person = {
        "supervisor": project.supervisor,
        "co_supervisor": project.co_supervisor,
        "academic_supervisor": project.academic_supervisor,
    }.get(persona)
    if person is not None:
        return SignerRef(persona, person.name)
    if persona == AUTHOR_PERSONA:
        return SignerRef(persona, project.authors[0].name if project.authors else "")
    author = next((a for a in project.authors if a.slug == persona), None)
    return SignerRef(persona, author.name if author else "")


@dataclass(frozen=True)
class PlanSlot:
    doc_id: str
    slot_id: str
    label: dict[str, str]
    signer: SignerRef
    mode: SignMode
    state: SlotState
    allowed_methods: tuple[str, ...] = ()
    required_by: tuple[str, ...] = ()
    is_mine: bool = False
    # У документа есть версия на подписи: подсказка `rebuilt` другая (12.9).
    pinned: bool = False
    # Подпись необязательна на точке (signing-route.md, 13.3) и пропуск, если маршрут её пропустил.
    optional: bool = False
    skipped: SkippedSlot | None = None

    @property
    def status(self) -> SlotStatus:
        return self.state.status

    @property
    def counted(self) -> bool:
        """Слот входит в счётчик «подписано k из n»: не пропущен и не необязательный неподписанный (13.3)."""
        if self.status is SlotStatus.skipped:
            return False
        return not (self.optional and self.status is not SlotStatus.signed)

    @property
    def hint(self) -> str:
        return reason_hint(self.state.reason, pinned=self.pinned)


@dataclass(frozen=True)
class DocPlan:
    """План документа. `built` есть источник подписи (версия на подписи или сборка); `pinned` версия на
    подписи (signing-route.md, 12.3), `working_differs` рабочая сборка разошлась с ней (12.4)."""

    doc_id: str
    built: bool
    frozen: FrozenPdf | None
    frozen_outdated: PlanReason | None
    slots: tuple[PlanSlot, ...]
    pinned: PinnedPdf | None = None
    working_differs: bool = False

    @property
    def has_crypto(self) -> bool:
        """Есть слот ЭП; пропущенный не считается: документ, где ЭП больше никто не ставит, сдаётся без ЭП (13.3)."""
        return any(s.state.crypto and s.status is not SlotStatus.skipped for s in self.slots)


@dataclass(frozen=True)
class SignaturePlan:
    docs: tuple[DocPlan, ...]
    profile_id: str | None = None
    personas: frozenset[str] | None = None  # персоны смотрящего; None — неизвестны

    @property
    def slots(self) -> tuple[PlanSlot, ...]:
        return tuple(s for d in self.docs for s in d.slots)

    @property
    def total(self) -> int:
        """Сколько подписей нужно: без пропущенных и без необязательных неподписанных (signing-route.md, 13.3)."""
        return sum(1 for s in self.slots if s.counted)

    @property
    def signed(self) -> int:
        return sum(1 for s in self.slots if s.counted and s.status is SlotStatus.signed)

    @property
    def optional_pending(self) -> int:
        """Необязательные подписи, которые ещё можно поставить: не подписаны и не пропущены (13.3)."""
        return sum(1 for s in self.slots if s.optional and s.status not in _SETTLED)

    @property
    def waiting_for_me(self) -> int:
        return sum(1 for s in self.slots if s.is_mine and s.status not in _SETTLED)


# Слот больше ничего не ждёт: подписан или пропущен маршрутом.
_SETTLED = frozenset({SlotStatus.signed, SlotStatus.skipped})


_METHOD_NAMES = {
    "image": ("картинка", "image"),
    "detached": ("открепленная ЭП", "detached e-signature"),
    "pades": ("встроенная ЭП (PAdES)", "embedded e-signature (PAdES)"),
}


def _names(methods: Sequence[str], lang_index: int) -> str:
    return ", ".join(_METHOD_NAMES.get(m, (m, m))[lang_index] for m in methods)


def slot_mode_conflict(
    mode: SignMode,
    identity_kind: str | None,
    restrictions: Sequence[tuple[str, tuple[str, ...]]],
) -> str | None:
    """Почему способ слота несовместим в принципе; None, если совместим.

    Проверяется при настройке слота, а не при сдаче. `identity_kind` вид ключа, назначенного слоту
    (`SigningIdentityKind`), `restrictions` пары «название точки, разрешённые способы» по каждой точке,
    которая требует этот слот (пустой кортеж: любой способ). Запрещено:
    - PAdES ключом OpenPGP: встроенная подпись PDF строится только на сертификате X.509;
    - способ, который не принимает ни одна точка, требующая слот: такой подписью нечего сдавать.
    """
    method = method_of(mode)
    if method is SignMethod.pades and identity_kind == "openpgp":
        return localized_error(
            "Встроенная подпись PAdES делается только ключом с сертификатом X.509 (PKCS#12). "
            "Ключ OpenPGP подходит для открепленной подписи .asc",
            "An embedded PAdES signature needs a key with an X.509 certificate (PKCS#12). "
            "An OpenPGP key fits a detached .asc signature",
        )
    if restrictions and all(allowed and method.value not in allowed for _, allowed in restrictions):
        points = "; ".join(f"{name}: {_names(allowed, 0)}" for name, allowed in restrictions)
        points_en = "; ".join(f"{name}: {_names(allowed, 1)}" for name, allowed in restrictions)
        return localized_error(
            f"Способ «{_names([method.value], 0)}» не принимает ни одна контрольная точка с этим слотом ({points})",
            f"No checkpoint with this slot accepts “{_names([method.value], 1)}” ({points_en})",
        )
    return None


class SlotModeConflictError(ValueError):
    """Способ слота несовместим в принципе: настройка отклоняется сразу, а не при сдаче."""


def profile_restrictions(
    project: Project, version: TemplateVersion, slot_id: str, lang: str
) -> list[tuple[str, tuple[str, ...]]]:
    """Пары «точка сдачи, разрешённые способы» по каждой точке, где пункт требует этот слот."""
    base = slot_id.split("--", 1)[0]
    profiles = version.pack_submission.profiles if version.pack_submission is not None else ()
    result: list[tuple[str, tuple[str, ...]]] = []
    for profile in profiles:
        for item in profile.items:
            if base not in item.signatures or str(project.kind) not in item.supported_kinds:
                continue
            name = profile.name.get(lang) or profile.name.get("ru") or profile.id
            result.append((name, item.allowed_methods(base)))
    return result
