"""CI проекта: предпросмотр файлов сборки документов и запись их в папку проекта.

Записывается только сам файл CI выбранного провайдера: ничего другого в проекте
не меняется, а существующий файл с другим содержимым заменяется лишь по `overwrite`.
Файл попадёт на удалённый репозиторий вместе со следующей синхронизацией.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.ci import CiOptions, CiProvider, CiPublish, RenderedCiFile, parse_ci_options
from hse_doc_studio.core.git_sync.protocols import ICiRenderer
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IFileRepository, IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks

logger = structlog.get_logger()


@dataclass(frozen=True)
class CiInput:
    project_id: UUID
    provider: str
    docs: str | list[str]
    publish: str
    triggers: list[str]
    image: str | None = None


@dataclass(frozen=True)
class CiWriteInput(CiInput):
    overwrite: bool = False


@dataclass(frozen=True)
class CiPreviewFile:
    path: str
    content: str
    exists: bool
    same: bool


@dataclass(frozen=True)
class CiPreview:
    files: list[CiPreviewFile]
    command: str
    notes: list[str]


@dataclass(frozen=True)
class CiWritten:
    written: list[str]


def _normalized(text: str) -> str:
    return text.replace("\r\n", "\n")


class _CiBase:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        renderer: ICiRenderer,
        default_image: str,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._file_repo = file_repo
        self._renderer = renderer
        self._default_image = default_image

    def _find(self, project_id: UUID) -> tuple[Path, Project]:
        for folder in self._project_index_repo.list_known():
            try:
                project = self._project_repo.get(folder)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ci: project load failed", folder=str(folder), exc=str(exc))
                continue
            if project is not None and project.id == project_id:
                return folder, project
        raise NotFoundError(localized_error(f"Проект {project_id!r} не найден", f"Project {project_id!r} not found"))

    def _options(self, inp: CiInput, project: Project) -> CiOptions:
        options = parse_ci_options(
            provider=inp.provider,
            docs=inp.docs,
            publish=inp.publish,
            triggers=inp.triggers,
            image=inp.image,
            default_image=self._default_image,
        )
        known = {doc.id for doc in project.documents}
        missing = [doc for doc in options.docs or () if doc not in known]
        if missing:
            raise ValueError(
                localized_error(
                    f"В проекте нет документов: {', '.join(missing)}",
                    f"The project has no documents: {', '.join(missing)}",
                )
            )
        return options

    def _inspect(self, folder: Path, rendered: RenderedCiFile) -> CiPreviewFile:
        try:
            exists = self._file_repo.exists(folder, rendered.path)
            current = self._file_repo.read(folder, rendered.path).decode("utf-8", errors="replace") if exists else None
        except OSError as exc:
            raise ValueError(_unwritable(rendered.path, exc)) from exc
        return CiPreviewFile(
            path=rendered.path,
            content=rendered.content,
            exists=exists,
            same=current is not None and _normalized(current) == _normalized(rendered.content),
        )


class PreviewCiUC(_CiBase):
    async def execute(self, inp: CiInput) -> CiPreview:
        folder, project = self._find(inp.project_id)
        options = self._options(inp, project)
        rendered = self._renderer.render(options)
        return CiPreview(
            files=[self._inspect(folder, rendered)],
            command=options.command,
            notes=_notes(options, project),
        )


class WriteCiUC(_CiBase):
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        renderer: ICiRenderer,
        default_image: str,
        vcs_locks: IVcsFolderLocks,
    ) -> None:
        super().__init__(project_repo, project_index_repo, file_repo, renderer, default_image)
        self._vcs_locks = vcs_locks

    async def execute(self, inp: CiWriteInput) -> CiWritten:
        folder, project = self._find(inp.project_id)
        options = self._options(inp, project)
        file = self._inspect(folder, self._renderer.render(options))
        if file.same or (file.exists and not inp.overwrite):
            return CiWritten(written=[])
        # Применение синхронизации держит замок папки между снимком и записью: без него файл CI попал бы в это окно.
        async with self._vcs_locks.for_folder(folder):
            try:
                self._file_repo.write(folder, file.path, file.content.encode("utf-8"))
            except OSError as exc:
                raise ValueError(_unwritable(file.path, exc)) from exc
        return CiWritten(written=[file.path])


def _unwritable(path: str, exc: Exception) -> str:
    return localized_error(f"Не удалось записать {path}: {exc}", f"Could not write {path}: {exc}")


def _notes(options: CiOptions, project: Project) -> list[str]:
    notes = [
        localized_error(
            "Образ Студии и образ LaTeX скачиваются при первом запуске, он длиннее следующих.",
            "The Studio and LaTeX images are downloaded on the first run, so it takes longer than the next ones.",
        )
    ]
    if options.provider is CiProvider.github:
        notes.append(
            localized_error(
                "Чтобы отправить файл в .github/workflows, токену нужно право workflow.",
                "To push a file under .github/workflows, the token needs the workflow scope.",
            )
        )
        if options.publish is CiPublish.release:
            notes.append(
                localized_error(
                    "Токен для публикации релиза не нужен: используется встроенный токен запуска.",
                    "No token is needed to publish a release: the built-in run token is used.",
                )
            )
    else:
        notes.append(
            localized_error(
                "Раннеру GitLab нужен Docker: привилегированный docker:dind или проброшенный сокет.",
                "The GitLab runner needs Docker: a privileged docker:dind or a bound socket.",
            )
        )
    if project.meta.get("nda"):
        notes.append(
            localized_error(
                "Проект под NDA: сборка на внешнем хостинге отправит его содержимое третьим лицам.",
                "The project is under an NDA: building on an external host sends its content to third parties.",
            )
        )
    return notes
