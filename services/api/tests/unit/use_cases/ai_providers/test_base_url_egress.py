"""Адрес ИИ-провайдера проходит политику исходящих запросов: личный строго, общий мягче, local не проверяет."""

from __future__ import annotations

import socket
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderOwnerKind, AIProviderType
from hse_doc_studio.infra.egress.policy import ResolvingEgressPolicy
from hse_doc_studio.use_cases.ai_providers.create_ai_provider import CreateAIProviderInput, CreateAIProviderUC
from hse_doc_studio.use_cases.ai_providers.list_provider_models import ListProviderModelsInput, ListProviderModelsUC
from hse_doc_studio.use_cases.ai_providers.update_ai_provider import UpdateAIProviderInput, UpdateAIProviderUC

pytestmark = pytest.mark.unit

_ZONE = {"llm.example.test": "93.184.216.34", "ollama.lan": "10.0.0.7", "rebind.example.test": "127.0.0.1"}


async def _resolve(host: str, port: int) -> list[str]:
    try:
        return [_ZONE[host]]
    except KeyError:
        raise socket.gaierror(socket.EAI_NONAME, "unknown") from None


class _Repo:
    def __init__(self, *items: AIProvider) -> None:
        self.items: dict[UUID, AIProvider] = {p.id: p for p in items}

    async def list_all(self) -> list[AIProvider]:
        return list(self.items.values())

    async def get(self, provider_id: UUID) -> AIProvider | None:
        return self.items.get(provider_id)

    async def create(self, provider: AIProvider) -> None:
        self.items[provider.id] = provider

    async def update(self, provider: AIProvider) -> None:
        self.items[provider.id] = provider

    async def delete(self, provider_id: UUID) -> bool:
        return self.items.pop(provider_id, None) is not None


class _Lister:
    async def list_models(self, provider: AIProvider) -> list[str]:
        return ["m1"]


def _egress() -> ResolvingEgressPolicy:
    return ResolvingEgressPolicy(resolver=_resolve)


def _provider(base_url: str = "https://llm.example.test/v1", **changes: object) -> AIProvider:
    return replace(
        AIProvider(
            id=uuid4(),
            name="P",
            type=AIProviderType.openai_compat,
            api_key="sk",
            base_url=base_url,
            models=[],
            created_at=datetime.now(timezone.utc),
        ),
        **changes,
    )


def _create(base_url: str, **changes: object) -> CreateAIProviderInput:
    return CreateAIProviderInput(
        name="P", type=AIProviderType.openai_compat, api_key="sk", base_url=base_url, **changes
    )  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1:5432/v1",
        "http://169.254.169.254/latest",
        "http://10.0.0.7:11434/v1",
        "http://[::1]/v1",
        "https://rebind.example.test/v1",
        "http://metadata.google.internal/",
        "file:///etc/passwd",
        "https:///nohost",
    ],
)
async def test__create__internal_or_malformed_url_of_a_user_provider__is_refused(base_url: str) -> None:
    repo = _Repo()

    with pytest.raises(ValueError, match="Адрес провайдера"):
        await CreateAIProviderUC(repo, _egress()).execute(_create(base_url))

    assert not repo.items


@pytest.mark.parametrize("base_url", ["", "https://llm.example.test/v1", "https://unresolvable.example.test/v1"])
async def test__create__public_empty_or_unresolvable_url__is_accepted(base_url: str) -> None:
    out = await CreateAIProviderUC(_Repo(), _egress()).execute(_create(base_url))

    assert out.provider.base_url == base_url


async def test__create__shared_provider__may_use_a_lan_host_but_never_metadata() -> None:
    uc = CreateAIProviderUC(_Repo(), _egress())

    out = await uc.execute(_create("http://ollama.lan:11434/v1", owner_kind=AIProviderOwnerKind.instance))
    with pytest.raises(ValueError, match="Адрес провайдера"):
        await uc.execute(_create("http://169.254.169.254/", owner_kind=AIProviderOwnerKind.instance))

    assert out.provider.owner_kind is AIProviderOwnerKind.instance


async def test__create__without_policy__local_mode_checks_nothing() -> None:
    out = await CreateAIProviderUC(_Repo()).execute(_create("http://127.0.0.1:11434/v1"))

    assert out.provider.base_url == "http://127.0.0.1:11434/v1"


async def test__update__changing_url_to_an_internal_one__is_refused_and_unchanged_url_is_not_rechecked() -> None:
    legacy = _provider("http://10.0.0.7:11434/v1")
    repo = _Repo(legacy)
    uc = UpdateAIProviderUC(repo, _egress())

    renamed = await uc.execute(UpdateAIProviderInput(provider_id=legacy.id, name="Новое"))
    with pytest.raises(ValueError, match="Адрес провайдера"):
        await uc.execute(UpdateAIProviderInput(provider_id=legacy.id, base_url="http://127.0.0.1/"))

    assert renamed.provider.name == "Новое"
    assert repo.items[legacy.id].base_url == "http://10.0.0.7:11434/v1"


async def test__update__keeps_the_owner_kind_of_the_provider() -> None:
    shared = _provider(owner_kind=AIProviderOwnerKind.instance)
    out = await UpdateAIProviderUC(_Repo(shared), _egress()).execute(
        UpdateAIProviderInput(provider_id=shared.id, base_url="http://ollama.lan/v1")
    )

    assert out.provider.owner_kind is AIProviderOwnerKind.instance


async def test__list_models__rechecks_the_stored_url_before_calling_out() -> None:
    bad = _provider("http://127.0.0.1:9999/v1")
    good = _provider()
    uc = ListProviderModelsUC(_Repo(bad, good), _Lister(), _egress())

    with pytest.raises(ValueError, match="Адрес провайдера"):
        await uc.execute(ListProviderModelsInput(provider_id=bad.id))
    out = await uc.execute(ListProviderModelsInput(provider_id=good.id))

    assert out.models == ["m1"]
