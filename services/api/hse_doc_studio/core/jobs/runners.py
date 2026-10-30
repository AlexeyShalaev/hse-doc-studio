"""Реестр раннеров: сущности, порты и токены.

Секреты (токен регистрации, токен раннера) в сущностях хранятся только хешем sha256: токены
случайные и длинные, медленный хеш не нужен. Сам секрет существует в ответе на создание и в
процессе раннера. Токен задачи (`job_token`) подписан HMAC и в БД не лежит.
"""

from __future__ import annotations

import base64
import builtins
import hashlib
import hmac
import json
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError
from hse_doc_studio.core.jobs.relay import AiEndpointFlavor
from hse_doc_studio.core.jobs.routing import RunnerScope

REGISTRATION_TOKEN_PREFIX = "hsrt_"  # noqa: S105 — префикс для сканеров секретов, не секрет
RUNNER_TOKEN_PREFIX = "hsrn_"  # noqa: S105
TOKEN_BYTES = 32
JOB_TOKEN_VERSION = "v1"  # noqa: S105
# Назначение производного ключа HKDF: смена ключа связки меняет и этот ключ, прежние остаются в проверке.
JOB_TOKEN_KEY_PURPOSE = "job-token"  # noqa: S105
BOOTSTRAP_TOKEN_ID = "bootstrap"  # noqa: S105


class RunnerOwnerKind(StrEnum):
    """Кому принадлежит раннер: установке (общий) или человеку (личный). Организации позже."""

    instance = "instance"
    user = "user"


class RunnerHostKind(StrEnum):
    """Где живёт раннер: консольный процесс или локальная Студия; нужно интерфейсу для подсказок."""

    cli = "cli"
    desktop = "desktop"


class RunnerPausedBy(StrEnum):
    """Кто поставил раннер на паузу: паузу админа хозяин личного раннера снять не может."""

    owner = "owner"
    admin = "admin"


class RegistrationTokenPurpose(StrEnum):
    # Создан человеком или админом.
    manual = "manual"
    # Выдан сопряжением по коду устройства.
    pairing = "pairing"


@dataclass(frozen=True)
class DeclaredAiEndpoint:
    """ИИ-адрес, объявленный раннером: только имя и вид, URL остаётся в конфигурации раннера."""

    name: str
    flavor: AiEndpointFlavor = AiEndpointFlavor.openai


def new_runner_secret(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(TOKEN_BYTES)


def hash_runner_secret(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RegistrationToken:
    """Разовый (или `max_uses`-кратный) токен, которым раннер получает свой постоянный токен."""

    id: str
    token_hash: str = field(repr=False)
    created_by: str | None
    created_at: datetime
    expires_at: datetime | None
    max_uses: int = 1
    uses: int = 0
    label: str = ""
    revoked_at: datetime | None = None
    owner_kind: RunnerOwnerKind = RunnerOwnerKind.instance
    owner_id: str | None = None
    purpose: RegistrationTokenPurpose = RegistrationTokenPurpose.manual

    def usable(self, now: datetime) -> bool:
        if self.revoked_at is not None or self.uses >= self.max_uses:
            return False
        return self.expires_at is None or self.expires_at > now


@dataclass(frozen=True)
class Runner:
    id: str
    name: str
    token_hash: str = field(repr=False)
    tags: frozenset[str]
    concurrency: int
    resource_class: str
    version: str
    created_at: datetime
    created_by: str | None = None
    last_seen_at: datetime | None = None
    paused: bool = False
    revoked_at: datetime | None = None
    owner_kind: RunnerOwnerKind = RunnerOwnerKind.instance
    owner_id: str | None = None
    host_kind: RunnerHostKind = RunnerHostKind.cli
    # Согласованные возможности протокола (пересечение объявленных раннером и известных серверу).
    features: frozenset[str] = frozenset()
    ai_endpoints: tuple[DeclaredAiEndpoint, ...] = ()
    # Слоты под ретрансляцию ИИ, отдельно от `concurrency`.
    ai_concurrency: int = 0
    last_seen_ip: str | None = None
    # Раннер сам сказал «ухожу»; следующий опрос это снимает.
    offline_at: datetime | None = None
    # Имя меняли в интерфейсе: `/announce` его больше не трогает.
    renamed_at: datetime | None = None
    # Кто поставил на паузу; без паузы пусто.
    paused_by: RunnerPausedBy | None = None

    @property
    def scope(self) -> RunnerScope:
        return RunnerScope.personal if self.owner_kind is RunnerOwnerKind.user else RunnerScope.shared

    def ai_endpoint(self, name: str) -> DeclaredAiEndpoint | None:
        return next((endpoint for endpoint in self.ai_endpoints if endpoint.name == name), None)


@dataclass(frozen=True)
class RunnerAnnouncement:
    """Что раннер сообщает о себе в `/announce`; `name=None` значит «имя не менять»."""

    name: str | None
    version: str
    tags: frozenset[str]
    concurrency: int
    ai_concurrency: int
    host_kind: RunnerHostKind
    features: frozenset[str]
    ai_endpoints: tuple[DeclaredAiEndpoint, ...]


class IRunnerRepository(Protocol):
    async def add(self, runner: Runner) -> None: ...
    async def get(self, runner_id: str) -> Runner | None: ...
    async def get_by_token_hash(self, token_hash: str) -> Runner | None: ...
    async def list(self) -> list[Runner]: ...
    async def set_token_hash(self, runner_id: str, token_hash: str) -> bool: ...
    async def set_paused(self, runner_id: str, paused: bool, by: RunnerPausedBy | None = None) -> bool:
        """Пауза запоминает, кто её поставил (`by`); снятие паузы стирает и это."""
        ...

    async def revoke(self, runner_id: str, now: datetime) -> bool:
        """Отзыв необратим: токен перестаёт работать, запись остаётся для журнала. False, если раннера нет."""
        ...

    async def touch(self, runner_id: str, now: datetime, version: str | None = None) -> None: ...
    async def list_owned(self, owner_id: str) -> builtins.list[Runner]:
        """Личные раннеры человека, включая отозванные."""
        ...

    async def count_active_owned(self, owner_id: str) -> int: ...
    async def rename(self, runner_id: str, name: str, now: datetime) -> bool:
        """Меняет имя и ставит renamed_at: имя из интерфейса `/announce` больше не перетирает."""
        ...

    async def apply_announcement(
        self, runner_id: str, info: RunnerAnnouncement, now: datetime, ip: str | None
    ) -> Runner | None: ...
    async def mark_offline(self, runner_id: str, now: datetime) -> None: ...


class IRegistrationTokenRepository(Protocol):
    async def add(self, token: RegistrationToken) -> None: ...
    async def get(self, token_id: str) -> RegistrationToken | None: ...
    async def list(self) -> list[RegistrationToken]: ...
    async def revoke(self, token_id: str, now: datetime) -> bool: ...
    async def consume(self, token_hash: str, now: datetime) -> RegistrationToken | None:
        """Атомарно списывает одно использование у годного токена; негодный (чужой, истёкший, исчерпанный) даёт None."""
        ...

    async def upsert_bootstrap(self, token: RegistrationToken) -> None:
        """Токен из окружения: тот же секрет оставляет счётчик, новый секрет заменяет запись и обнуляет его."""
        ...

    async def list_owned(self, owner_id: str) -> builtins.list[RegistrationToken]:
        """Личные токены человека, новые первыми."""
        ...

    async def revoke_owned(self, owner_id: str, now: datetime) -> int:
        """Отзывает все неотозванные личные токены человека; возвращает их число."""
        ...


class IUserRunnerRevoker(Protocol):
    async def revoke_all_of_user(self, user_id: str) -> int:
        """Отзывает личные раннеры и токены человека в текущей транзакции; возвращает число раннеров."""
        ...


@dataclass(frozen=True)
class JobTokenClaims:
    job_id: str
    runner_id: str
    expires_at: datetime
    attempt: int | None = None


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(key: bytes, signed: str) -> bytes:
    return hmac.new(key, signed.encode("ascii"), hashlib.sha256).digest()


class JobTokenSigner:
    """Подписывает и проверяет токен задачи: (job_id, runner_id, срок).

    Ключи это производные ключи связки, первичный первым: подписывает он, проверка перебирает все,
    так что смена ключа не рвёт идущие задачи.
    """

    def __init__(self, keys: Sequence[bytes]) -> None:
        if not keys:
            raise ValueError("нужен хотя бы один ключ")
        self._keys = tuple(keys)

    def sign(self, job_id: str, runner_id: str, expires_at: datetime, attempt: int | None = None) -> str:
        claims: dict[str, str | int] = {"j": job_id, "r": runner_id, "e": int(expires_at.timestamp())}
        if attempt is not None:
            claims["a"] = attempt
        payload = json.dumps(claims, separators=(",", ":"), sort_keys=True)
        signed = f"{JOB_TOKEN_VERSION}.{_b64(payload.encode('utf-8'))}"
        return f"{signed}.{_b64(_mac(self._keys[0], signed))}"

    def verify(
        self, token: str, now: datetime, *, job_id: str | None = None, runner_id: str | None = None
    ) -> JobTokenClaims:
        """Подлинные claims или `RunnerAuthError(job_token_invalid)`; причину наружу не раскрываем."""
        invalid = RunnerAuthError(RunnerErrorCode.job_token_invalid)
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != JOB_TOKEN_VERSION:  # noqa: PLR2004
            raise invalid
        signed = f"{parts[0]}.{parts[1]}"
        try:
            given = _unb64(parts[2])
            payload = json.loads(_unb64(parts[1]))
            claims = JobTokenClaims(
                job_id=str(payload["j"]),
                runner_id=str(payload["r"]),
                expires_at=datetime.fromtimestamp(int(payload["e"]), tz=now.tzinfo),
                attempt=int(payload["a"]) if "a" in payload else None,
            )
        except (ValueError, KeyError, TypeError, UnicodeError, OverflowError, OSError):
            raise invalid from None
        # Перебор без раннего выхода: время проверки не зависит от того, какой ключ подошёл.
        matched = False
        for key in self._keys:
            matched |= hmac.compare_digest(_mac(key, signed), given)
        if not matched or claims.expires_at <= now:
            raise invalid
        if (job_id is not None and claims.job_id != job_id) or (
            runner_id is not None and claims.runner_id != runner_id
        ):
            raise invalid
        return claims
