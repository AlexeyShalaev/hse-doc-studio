"""Профиль подписанта на сервере: картинка подписи и открытая часть ключа у аккаунта (signing-route.md, R10)."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.core.signatures.ports import ISignatureAudit, ISignerPlateData
from hse_doc_studio.core.signatures.signer_profile import IPublicKeyReader, ISignerProfileRepository
from hse_doc_studio.infra.db.repositories.signer_profiles import PostgresSignerProfileRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.infra.signatures.public_key_reader import PublicKeyReader
from hse_doc_studio.use_cases.signer_profile.plate_data import ProfileSignerPlateData
from hse_doc_studio.use_cases.signer_profile.profile import (
    ClearProfileImageUC,
    ClearProfilePublicKeyUC,
    GetSignerProfileUC,
    ReadProfileImageUC,
    SaveProfileImageUC,
    SaveProfilePublicKeyUC,
)


class ServerSignerProfileProvider(Provider):
    scope = Scope.APP

    @provide
    def get_signer_profile_repository(self, sessions: SessionProvider) -> ISignerProfileRepository:
        return PostgresSignerProfileRepository(sessions)

    @provide
    def get_public_key_reader(self, keyring: GpgKeyring) -> IPublicKeyReader:
        return PublicKeyReader(keyring)

    @provide
    def get_signer_plate_data(self, repo: ISignerProfileRepository) -> ISignerPlateData:
        # Перекрывает локальный источник: плашку участника маршрута знает ещё и его профиль (signing-route.md, 6.5).
        return ProfileSignerPlateData(repo)

    @provide(scope=Scope.REQUEST)
    def get_signer_profile(self, repo: ISignerProfileRepository) -> GetSignerProfileUC:
        return GetSignerProfileUC(repo)

    @provide(scope=Scope.REQUEST)
    def read_profile_image(self, repo: ISignerProfileRepository) -> ReadProfileImageUC:
        return ReadProfileImageUC(repo)

    @provide(scope=Scope.REQUEST)
    def save_profile_image(self, repo: ISignerProfileRepository, audit: ISignatureAudit) -> SaveProfileImageUC:
        return SaveProfileImageUC(repo, audit)

    @provide(scope=Scope.REQUEST)
    def clear_profile_image(self, repo: ISignerProfileRepository, audit: ISignatureAudit) -> ClearProfileImageUC:
        return ClearProfileImageUC(repo, audit)

    @provide(scope=Scope.REQUEST)
    def save_profile_public_key(
        self, repo: ISignerProfileRepository, reader: IPublicKeyReader, audit: ISignatureAudit
    ) -> SaveProfilePublicKeyUC:
        return SaveProfilePublicKeyUC(repo, reader, audit)

    @provide(scope=Scope.REQUEST)
    def clear_profile_public_key(
        self, repo: ISignerProfileRepository, audit: ISignatureAudit
    ) -> ClearProfilePublicKeyUC:
        return ClearProfilePublicKeyUC(repo, audit)
