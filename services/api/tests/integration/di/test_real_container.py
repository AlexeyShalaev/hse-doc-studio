"""Сборка настоящего DI-контейнера.

Остальные тесты используют TestRepositoryProvider, поэтому реальная связка
RepositoryProvider + DomainServiceProvider + UseCaseProvider нигде не проверяется.
dishka валидирует граф при сборке: пропавшая фабрика падает здесь, а не при старте.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.update.repositories import ISelfUpdateGateway
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.use_cases.compile.trigger_compile import TriggerCompileUC
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC


@pytest.fixture
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Синглтон settings общий на процесс: возвращаем его в исходное состояние."""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "host_data_dir", None)


@pytest.mark.usefixtures("isolated_settings")
async def test__real_container__builds__resolves_core_services() -> None:
    container = create_container()
    try:
        async with container() as request_container:
            gateway = await request_container.get(ISelfUpdateGateway)
            get_project = await request_container.get(GetProjectUC)
            trigger_compile = await request_container.get(TriggerCompileUC)
    finally:
        await container.close()

    assert gateway is not None
    assert isinstance(get_project, GetProjectUC)
    assert isinstance(trigger_compile, TriggerCompileUC)
