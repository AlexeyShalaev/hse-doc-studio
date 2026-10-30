"""Провайдер сервера, настройки хоста и проверка токена: настоящее хранилище настроек, сеть подменена."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    ServerCertificate,
    TokenIntrospection,
    TokenState,
)
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.host_settings import GitHostSettings
from hse_doc_studio.core.git_sync.protocols import DetectionRequest, IntrospectionRequest
from hse_doc_studio.core.git_sync.providers import ApiDetection, DetectedBy, GitProvider, Sufficiency
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.infra.git_sync.host_settings_repository import JsonGitHostSettingsRepository
from hse_doc_studio.use_cases.git_sync.host_settings import (
    CheckCredentialUC,
    ListHostSettingsUC,
    UpdateHostSettingsInput,
    UpdateHostSettingsUC,
)
from hse_doc_studio.use_cases.git_sync.provider_resolver import ProviderResolver
from hse_doc_studio.use_cases.git_sync.token_check import TokenChecker

_NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)
_PIN = "SHA256:b1Kq0vU7m4Zl9Xc2Tn8RjHf3eWyAo5DsPi6GgLxEu0w"
_OTHER_PIN = "SHA256:Zr3Vn8Hq1Lw6Ys0Ud4Cx9TkPb2Ea7MgFj5RiOtNo1Ae"
_GITLAB_API = "https://gitlab.hse.local/api/v4"


class _Detector:
    def __init__(self, result: ApiDetection | None = None) -> None:
        self.result = result
        self.requests: list[DetectionRequest] = []

    async def detect(self, request: DetectionRequest) -> ApiDetection | None:
        self.requests.append(request)
        return self.result


class _Introspector:
    def __init__(self, result: TokenIntrospection | Exception) -> None:
        self.result = result
        self.requests: list[IntrospectionRequest] = []

    async def introspect(self, request: IntrospectionRequest) -> TokenIntrospection:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Certificates:
    def __init__(self, fingerprint: str = _PIN) -> None:
        self.fingerprint = fingerprint
        self.fetched: list[tuple[str, int | None]] = []

    async def fetch(self, host: str, port: int | None) -> ServerCertificate:
        self.fetched.append((host, port))
        return ServerCertificate(self.fingerprint, "CN=x", "CN=ca", _NOW, _NOW, False, "SERVER-PEM\n")

    def normalize_ca_pem(self, pem: str) -> str:
        if "BEGIN CERTIFICATE" not in pem:
            raise GitSyncError(GitErrorCode.host_settings_invalid, "bad")
        return pem.strip() + "\n"


@dataclass
class _Credentials:
    items: dict[UUID, GitCredential] = field(default_factory=dict)
    marks: list[tuple[UUID, CredentialStatus]] = field(default_factory=list)

    def add(self, credential: GitCredential) -> GitCredential:
        self.items[credential.id] = credential
        return credential

    async def list(self) -> list[GitCredential]:
        return list(self.items.values())

    async def get(self, credential_id: UUID) -> GitCredential | None:
        return self.items.get(credential_id)

    async def update(self, credential: GitCredential, secret: Secret | None = None) -> None:
        self.items[credential.id] = credential

    async def get_secret(self, credential_id: UUID) -> Secret:
        if credential_id not in self.items:
            raise NotFoundError("credential")
        return Secret("glpat-CANARYtoken1234567890")

    async def mark(self, credential_id: UUID, status: CredentialStatus, *, used_at: datetime | None = None) -> None:
        self.marks.append((credential_id, status))
        self.items[credential_id] = replace(self.items[credential_id], status=status)


class _Usage:
    async def by_credential(self) -> dict[UUID, list[object]]:
        return {}


def _credential(host: str = "gitlab.hse.local", kind: GitCredentialKind = GitCredentialKind.pat) -> GitCredential:
    return GitCredential(
        id=uuid4(),
        kind=kind,
        label="t",
        host=host,
        username=None,
        status=CredentialStatus.unverified,
        created_at=_NOW,
    )


@pytest.fixture
def settings(tmp_path: Path) -> JsonGitHostSettingsRepository:
    return JsonGitHostSettingsRepository(tmp_path)


def _resolver(settings: JsonGitHostSettingsRepository, detector: _Detector | None = None) -> ProviderResolver:
    return ProviderResolver(settings, detector or _Detector())


def _url(raw: str):  # type: ignore[no-untyped-def]
    return parse_remote_url(raw, allow_http=True, allow_local=True)


# --- ProviderResolver ----------------------------------------------------------------------------------------


async def test__resolve__saas_host__is_known_without_asking_the_network(
    settings: JsonGitHostSettingsRepository,
) -> None:
    detector = _Detector()

    resolved = await _resolver(settings, detector).resolve(_url("https://github.com/hse/paper.git"))

    assert (resolved.info.id, resolved.info.detected_by) == (GitProvider.github, DetectedBy.host)
    assert resolved.api_base == "https://api.github.com"
    assert detector.requests == []


async def test__resolve__unknown_host_answering_like_gitlab__is_detected_by_api_and_remembered(
    settings: JsonGitHostSettingsRepository,
) -> None:
    found = ApiDetection(GitProvider.gitlab, "17.3.1", "https://git.hse.ru/gitlab/api/v4")
    detector = _Detector(found)
    resolver = _resolver(settings, detector)

    resolved = await resolver.resolve(_url("https://git.hse.ru/gitlab/team/paper.git"))

    assert (resolved.info.id, resolved.info.detected_by, resolved.info.version) == (
        GitProvider.gitlab,
        DetectedBy.api,
        "17.3.1",
    )
    assert resolved.api_base == "https://git.hse.ru/gitlab/api/v4"
    request = detector.requests[0]
    assert (request.host, request.segments, request.secure) == ("git.hse.ru", ("gitlab", "team", "paper.git"), True)
    assert request.providers == (GitProvider.gitlab, GitProvider.gitea, GitProvider.github)
    assert await settings.get("git.hse.ru", None) == GitHostSettings("git.hse.ru", None, detected=found)
    assert (await resolver.known("git.hse.ru", None)).version == "17.3.1"


async def test__resolve__http_api_base_stored_earlier__is_not_reused_for_an_https_address(
    settings: JsonGitHostSettingsRepository,
) -> None:
    # Хост и порт без схемы: проба по http (при разрешённом http) сохранила бы http-корень для https-адреса тоже.
    await settings.save(
        GitHostSettings(
            "git.hse.ru", None, detected=ApiDetection(GitProvider.gitlab, "17.3.1", "http://git.hse.ru/api/v4")
        )
    )

    resolved = await _resolver(settings).resolve(_url("https://git.hse.ru/team/paper.git"))

    assert resolved.info.id is GitProvider.gitlab
    assert resolved.api_base == "https://git.hse.ru/api/v4"


async def test__resolve__http_api_base_stored_earlier__is_kept_for_the_same_http_address(
    settings: JsonGitHostSettingsRepository,
) -> None:
    await settings.save(
        GitHostSettings(
            "git.hse.ru", None, detected=ApiDetection(GitProvider.gitlab, "17.3.1", "http://git.hse.ru/api/v4")
        )
    )

    resolved = await _resolver(settings).resolve(_url("http://git.hse.ru/team/paper.git"))

    assert resolved.api_base == "http://git.hse.ru/api/v4"


async def test__resolve__host_heuristic_hit__asks_only_that_provider_for_the_version(
    settings: JsonGitHostSettingsRepository,
) -> None:
    detector = _Detector(ApiDetection(GitProvider.gitlab, "16.11.0", "https://gitlab.hse.local/api/v4"))

    resolved = await _resolver(settings, detector).resolve(_url("https://gitlab.hse.local/team/paper.git"))

    assert detector.requests[0].providers == (GitProvider.gitlab,)
    assert (resolved.info.detected_by, resolved.info.version) == (DetectedBy.host, "16.11.0")


async def test__resolve__user_override__wins_over_the_host_name_and_is_the_only_one_asked(
    settings: JsonGitHostSettingsRepository,
) -> None:
    await settings.save(GitHostSettings("gitlab.hse.local", None, provider_override=GitProvider.gitea))
    detector = _Detector()

    resolved = await _resolver(settings, detector).resolve(_url("https://gitlab.hse.local/team/paper.git"))

    assert (resolved.info.id, resolved.info.detected_by) == (GitProvider.gitea, DetectedBy.override)
    assert detector.requests[0].providers == (GitProvider.gitea,)
    assert resolved.api_base == "https://gitlab.hse.local/api/v1"


async def test__resolve__nothing_answers__is_other_and_unknown(settings: JsonGitHostSettingsRepository) -> None:
    resolved = await _resolver(settings).resolve(_url("https://git.corp.example/team/paper.git"))

    assert (resolved.info.id, resolved.info.detected_by) == (GitProvider.other, DetectedBy.unknown)
    assert resolved.api_base is None
    assert await settings.list() == []


@pytest.mark.parametrize("raw", ["ssh://git@git.hse.ru/team/paper.git", "git@git.hse.ru:team/paper.git"])
async def test__resolve__ssh_address__is_not_probed_over_http(
    settings: JsonGitHostSettingsRepository, raw: str
) -> None:
    detector = _Detector()

    await _resolver(settings, detector).resolve(_url(raw))

    assert detector.requests == []


async def test__resolve__server_with_own_trust__hands_the_trust_file_to_the_detector(
    settings: JsonGitHostSettingsRepository,
) -> None:
    await settings.save(GitHostSettings("git.hse.ru", None, ca_pem="CA\n"))
    detector = _Detector()

    resolved = await _resolver(settings, detector).resolve(_url("https://git.hse.ru/team/paper.git"))

    assert resolved.ca_file is not None
    assert detector.requests[0].ca_file == resolved.ca_file


async def test__known__remembered_detection_is_used_without_network(settings: JsonGitHostSettingsRepository) -> None:
    await settings.save(GitHostSettings("git.hse.ru", None, detected=ApiDetection(GitProvider.gitea, "1.22.3")))

    info = await _resolver(settings).known("git.hse.ru", None)

    assert (info.id, info.detected_by, info.version) == (GitProvider.gitea, DetectedBy.api, "1.22.3")


async def test__known__override_to_another_provider__drops_the_version_of_the_detected_one(
    settings: JsonGitHostSettingsRepository,
) -> None:
    await settings.save(
        GitHostSettings(
            "git.hse.ru",
            None,
            provider_override=GitProvider.github,
            detected=ApiDetection(GitProvider.gitea, "1.22.3"),
        )
    )

    info = await _resolver(settings).known("git.hse.ru", None)

    assert (info.id, info.detected_by, info.version) == (GitProvider.github, DetectedBy.override, None)


# --- настройки хоста -------------------------------------------------------------------------------------------


def _update(settings: JsonGitHostSettingsRepository, certificates: _Certificates | None = None) -> UpdateHostSettingsUC:
    return UpdateHostSettingsUC(settings, certificates or _Certificates(), _resolver(settings))  # type: ignore[arg-type]


async def test__update__override__is_saved_and_changes_the_reported_provider(
    settings: JsonGitHostSettingsRepository,
) -> None:
    view = await _update(settings).execute(
        UpdateHostSettingsInput("Git.HSE.ru", None, provider_override="gitlab", given=frozenset({"provider_override"}))
    )

    assert view.settings.host == "git.hse.ru"
    assert (view.provider.id, view.provider.detected_by) == (GitProvider.gitlab, DetectedBy.override)
    assert await settings.get("git.hse.ru", None) is not None


async def test__update__unknown_provider__is_provider_unknown(settings: JsonGitHostSettingsRepository) -> None:
    with pytest.raises(GitSyncError) as error:
        await _update(settings).execute(
            UpdateHostSettingsInput("git.hse.ru", None, provider_override="svn", given=frozenset({"provider_override"}))
        )

    assert error.value.code is GitErrorCode.provider_unknown


async def test__update__absent_field_keeps_the_value_and_null_resets_it(
    settings: JsonGitHostSettingsRepository,
) -> None:
    uc = _update(settings)
    await uc.execute(
        UpdateHostSettingsInput(
            "git.hse.ru",
            None,
            provider_override="gitlab",
            ca_pem="-----BEGIN CERTIFICATE-----",
            given=frozenset({"provider_override", "ca_pem"}),
        )
    )

    await uc.execute(UpdateHostSettingsInput("git.hse.ru", None, given=frozenset()))
    kept = await settings.get("git.hse.ru", None)
    await uc.execute(UpdateHostSettingsInput("git.hse.ru", None, given=frozenset({"provider_override"})))
    reset = await settings.get("git.hse.ru", None)

    assert kept is not None
    assert (kept.provider_override, kept.ca_pem is not None) == (GitProvider.gitlab, True)
    assert reset is not None
    assert (reset.provider_override, reset.ca_pem is not None) == (None, True)


async def test__update__all_fields_reset__removes_the_record(settings: JsonGitHostSettingsRepository) -> None:
    uc = _update(settings)
    await uc.execute(
        UpdateHostSettingsInput("git.hse.ru", None, provider_override="gitlab", given=frozenset({"provider_override"}))
    )

    await uc.execute(UpdateHostSettingsInput("git.hse.ru", None, given=frozenset({"provider_override"})))

    assert await settings.list() == []


async def test__update__ca_pem__is_normalized_and_marks_ca_present(settings: JsonGitHostSettingsRepository) -> None:
    await _update(settings).execute(
        UpdateHostSettingsInput(
            "git.hse.ru", 8443, ca_pem="  -----BEGIN CERTIFICATE-----  ", given=frozenset({"ca_pem"})
        )
    )

    saved = await settings.get("git.hse.ru", 8443)
    assert saved is not None
    assert saved.ca_pem == "-----BEGIN CERTIFICATE-----\n"


async def test__update__invalid_ca_pem__is_rejected_and_nothing_is_saved(
    settings: JsonGitHostSettingsRepository,
) -> None:
    with pytest.raises(GitSyncError) as error:
        await _update(settings).execute(
            UpdateHostSettingsInput("git.hse.ru", None, ca_pem="hello", given=frozenset({"ca_pem"}))
        )

    assert error.value.code is GitErrorCode.host_settings_invalid
    assert await settings.list() == []


async def test__update__pin_with_the_fingerprint_the_server_presents__stores_fingerprint_and_certificate(
    settings: JsonGitHostSettingsRepository,
) -> None:
    certificates = _Certificates(_PIN)

    await _update(settings, certificates).execute(
        UpdateHostSettingsInput(
            "git.hse.ru", 8443, pinned_fingerprint=f" {_PIN} ", given=frozenset({"pinned_fingerprint"})
        )
    )

    saved = await settings.get("git.hse.ru", 8443)
    assert saved is not None
    assert (saved.pinned_fingerprint, saved.pinned_pem) == (_PIN, "SERVER-PEM\n")
    assert certificates.fetched == [("git.hse.ru", 8443)]


async def test__update__pin_when_the_server_presents_another_certificate__is_a_mismatch_and_saves_nothing(
    settings: JsonGitHostSettingsRepository,
) -> None:
    with pytest.raises(GitSyncError) as error:
        await _update(settings, _Certificates(_OTHER_PIN)).execute(
            UpdateHostSettingsInput(
                "git.hse.ru", None, pinned_fingerprint=_PIN, given=frozenset({"pinned_fingerprint"})
            )
        )

    assert error.value.code is GitErrorCode.tls_pin_mismatch
    assert (error.value.ctx["expected"], error.value.ctx["actual"]) == (_PIN, _OTHER_PIN)
    assert await settings.list() == []


async def test__update__malformed_fingerprint__is_invalid_without_touching_the_network(
    settings: JsonGitHostSettingsRepository,
) -> None:
    certificates = _Certificates()

    with pytest.raises(GitSyncError) as error:
        await _update(settings, certificates).execute(
            UpdateHostSettingsInput(
                "git.hse.ru", None, pinned_fingerprint="SHA256:short", given=frozenset({"pinned_fingerprint"})
            )
        )

    assert error.value.code is GitErrorCode.host_settings_invalid
    assert certificates.fetched == []


async def test__update__unpin__removes_fingerprint_and_certificate(settings: JsonGitHostSettingsRepository) -> None:
    uc = _update(settings)
    await uc.execute(
        UpdateHostSettingsInput("git.hse.ru", None, pinned_fingerprint=_PIN, given=frozenset({"pinned_fingerprint"}))
    )

    await uc.execute(UpdateHostSettingsInput("git.hse.ru", None, given=frozenset({"pinned_fingerprint"})))

    assert await settings.list() == []


async def test__update__bad_host_or_port__is_credential_invalid(settings: JsonGitHostSettingsRepository) -> None:
    with pytest.raises(GitSyncError):
        await _update(settings).execute(UpdateHostSettingsInput("bad host!", None))
    with pytest.raises(GitSyncError):
        await _update(settings).execute(UpdateHostSettingsInput("git.hse.ru", 70000))


async def test__list__merges_saved_settings_with_hosts_of_credentials(settings: JsonGitHostSettingsRepository) -> None:
    await settings.save(GitHostSettings("git.corp.example", 8443, provider_override=GitProvider.gitlab))
    credentials = _Credentials()
    credentials.add(_credential("github.com"))
    credentials.add(_credential("git.corp.example"))

    views = await ListHostSettingsUC(settings, credentials, _resolver(settings)).execute()  # type: ignore[arg-type]

    assert sorted((view.settings.host, view.settings.port or 0, view.provider.id.value) for view in views) == [
        ("git.corp.example", 0, "other"),
        ("git.corp.example", 8443, "gitlab"),
        ("github.com", 0, "github"),
    ]


# --- проверка токена ---------------------------------------------------------------------------------------------


def _checker(result: TokenIntrospection | Exception, credentials: _Credentials) -> tuple[TokenChecker, _Introspector]:
    introspector = _Introspector(result)
    return TokenChecker(introspector, credentials), introspector  # type: ignore[arg-type]


def _check_uc(
    settings: JsonGitHostSettingsRepository, credentials: _Credentials, checker: TokenChecker
) -> CheckCredentialUC:
    return CheckCredentialUC(credentials, settings, _resolver(settings), checker, _Usage())  # type: ignore[arg-type]


async def test__check_credential__valid_gitlab_token__returns_assessment_and_remembers_the_expiry(
    settings: JsonGitHostSettingsRepository,
) -> None:
    credentials = _Credentials()
    credential = credentials.add(_credential())
    expiry = _NOW + timedelta(days=90)
    checker, introspector = _checker(
        TokenIntrospection(
            TokenState.valid, login="anna", scopes=("read_repository", "write_repository"), expires_at=expiry
        ),
        credentials,
    )

    view = await _check_uc(settings, credentials, checker).execute(credential.id)

    assert view.token is not None
    assert view.token.info is not None
    assert (view.token.info.login, view.token.info.sufficiency) == ("anna", Sufficiency.sufficient)
    assert view.credential.credential.expires_at == expiry
    assert (await credentials.get(credential.id)).expires_at == expiry  # type: ignore[union-attr]
    assert introspector.requests[0].api_base == _GITLAB_API
    assert introspector.requests[0].provider is GitProvider.gitlab


async def test__check_credential__too_narrow_token__names_what_is_missing(
    settings: JsonGitHostSettingsRepository,
) -> None:
    credentials = _Credentials()
    credential = credentials.add(_credential())
    checker, _ = _checker(TokenIntrospection(TokenState.valid, login="anna", scopes=("read_repository",)), credentials)

    view = await _check_uc(settings, credentials, checker).execute(credential.id)

    assert view.token is not None
    assert view.token.info is not None
    assert (view.token.info.sufficiency, view.token.info.missing) == (Sufficiency.too_narrow, ("write_repository",))


async def test__check_credential__server_does_not_tell_scopes__is_unknown_not_an_error(
    settings: JsonGitHostSettingsRepository,
) -> None:
    credentials = _Credentials()
    credential = credentials.add(_credential("github.com"))
    checker, _ = _checker(TokenIntrospection(TokenState.valid, login="anna-petrova"), credentials)

    view = await _check_uc(settings, credentials, checker).execute(credential.id)

    assert view.token is not None
    assert view.token.info is not None
    assert (view.token.info.sufficiency, view.token.info.scopes) == (Sufficiency.unknown, ())
    assert view.provider.id is GitProvider.github


async def test__check_credential__expired__raises_token_expired_and_marks_the_credential(
    settings: JsonGitHostSettingsRepository,
) -> None:
    credentials = _Credentials()
    credential = credentials.add(_credential())
    expiry = _NOW - timedelta(days=2)
    checker, _ = _checker(TokenIntrospection(TokenState.expired, expires_at=expiry), credentials)

    with pytest.raises(GitSyncError) as error:
        await _check_uc(settings, credentials, checker).execute(credential.id)

    assert error.value.code is GitErrorCode.token_expired
    assert (await credentials.get(credential.id)).expires_at == expiry  # type: ignore[union-attr]
    assert credentials.marks == [(credential.id, CredentialStatus.auth_failed)]
    assert (await credentials.get(credential.id)).status is CredentialStatus.auth_failed  # type: ignore[union-attr]


async def test__check_credential__valid_token_after_a_failure__clears_auth_failed(
    settings: JsonGitHostSettingsRepository,
) -> None:
    credentials = _Credentials()
    credential = credentials.add(replace(_credential(), status=CredentialStatus.auth_failed))
    checker, _ = _checker(TokenIntrospection(TokenState.valid, login="anna"), credentials)

    view = await _check_uc(settings, credentials, checker).execute(credential.id)

    assert view.credential.credential.status is CredentialStatus.ok
    assert credentials.marks == [(credential.id, CredentialStatus.ok)]


@pytest.mark.parametrize("status", [CredentialStatus.unverified, CredentialStatus.ok, CredentialStatus.unreadable])
async def test__check_credential__valid_token_without_a_failure__status_is_left_alone(
    settings: JsonGitHostSettingsRepository, status: CredentialStatus
) -> None:
    credentials = _Credentials()
    credential = credentials.add(replace(_credential(), status=status))
    checker, _ = _checker(TokenIntrospection(TokenState.valid, login="anna"), credentials)

    await _check_uc(settings, credentials, checker).execute(credential.id)

    assert credentials.marks == []


async def test__check_credential__rejected__raises_auth_failed(settings: JsonGitHostSettingsRepository) -> None:
    credentials = _Credentials()
    credential = credentials.add(_credential())
    checker, _ = _checker(TokenIntrospection(TokenState.rejected), credentials)

    with pytest.raises(GitSyncError) as error:
        await _check_uc(settings, credentials, checker).execute(credential.id)

    assert error.value.code is GitErrorCode.auth_failed


async def test__check_credential__network_error__propagates_with_its_code(
    settings: JsonGitHostSettingsRepository,
) -> None:
    credentials = _Credentials()
    credential = credentials.add(_credential())
    checker, _ = _checker(GitSyncError(GitErrorCode.offline), credentials)

    with pytest.raises(GitSyncError) as error:
        await _check_uc(settings, credentials, checker).execute(credential.id)

    assert error.value.code is GitErrorCode.offline


async def test__check_credential__provider_without_introspection__returns_no_token_info_and_asks_nobody(
    settings: JsonGitHostSettingsRepository,
) -> None:
    credentials = _Credentials()
    credential = credentials.add(_credential("bitbucket.org"))
    checker, introspector = _checker(TokenIntrospection(TokenState.valid), credentials)

    view = await _check_uc(settings, credentials, checker).execute(credential.id)

    assert view.token is None
    assert view.provider.id is GitProvider.bitbucket
    assert introspector.requests == []


async def test__check_credential__uses_the_detected_api_base_and_trust_of_the_known_server(
    settings: JsonGitHostSettingsRepository,
) -> None:
    await settings.save(
        GitHostSettings(
            "git.hse.ru",
            8443,
            ca_pem="CA\n",
            detected=ApiDetection(GitProvider.gitlab, "17.3.1", "https://git.hse.ru:8443/gitlab/api/v4"),
        )
    )
    credentials = _Credentials()
    credential = credentials.add(_credential("git.hse.ru"))
    checker, introspector = _checker(TokenIntrospection(TokenState.valid, scopes=("api",)), credentials)

    view = await _check_uc(settings, credentials, checker).execute(credential.id)

    request = introspector.requests[0]
    assert request.api_base == "https://git.hse.ru:8443/gitlab/api/v4"
    assert request.ca_file is not None
    assert view.token is not None
    assert view.token.info is not None
    assert view.token.info.sufficiency is Sufficiency.too_broad


async def test__check_credential__http_api_base_stored_earlier__token_goes_to_https(
    settings: JsonGitHostSettingsRepository,
) -> None:
    await settings.save(
        GitHostSettings(
            "git.hse.ru", None, detected=ApiDetection(GitProvider.gitlab, "17.3.1", "http://git.hse.ru/api/v4")
        )
    )
    credentials = _Credentials()
    credential = credentials.add(_credential("git.hse.ru"))
    checker, introspector = _checker(TokenIntrospection(TokenState.valid, scopes=("api",)), credentials)

    await _check_uc(settings, credentials, checker).execute(credential.id)

    assert introspector.requests[0].api_base == "https://git.hse.ru/api/v4"


async def test__check_credential__unknown_credential__is_not_found(settings: JsonGitHostSettingsRepository) -> None:
    credentials = _Credentials()
    checker, _ = _checker(TokenIntrospection(TokenState.valid), credentials)

    with pytest.raises(NotFoundError):
        await _check_uc(settings, credentials, checker).execute(uuid4())


async def test__check_credential__ssh_key__is_rejected(settings: JsonGitHostSettingsRepository) -> None:
    credentials = _Credentials()
    credential = credentials.add(_credential(kind=GitCredentialKind.ssh_key))
    checker, _ = _checker(TokenIntrospection(TokenState.valid), credentials)

    with pytest.raises(GitSyncError) as error:
        await _check_uc(settings, credentials, checker).execute(credential.id)

    assert error.value.code is GitErrorCode.credential_invalid
