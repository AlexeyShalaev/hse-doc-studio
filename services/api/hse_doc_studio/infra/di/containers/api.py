from __future__ import annotations

from dishka import AsyncContainer, make_async_container
from dishka.integrations.fastapi import FastapiProvider

from hse_doc_studio.infra.di.providers.repositories import RepositoryProvider
from hse_doc_studio.infra.di.providers.services import DomainServiceProvider
from hse_doc_studio.infra.di.providers.use_cases import UseCaseProvider


def create_container() -> AsyncContainer:
    return make_async_container(
        RepositoryProvider(),
        DomainServiceProvider(),
        UseCaseProvider(),
        FastapiProvider(),
    )
