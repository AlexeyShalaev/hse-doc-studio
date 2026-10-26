from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.git_sync.entities import ContentsFile, RepoContents, TreeEntry
from hse_doc_studio.core.git_sync.protocols import IGitRepoReader
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.entities import VcsAuthor, VcsSettings
from hse_doc_studio.core.vcs.errors import VcsCommandError
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

_LARGEST = 5
_SIGNATURES_DIR = ".hse-studio/signatures/"
_NDA_DIR = "nda"
_BLOB = "blob"
_REGULAR_FILE_MODES = frozenset({"100644", "100755"})
# Указатель Git LFS занимает около 130 байт; читаем только такие файлы.
_LFS_MAX_BYTES = 200
_LFS_MAX_CANDIDATES = 2000
_LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1"


@dataclass
class GetGitContentsInput:
    project_id: UUID


class GetGitContentsUC:
    """Что попадёт в удалённый репозиторий: считается по истории текущей ветки, без сети."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        reader: IGitRepoReader,
        bot_author: VcsAuthor,
        large_file_bytes: int,
    ) -> None:
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._reader = reader
        self._bot_email = bot_author.email.casefold()
        self._limit = large_file_bytes

    async def execute(self, inp: GetGitContentsInput) -> RepoContents:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        track_pdf = VcsSettings.from_meta(project.meta).track_pdf
        return await asyncio.to_thread(self._collect, project.folder, track_pdf)

    def _collect(self, folder: Path, track_pdf: bool) -> RepoContents:
        head = self._head(folder)
        if head is None:
            return self._empty(track_pdf)
        blobs = [e for e in self._reader.tree_entries(folder, head) if e.kind == _BLOB]
        authors = self._reader.author_counts(folder, head)
        largest = sorted((e for e in blobs if e.size), key=lambda e: (-(e.size or 0), e.path))[:_LARGEST]
        over_limit = self._reader.large_blobs(folder, head, min_bytes=self._limit)
        return RepoContents(
            files=len(blobs),
            bytes=sum(e.size or 0 for e in blobs),
            commits=sum(a.commits for a in authors),
            bot_authored_commits=sum(a.commits for a in authors if a.email.casefold() == self._bot_email),
            signatures=sum(1 for e in blobs if e.path.startswith(_SIGNATURES_DIR)),
            nda_files=sum(1 for e in blobs if _in_nda_folder(e.path)),
            pdf_tracked=track_pdf,
            largest=tuple(ContentsFile(e.path, e.size or 0) for e in largest),
            over_limit=tuple(ContentsFile(b.path, b.size) for b in over_limit),
            limit_bytes=self._limit,
            lfs_pointers=self._count_lfs_pointers(folder, head, blobs),
        )

    def _head(self, folder: Path) -> str | None:
        try:
            return self._reader.rev_parse(folder, "HEAD")
        except VcsCommandError:
            # Хранилища ещё нет (проект без истории): публиковать нечего.
            return None

    def _empty(self, track_pdf: bool) -> RepoContents:
        return RepoContents(
            files=0,
            bytes=0,
            commits=0,
            bot_authored_commits=0,
            signatures=0,
            nda_files=0,
            pdf_tracked=track_pdf,
            largest=(),
            over_limit=(),
            limit_bytes=self._limit,
            lfs_pointers=0,
        )

    def _count_lfs_pointers(self, folder: Path, head: str, blobs: list[TreeEntry]) -> int:
        candidates = [
            e.path
            for e in blobs
            if e.mode in _REGULAR_FILE_MODES and e.size is not None and 0 < e.size <= _LFS_MAX_BYTES
        ][:_LFS_MAX_CANDIDATES]
        if not candidates:
            return 0
        contents = self._reader.read_files(folder, head, candidates)
        return sum(1 for data in contents.values() if data is not None and data.startswith(_LFS_PREFIX))


def _in_nda_folder(path: str) -> bool:
    """Файл лежит в каталоге `nda`: в корне проекта или в папке автора (`<автор>/nda/...`)."""
    return _NDA_DIR in path.casefold().split("/")[:-1]
