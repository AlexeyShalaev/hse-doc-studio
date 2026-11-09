"""«Подписать комплект»: одно действие по всем документам профиля сдачи (docs/design/signature-plan.md, раздел 7).

Два шага. Предпросмотр говорит, что будет сделано: какие PDF зафиксировать, чьи подписи это сбросит, какие слоты
актора подписать и каким ключом, что мешает. Подпись повторяет расчёт и сверяет отпечатки документов с теми, что
видел человек: пересборка между шагами даёт отказ, а не подпись новой версии.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from uuid import UUID

import structlog

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker, ProjectForbiddenError
from hse_doc_studio.core.entities import Project, SigningIdentity
from hse_doc_studio.core.enums import SigningIdentityKind, SignMode
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signatures.plan import (
    CRYPTO_METHODS,
    DocPlan,
    PlanReason,
    PlanSlot,
    SignMethod,
    SlotStatus,
    reason_hint,
)
from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signatures._doc_context import load_doc_context
from hse_doc_studio.use_cases.signatures._studio_signer import (
    X509_KINDS,
    KeyPassphraseRequiredError,
    SlotNotYoursError,
    StudioSigner,
    project_lock,
    signer_for_identity,
)
from hse_doc_studio.use_cases.signatures.default_key import DefaultSigningKey
from hse_doc_studio.use_cases.signatures.freeze_pdf import FreezePdfInput, FreezePdfUC
from hse_doc_studio.use_cases.signatures.get_signature_plan import (
    GetSignaturePlanInput,
    GetSignaturePlanUC,
    doc_facts,
)

logger = structlog.get_logger()

# Причины, которые снимает только человек руками: способ, размещение, картинка, сборка.
_MANUAL = frozenset(
    {PlanReason.method_not_allowed, PlanReason.placement_off, PlanReason.no_image, PlanReason.not_built}
)


class SigningConflictError(Exception):
    """409: документ изменился после предпросмотра или фиксация сбросит чужие подписи без подтверждения."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class SignSubmissionInput:
    project_id: UUID
    profile_id: str
    author: str | None = None
    identity_id: UUID | None = None
    passphrase: str = field(default="", repr=False)
    confirm_reset: bool = False
    # Отпечатки документов из предпросмотра (doc_id -> token); None: подписать то, что есть сейчас (MCP).
    expected: dict[str, str] | None = None


@dataclass(frozen=True)
class KeyInfo:
    id: UUID
    label: str
    kind: str
    protected: bool
    auto: bool
    signer: str


@dataclass(frozen=True)
class ResetItem:
    slot_id: str
    label: dict[str, str]
    signer: str
    method: str


@dataclass(frozen=True)
class SlotAction:
    slot_id: str
    label: dict[str, str]
    method: SignMethod
    status: SlotStatus
    # "stamp": картинка встанет при фиксации; "sign": подпись ключом; "none": уже готово.
    action: str
    blocker: str = ""


@dataclass(frozen=True)
class DocPreview:
    doc_id: str
    token: str
    needs_freeze: bool
    can_freeze: bool
    resets: tuple[ResetItem, ...]
    slots: tuple[SlotAction, ...]
    blocker: str = ""


@dataclass(frozen=True)
class SignSubmissionPreview:
    profile_id: str
    key: KeyInfo | None
    docs: tuple[DocPreview, ...]

    @property
    def needs_passphrase(self) -> bool:
        return self.key is not None and self.key.protected and self.to_sign > 0

    @property
    def to_sign(self) -> int:
        return sum(1 for d in self.docs if not d.blocker for s in d.slots if s.action == "sign" and not s.blocker)

    @property
    def resets(self) -> tuple[ResetItem, ...]:
        return tuple(r for d in self.docs if d.needs_freeze and not d.blocker for r in d.resets)


@dataclass(frozen=True)
class SlotResult:
    doc_id: str
    slot_id: str
    ok: bool
    message: str = ""


@dataclass(frozen=True)
class SignSubmissionOutput:
    preview: SignSubmissionPreview
    frozen_docs: tuple[str, ...]
    results: tuple[SlotResult, ...]


class SignSubmissionUC:
    def __init__(  # noqa: PLR0913 — порты сценария перечислены явно
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        plan_uc: GetSignaturePlanUC,
        freeze_uc: FreezePdfUC,
        signer: StudioSigner,
        default_key: DefaultSigningKey,
        access: IProjectAccessChecker,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._plan_uc = plan_uc
        self._freeze_uc = freeze_uc
        self._signer = signer
        self._default_key = default_key
        self._access = access
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def preview(self, inp: SignSubmissionInput) -> SignSubmissionPreview:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        identity = await self._default_key.resolve(inp.identity_id)
        signer = await self._key_signer(identity)
        plan = await self._plan_uc.execute(
            GetSignaturePlanInput(project_id=inp.project_id, profile_id=inp.profile_id, author=inp.author)
        )
        state = self._signature_repo.get_state(project.folder)
        docs: list[DocPreview] = []
        for doc in plan.docs:
            item = await self._doc_preview(project, state, doc, identity, signer)
            if item is not None:
                docs.append(item)
        key = (
            KeyInfo(
                id=identity.id,
                label=identity.label,
                kind=identity.kind.value,
                protected=identity.protected and identity.kind is SigningIdentityKind.openpgp,
                auto=inp.identity_id is None and (await self._default_key.get()).auto,
                signer=signer.owner if signer is not None else identity.subject_cn,
            )
            if identity is not None
            else None
        )
        return SignSubmissionPreview(profile_id=inp.profile_id, key=key, docs=tuple(docs))

    async def execute(self, inp: SignSubmissionInput) -> SignSubmissionOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        async with project_lock(project):
            preview = await self.preview(inp)
            self._check_confirmations(inp, preview)
            identity = await self._default_key.resolve(inp.identity_id)
            signer = await self._key_signer(identity)
            frozen_docs: list[str] = []
            results: list[SlotResult] = []
            for doc in preview.docs:
                if doc.blocker:
                    results.extend(SlotResult(doc.doc_id, s.slot_id, False, doc.blocker) for s in doc.slots)
                    continue
                if doc.needs_freeze:
                    await self._freeze(project, doc, signer)
                    frozen_docs.append(doc.doc_id)
                results.extend(await self._sign_doc(project, doc, identity, inp.passphrase))
        signed = sum(1 for r in results if r.ok)
        await self._signer.audit.record(
            "signature.submission_sign",
            project_id=inp.project_id,
            details={
                "profile_id": inp.profile_id,
                "frozen_docs": frozen_docs,
                "signed": signed,
                "failed": len(results) - signed,
                "identity_id": str(identity.id) if identity is not None else None,
            },
        )
        logger.info("submission signed", project_id=str(inp.project_id), profile_id=inp.profile_id, signed=signed)
        return SignSubmissionOutput(preview=preview, frozen_docs=tuple(frozen_docs), results=tuple(results))

    def _check_confirmations(self, inp: SignSubmissionInput, preview: SignSubmissionPreview) -> None:
        if inp.expected is not None:
            changed = [d.doc_id for d in preview.docs if inp.expected.get(d.doc_id) != d.token]
            if changed:
                raise SigningConflictError(
                    localized_error(
                        f"Документы изменились после просмотра ({', '.join(changed)}): откройте комплект заново",
                        f"Documents changed after you reviewed them ({', '.join(changed)}): open the submission again",
                    ),
                    "changed",
                )
        if preview.resets and not inp.confirm_reset:
            names = ", ".join(sorted({r.signer or r.slot_id for r in preview.resets}))
            raise SigningConflictError(
                localized_error(
                    f"Фиксация PDF сбросит уже поставленные подписи ({names}): подтвердите сброс",
                    f"Freezing the PDF resets signatures already made ({names}): confirm the reset",
                ),
                "reset_required",
            )
        if preview.needs_passphrase and not inp.passphrase:
            raise KeyPassphraseRequiredError

    async def _key_signer(self, identity: SigningIdentity | None) -> SignerInfo | None:
        if identity is None:
            return None
        try:
            return await signer_for_identity(identity, self._signer.keyring, self._signer.identity_repo)
        except ValueError:
            return None

    async def _doc_preview(  # noqa: C901, PLR0912 — разбор слотов документа по таблице раздела 7
        self,
        project: Project,
        state: SignaturesState,
        doc: DocPlan,
        identity: SigningIdentity | None,
        signer: SignerInfo | None,
    ) -> DocPreview | None:
        mine = [s for s in doc.slots if s.is_mine and s.status is not SlotStatus.signed]
        if not mine:
            return None
        crypto_pending = any(s.state.method in CRYPTO_METHODS for s in mine)
        uses_frozen = doc.has_crypto
        needs_freeze = (crypto_pending or uses_frozen) and (doc.frozen is None or doc.frozen_outdated is not None)
        if not crypto_pending and all(s.state.reason in _MANUAL for s in mine):
            needs_freeze = False
        can_freeze = True
        if needs_freeze:
            try:
                await self._access.require(project.id, Action.FILES_WRITE, doc.doc_id)
            except (ProjectForbiddenError, NotFoundError):
                can_freeze = False
        actions = tuple(self._slot_action(state, s, identity, signer) for s in mine)
        resets = self._resets(state, doc) if needs_freeze else ()
        token = await self._token(project, state, doc, needs_freeze)
        blocker = ""
        if needs_freeze and not can_freeze:
            blocker = localized_error(
                "PDF нужно зафиксировать заново, а фиксировать может автор проекта: попросите его",
                "The PDF has to be frozen again, which only the project author can do: ask them",
            )
        return DocPreview(doc.doc_id, token, needs_freeze, can_freeze, resets, actions, blocker)

    @staticmethod
    def _slot_action(
        state: SignaturesState, slot: PlanSlot, identity: SigningIdentity | None, signer: SignerInfo | None
    ) -> SlotAction:
        method = slot.state.method
        base = SlotAction(slot.slot_id, slot.label, method, slot.status, "sign")
        if slot.state.reason in _MANUAL:
            return replace(base, action="none", blocker=reason_hint(slot.state.reason))
        if method is SignMethod.image:
            return replace(base, action="stamp")
        if identity is None:
            return replace(
                base,
                blocker=localized_error(
                    "Нет ключа подписи: добавьте ключ в профиле и выберите его по умолчанию",
                    "No signing key: add a key in your profile and make it the default",
                ),
            )
        if method is SignMethod.pades and identity.kind not in X509_KINDS:
            return replace(
                base,
                blocker=localized_error(
                    "Для встроенной подписи PAdES нужен ключ с сертификатом X.509, а выбран ключ OpenPGP",
                    "An embedded PAdES signature needs an X.509 key, an OpenPGP key is selected",
                ),
            )
        slot_state = state.slots.get(slot.slot_id)
        plate = slot_state.signer if slot_state is not None else None
        if plate is not None and plate.signer_id and signer is not None and plate.signer_id != signer.signer_id:
            return replace(
                base,
                blocker=localized_error(
                    f"На плашке указан другой подписант ({plate.owner}): выберите его ключ",
                    f"The plate names another signer ({plate.owner}): pick their key",
                ),
            )
        return base

    @staticmethod
    def _resets(state: SignaturesState, doc: DocPlan) -> tuple[ResetItem, ...]:
        """Подписи прежней фиксации, которые уйдут вместе с ней: открепленные и встроенные."""
        labels = {s.slot_id: s.label for s in doc.slots}
        items = [
            ResetItem(slot_id, labels.get(slot_id, {"ru": slot_id}), sig.signer, SignMethod.detached.value)
            for slot_id, sig in state.detached.get(doc.doc_id, {}).items()
        ]
        items += [
            ResetItem(slot_id, labels.get(slot_id, {"ru": slot_id}), sig.signer, SignMethod.pades.value)
            for slot_id, sig in state.embedded.get(doc.doc_id, {}).items()
        ]
        return tuple(items)

    async def _token(self, project: Project, state: SignaturesState, doc: DocPlan, needs_freeze: bool) -> str:
        """Отпечаток того, что видел человек: итоговый PDF, а до фиксации сборка и видимый слой."""
        if not needs_freeze and doc.frozen is not None:
            return f"pdf:{doc.frozen.signed_sha256 or doc.frozen.sha256}"
        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        instance = next((d for d in project.documents if d.id == doc.doc_id), None)
        if version is None or instance is None:
            return "missing"
        facts = await doc_facts(project, version, instance, state, self._template_service)
        return f"build:{facts.compiled_sha256 or ''}:{facts.marks_digest}"

    async def _freeze(self, project: Project, doc: DocPreview, signer: SignerInfo | None) -> None:
        """Плашки открепленных ЭП актора без подписанта берут данные из его ключа, затем фиксация."""
        state = self._signature_repo.get_state(project.folder)
        if signer is not None:
            slots = dict(state.slots)
            for action in doc.slots:
                slot = slots.get(action.slot_id)
                if slot is not None and slot.sign_mode is SignMode.detached_text and slot.signer is None:
                    slots[action.slot_id] = replace(slot, signer=signer)
            if slots != state.slots:
                self._signature_repo.save_state(project.folder, replace(state, slots=slots))
        await self._freeze_uc.execute(FreezePdfInput(project_id=project.id, doc_id=doc.doc_id))

    async def _sign_doc(  # noqa: C901 — по слоту: право, персона, подпись, итог
        self, project: Project, doc: DocPreview, identity: SigningIdentity | None, passphrase: str
    ) -> list[SlotResult]:
        results: list[SlotResult] = []
        signable = [s for s in doc.slots if s.action == "sign"]
        for action in doc.slots:
            if action.action != "sign" or action.blocker:
                ok = action.action == "stamp" and not action.blocker
                results.append(SlotResult(doc.doc_id, action.slot_id, ok, action.blocker))
        if not signable or identity is None:
            return results
        ctx = await load_doc_context(self._get_uc, self._template_repo, self._template_service, project.id, doc.doc_id)
        signer = await signer_for_identity(identity, self._signer.keyring, self._signer.identity_repo)
        for action in signable:
            if action.blocker:
                continue
            state = self._signature_repo.get_state(project.folder)
            frozen = state.frozen.get(doc.doc_id)
            try:
                if frozen is None:
                    raise ValueError(localized_error("PDF не зафиксирован", "The PDF is not frozen"))
                await self._access.require(project.id, Action.SIGN, action.slot_id)
                label = action.label.get(ctx.lang) or action.label.get("ru") or action.slot_id
                await self._signer.may_sign(project, state, action.slot_id, label, signer, explicit=False)
                new_state = await self._signer.sign_slot(ctx, state, frozen, action.slot_id, identity, passphrase)
            except ProjectForbiddenError:
                results.append(SlotResult(doc.doc_id, action.slot_id, False, str(SlotNotYoursError(action.slot_id))))
                continue
            except (ValueError, PermissionError, NotFoundError) as exc:
                results.append(SlotResult(doc.doc_id, action.slot_id, False, str(exc)))
                continue
            self._signature_repo.save_state(project.folder, new_state)
            results.append(SlotResult(doc.doc_id, action.slot_id, True))
        return results
