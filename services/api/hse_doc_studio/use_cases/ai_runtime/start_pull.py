from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_catalog import ModelCatalog
from hse_doc_studio.core.ai_runtime import IPullModelJobs
from hse_doc_studio.core.entities import PullJob
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.ai_runtime.model_ref import is_valid_model_ref


@dataclass
class StartPullInput:
    name: str


class StartPullUC:
    """Validate a model name and start a background download job for it.

    The catalog is the recommended set, not a hard wall: a catalog name always
    passes; any other name passes only when `allow_custom` is on AND it is a
    validly-formatted model reference.
    """

    def __init__(self, jobs: IPullModelJobs, catalog: ModelCatalog, allow_custom: bool) -> None:
        self._jobs = jobs
        self._catalog = catalog
        self._allow_custom = allow_custom

    async def execute(self, inp: StartPullInput) -> PullJob:
        name = inp.name.strip()
        if not name:
            raise ValueError(localized_error("укажите название модели", "model name is required"))
        if name not in {m.name for m in self._catalog.models}:
            if not self._allow_custom:
                raise ValueError(localized_error(f"модели нет в каталоге: {name}", f"model not in catalog: {name}"))
            if not is_valid_model_ref(name):
                raise ValueError(
                    localized_error(f"некорректное название модели: {name}", f"invalid model name: {name}")
                )
        return await self._jobs.start(name)
