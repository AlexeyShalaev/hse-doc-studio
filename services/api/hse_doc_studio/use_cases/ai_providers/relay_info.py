"""Провайдер «через мой раннер»: откуда провайдер, готова ли ретрансляция, проверка раннера при сохранении."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderOwnerKind, AIProviderType
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.relay import ENDPOINT_NAME_RE, AiEndpointFlavor, RelayErrorCode
from hse_doc_studio.core.jobs.routing import IPersonalRunnerSettings
from hse_doc_studio.core.jobs.runners import IRunnerRepository, Runner, RunnerOwnerKind
from hse_doc_studio.use_cases.ai_relay.client import relay_state_of

AI_PROVIDER_RUNNER_INVALID = "ai_provider_runner_invalid"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AiProviderSource(StrEnum):
    """Откуда провайдер: свой, организации (позже), установки."""

    own = "own"
    org = "org"
    instance = "instance"


class RelayState(StrEnum):
    ready = "ready"
    runner_offline = "runner_offline"
    runner_paused = "runner_paused"
    runner_revoked = "runner_revoked"
    endpoint_missing = "endpoint_missing"
    disabled = "disabled"


@dataclass(frozen=True)
class AiProviderRelayInfo:
    runner_id: str
    runner_name: str | None
    endpoint: str
    flavor: AiEndpointFlavor
    state: RelayState


class AiProviderRunnerInvalidError(ValueError):
    """Провайдер через раннер указывает на чужой, отозванный раннер или на адрес, который раннер не объявил (422)."""

    code = AI_PROVIDER_RUNNER_INVALID


def source_of(provider: AIProvider) -> AiProviderSource:
    return AiProviderSource.instance if provider.owner_kind is AIProviderOwnerKind.instance else AiProviderSource.own


_STATE_OF_CODE = {
    RelayErrorCode.runner_offline: RelayState.runner_offline,
    RelayErrorCode.runner_paused: RelayState.runner_paused,
    RelayErrorCode.runner_revoked: RelayState.runner_revoked,
    RelayErrorCode.endpoint_missing: RelayState.endpoint_missing,
    RelayErrorCode.disabled: RelayState.disabled,
}


class ProviderRelayDescriber:
    """Состояние ретрансляции провайдеров вида `runner`; в локальном режиме раннеров нет и описывать нечего."""

    def __init__(
        self,
        runners: IRunnerRepository | None = None,
        settings: IPersonalRunnerSettings | None = None,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._runners = runners
        self._settings = settings
        self._clock = clock

    @property
    def available(self) -> bool:
        return self._runners is not None

    async def describe(self, providers: Sequence[AIProvider]) -> dict[UUID, AiProviderRelayInfo]:
        relayed = [p for p in providers if p.type is AIProviderType.runner and p.runner_id and p.runner_endpoint]
        if not relayed or self._runners is None:
            return {}
        enabled = (await self._settings.current()).enabled if self._settings is not None else True
        now = self._clock()
        described: dict[UUID, AiProviderRelayInfo] = {}
        for provider in relayed:
            assert provider.runner_id is not None  # noqa: S101 — отобрано выше
            assert provider.runner_endpoint is not None  # noqa: S101
            runner = _own(await self._runners.get(provider.runner_id))
            problem = relay_state_of(runner, provider.runner_endpoint, now=now, enabled=enabled)
            declared = runner.ai_endpoint(provider.runner_endpoint) if runner is not None else None
            described[provider.id] = AiProviderRelayInfo(
                runner_id=provider.runner_id,
                runner_name=runner.name if runner is not None else None,
                endpoint=provider.runner_endpoint,
                flavor=declared.flavor if declared is not None else AiEndpointFlavor.openai,
                state=RelayState.ready if problem is None else _STATE_OF_CODE.get(problem, RelayState.runner_offline),
            )
        return described

    async def validate(self, runner_id: str | None, endpoint: str | None) -> tuple[str, str]:
        """Раннер свой и не отозван, адрес им объявлен; иначе `AiProviderRunnerInvalidError`."""
        if self._runners is None:
            raise AiProviderRunnerInvalidError(
                localized_error(
                    "Провайдер через раннер доступен только на сервере",
                    "A runner provider is only available on a server",
                )
            )
        runner = _own(await self._runners.get(runner_id)) if runner_id else None
        if runner is None or runner.revoked_at is not None:
            raise AiProviderRunnerInvalidError(localized_error("Раннер не найден", "Runner not found"))
        if not endpoint or not ENDPOINT_NAME_RE.fullmatch(endpoint) or runner.ai_endpoint(endpoint) is None:
            raise AiProviderRunnerInvalidError(
                localized_error(
                    f"Раннер «{runner.name}» не объявил ИИ-адрес «{endpoint}»",
                    f'Runner "{runner.name}" has not declared the AI endpoint "{endpoint}"',
                )
            )
        return runner.id, endpoint


def _own(runner: Runner | None) -> Runner | None:
    """Чужой раннер неотличим от несуществующего: провайдер через раннер бывает только у его хозяина."""
    actor = current_actor()
    if runner is None or actor is None or actor.id is None:
        return None
    if runner.owner_kind is not RunnerOwnerKind.user or runner.owner_id != actor.id:
        return None
    return runner
