from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.ai_providers.create_ai_provider import (
    CreateAIProviderInput,
    CreateAIProviderUC,
)
from hse_doc_studio.use_cases.ai_providers.list_provider_models import (
    ListProviderModelsInput,
    ListProviderModelsUC,
)
from hse_doc_studio.use_cases.ai_providers.update_ai_provider import (
    UpdateAIProviderInput,
    UpdateAIProviderUC,
)


class _FakeRepo:
    def __init__(self) -> None:
        self._items: dict[UUID, AIProvider] = {}

    def list_all(self) -> list[AIProvider]:
        return list(self._items.values())

    def get(self, provider_id: UUID) -> AIProvider | None:
        return self._items.get(provider_id)

    def create(self, provider: AIProvider) -> None:
        self._items[provider.id] = provider

    def update(self, provider: AIProvider) -> None:
        self._items[provider.id] = provider

    def delete(self, provider_id: UUID) -> bool:
        return self._items.pop(provider_id, None) is not None


class _FakeLister:
    def __init__(self, models: list[str]) -> None:
        self._models = models

    async def list_models(self, provider: AIProvider) -> list[str]:
        return self._models


@pytest.mark.unit
async def test__create_ai_provider__persists_with_generated_id() -> None:
    repo = _FakeRepo()
    uc = CreateAIProviderUC(ai_provider_repo=repo)

    out = await uc.execute(
        CreateAIProviderInput(name="OpenAI", type=AIProviderType.openai, api_key="sk-x", base_url="", models=[])
    )

    assert out.provider.id in {p.id for p in repo.list_all()}
    assert out.provider.api_key == "sk-x"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "api_key", "match"),
    [
        ("  ", "sk-x", "название"),
        ("OpenAI", "", "API-ключ"),
    ],
)
async def test__create_ai_provider__blank_name_or_api_key__raises(name: str, api_key: str, match: str) -> None:
    uc = CreateAIProviderUC(ai_provider_repo=_FakeRepo())

    with pytest.raises(ValueError, match=match):
        await uc.execute(CreateAIProviderInput(name=name, type=AIProviderType.openai, api_key=api_key))


@pytest.mark.unit
async def test__update_ai_provider__blank_api_key__keeps_existing() -> None:
    repo = _FakeRepo()
    created = await CreateAIProviderUC(ai_provider_repo=repo).execute(
        CreateAIProviderInput(name="OpenAI", type=AIProviderType.openai, api_key="sk-original")
    )
    uc = UpdateAIProviderUC(ai_provider_repo=repo)

    out = await uc.execute(UpdateAIProviderInput(provider_id=created.provider.id, name="Renamed", api_key=""))

    assert out.provider.name == "Renamed"
    assert out.provider.api_key == "sk-original"


@pytest.mark.unit
@pytest.mark.parametrize("new_api_key", ["sk-new", "  sk-new  "])
async def test__update_ai_provider__new_api_key__replaces_and_strips(new_api_key: str) -> None:
    repo = _FakeRepo()
    created = await CreateAIProviderUC(ai_provider_repo=repo).execute(
        CreateAIProviderInput(name="OpenAI", type=AIProviderType.openai, api_key="sk-original")
    )
    uc = UpdateAIProviderUC(ai_provider_repo=repo)

    out = await uc.execute(UpdateAIProviderInput(provider_id=created.provider.id, api_key=new_api_key))

    assert out.provider.api_key == "sk-new"


@pytest.mark.unit
async def test__update_ai_provider__unknown_id__raises() -> None:
    uc = UpdateAIProviderUC(ai_provider_repo=_FakeRepo())
    with pytest.raises(NotFoundError, match="не найден"):
        await uc.execute(UpdateAIProviderInput(provider_id=uuid4(), name="x"))


@pytest.mark.unit
async def test__list_provider_models__returns_lister_output() -> None:
    repo = _FakeRepo()
    created = await CreateAIProviderUC(ai_provider_repo=repo).execute(
        CreateAIProviderInput(name="OpenAI", type=AIProviderType.openai, api_key="sk-x")
    )
    uc = ListProviderModelsUC(ai_provider_repo=repo, model_lister=_FakeLister(["a", "b"]))

    out = await uc.execute(ListProviderModelsInput(provider_id=created.provider.id))

    assert out.models == ["a", "b"]


@pytest.mark.unit
async def test__list_provider_models__unknown_id__raises() -> None:
    uc = ListProviderModelsUC(ai_provider_repo=_FakeRepo(), model_lister=_FakeLister([]))
    with pytest.raises(NotFoundError, match="не найден"):
        await uc.execute(ListProviderModelsInput(provider_id=uuid4()))


@pytest.mark.unit
async def test__create_ai_provider__strips_api_key_whitespace() -> None:
    out = await CreateAIProviderUC(ai_provider_repo=_FakeRepo()).execute(
        CreateAIProviderInput(name="OpenAI", type=AIProviderType.openai, api_key="  sk-padded  ")
    )
    assert out.provider.api_key == "sk-padded"
