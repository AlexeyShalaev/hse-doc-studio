"""Подпись слотов участника маршрута ключом Студии: «Отправить и подписать», «Согласовать и подписать», «Подписать».

Ключ проверяется до любых записей файлов (`check`): нет ключа, ключи на сервере запрещены или нужен пароль. Затем
каждый слот подписывается над текущей фиксацией тем же путём, что «Подписать комплект»: право SIGN на слот,
персона актора и подписант плашки (`StudioSigner.may_sign`). Пароль живёт только в аргументах.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker
from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISignatureRepository, ITemplateRepository
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signing_route.entities import DocSlot
from hse_doc_studio.core.value_objects import SignerInfo
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.signatures._doc_context import load_doc_context
from hse_doc_studio.use_cases.signatures._studio_signer import (
    KeyPassphraseRequiredError,
    StudioSigner,
    signer_for_identity,
)
from hse_doc_studio.use_cases.signatures.default_key import DefaultSigningKey
from hse_doc_studio.use_cases.signing_route.point import RoutePoint


@dataclass(frozen=True)
class KeyRequest:
    """Ключ Студии для подписи: явно выбранный или ключ по умолчанию, пароль на время вызова."""

    identity_id: UUID | None = None
    passphrase: str = field(default="", repr=False)


@dataclass(frozen=True)
class KeyInfo:
    id: UUID
    label: str
    kind: str
    protected: bool
    signer: str


class NoSigningKeyError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            localized_error(
                "Нет ключа подписи: добавьте ключ в профиле и выберите его по умолчанию",
                "No signing key: add a key in your profile and make it the default",
            )
        )


class RouteKeySigner:
    def __init__(
        self,
        get_project: GetProjectUC,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        signature_repo: ISignatureRepository,
        signer: StudioSigner,
        default_key: DefaultSigningKey,
        access: IProjectAccessChecker,
    ) -> None:
        self._get_project = get_project
        self._templates = template_repo
        self._template_service = template_service
        self._signatures = signature_repo
        self._signer = signer
        self._default_key = default_key
        self._access = access

    async def default_key_info(self) -> KeyInfo | None:
        """Ключ, которым подпишет «Отправить и подписать» без выбора: ключ по умолчанию актора."""
        identity = (await self._default_key.get()).effective
        return await self._info(identity) if identity is not None else None

    async def keys_allowed(self) -> bool:
        """Разрешены ли на установке ключи Студии (закрытые ключи на сервере): иначе подписать ими нельзя."""
        return await self._signer.key_policy.server_key_storage_allowed()

    async def plate_of(self, identity: SigningIdentity) -> SignerInfo:
        """Данные плашки из открытой части своего ключа Студии."""
        return await signer_for_identity(identity, self._signer.keyring, self._signer.identity_repo)

    async def own_key(self, identity_id: UUID) -> SigningIdentity:
        """Свой ключ Студии по id для плашки; чужой ключ неотличим от несуществующего (`NotFoundError`)."""
        await self._signer.require_key_allowed()
        identity = await self._default_key.resolve(identity_id)
        if identity is None:
            raise NoSigningKeyError
        return identity

    async def check(self, request: KeyRequest) -> SigningIdentity:
        """Ключ готов подписывать: найден, ключи на сервере разрешены, пароль передан, если нужен."""
        identity = await self._default_key.resolve(request.identity_id)
        if identity is None:
            raise NoSigningKeyError
        await self._signer.require_key_allowed()
        if _protected(identity) and not request.passphrase:
            raise KeyPassphraseRequiredError
        return identity

    async def sign(
        self, point: RoutePoint, pairs: Sequence[DocSlot], identity: SigningIdentity, passphrase: str
    ) -> tuple[DocSlot, ...]:
        """Подписать пары над текущими фиксациями; возвращает подписанные. Первая ошибка прерывает подпись."""
        signer = await signer_for_identity(identity, self._signer.keyring, self._signer.identity_repo)
        signed: list[DocSlot] = []
        for pair in pairs:
            await self._sign_pair(point, pair, identity, signer, passphrase)
            signed.append(pair)
        return tuple(signed)

    async def _sign_pair(
        self, point: RoutePoint, pair: DocSlot, identity: SigningIdentity, signer: SignerInfo, passphrase: str
    ) -> None:
        project = point.project
        await self._access.require(project.id, Action.SIGN, pair.slot_id)
        ctx = await load_doc_context(
            self._get_project, self._templates, self._template_service, project.id, pair.doc_id
        )
        state = self._signatures.get_state(project.folder)
        frozen = state.frozen.get(pair.doc_id)
        if frozen is None:
            raise ValueError(localized_error("PDF не зафиксирован", "The PDF is not frozen"))
        label = point.slot_label(pair.slot_id)
        await self._signer.may_sign(
            project, state, pair.slot_id, label.get(ctx.lang) or pair.slot_id, signer, explicit=False
        )
        new_state = await self._signer.sign_slot(ctx, state, frozen, pair.slot_id, identity, passphrase)
        self._signatures.save_state(project.folder, new_state)

    async def _info(self, identity: SigningIdentity) -> KeyInfo:
        try:
            owner = (await signer_for_identity(identity, self._signer.keyring, self._signer.identity_repo)).owner
        except ValueError:
            owner = identity.subject_cn or identity.label
        return KeyInfo(
            id=identity.id,
            label=identity.label,
            kind=identity.kind.value,
            protected=_protected(identity),
            signer=owner,
        )


def _protected(identity: SigningIdentity) -> bool:
    return identity.protected and identity.kind is SigningIdentityKind.openpgp
