"""Сборка документов в CI: параметры, допустимые значения и команда, которую CI запускает.

Файлы CI рендерит порт `ICiRenderer` (шаблоны лежат в infra), здесь только то, что не
зависит от формата YAML: проверка параметров запроса и строка команды сборки.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

# Значения идут в shell-скрипт и в YAML, поэтому допускаем только безопасный алфавит:
# идентификатор документа приходит из project.json, который может прислать соавтор.
_DOC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,199}$")

BUILD_OUT_DIR = "build"
RELEASE_TAG_GLOB = "v*"


class CiProvider(StrEnum):
    github = "github"
    gitlab = "gitlab"


class CiPublish(StrEnum):
    artifacts = "artifacts"
    release = "release"


class CiTrigger(StrEnum):
    push = "push"
    tag = "tag"
    manual = "manual"


# Порядок триггеров в файле не зависит от порядка в запросе: один набор, один результат.
_TRIGGER_ORDER = tuple(CiTrigger)

CI_FILE_PATHS: dict[CiProvider, str] = {
    CiProvider.github: ".github/workflows/hse-studio-build.yml",
    CiProvider.gitlab: ".gitlab-ci.yml",
}


@dataclass(frozen=True)
class CiOptions:
    """Выбор пользователя в диалоге CI. `docs=None` значит «все документы проекта»."""

    provider: CiProvider
    docs: tuple[str, ...] | None
    publish: CiPublish
    triggers: tuple[CiTrigger, ...]
    image: str

    @property
    def path(self) -> str:
        return CI_FILE_PATHS[self.provider]

    @property
    def docs_args(self) -> str:
        return "--all" if self.docs is None else "--docs " + " ".join(self.docs)

    @property
    def command(self) -> str:
        """Та же сборка у себя на машине."""
        return f"hse-doc-studio build . {self.docs_args} --out {BUILD_OUT_DIR}"


@dataclass(frozen=True)
class RenderedCiFile:
    path: str
    content: str


def parse_ci_options(  # noqa: C901 — линейная проверка полей запроса
    *,
    provider: str,
    docs: str | list[str],
    publish: str,
    triggers: list[str],
    image: str | None,
    default_image: str,
) -> CiOptions:
    """Собирает `CiOptions` из сырых значений запроса; на любую неточность ValueError без секретов."""
    try:
        parsed_provider = CiProvider(provider)
        parsed_publish = CiPublish(publish)
        parsed_triggers = {CiTrigger(item) for item in triggers}
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if not parsed_triggers:
        raise ValueError("triggers must not be empty")
    if parsed_publish is CiPublish.release and CiTrigger.tag not in parsed_triggers:
        raise ValueError("a release is made on a tag, so the tag trigger is required")

    if docs == "all":
        parsed_docs: tuple[str, ...] | None = None
    else:
        unique = tuple(dict.fromkeys(docs))
        if not unique:
            raise ValueError("docs must be 'all' or a non-empty list of document ids")
        bad = next((doc for doc in unique if not _DOC_ID_RE.match(doc)), None)
        if bad is not None:
            raise ValueError(f"invalid document id: {bad!r}")
        parsed_docs = unique

    chosen_image = (image or "").strip() or default_image
    if not _IMAGE_RE.match(chosen_image):
        raise ValueError(f"invalid image reference: {chosen_image!r}")

    return CiOptions(
        provider=parsed_provider,
        docs=parsed_docs,
        publish=parsed_publish,
        triggers=tuple(trigger for trigger in _TRIGGER_ORDER if trigger in parsed_triggers),
        image=chosen_image,
    )
