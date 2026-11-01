from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.ci import CiOptions, CiProvider, CiPublish, CiTrigger, RenderedCiFile
from hse_doc_studio.infra.git_sync.ci_renderer import JinjaCiRenderer
from hse_doc_studio.infra.persistence.project_locator import LocalProjectLocator
from hse_doc_studio.use_cases.git_sync.ci import CiInput, CiWriteInput, PreviewCiUC, WriteCiUC

_IMAGE = "ghcr.io/alexeyshalaev/hse-doc-studio:0.2.0"
_GITHUB_PATH = ".github/workflows/hse-studio-build.yml"


@dataclass
class _Doc:
    id: str


@dataclass
class _Project:
    id: Any
    documents: list[_Doc]
    meta: dict[str, Any] = field(default_factory=dict)


class _Projects:
    def __init__(self, project: _Project) -> None:
        self._project = project

    def get(self, folder: Path) -> Project:
        return self._project  # type: ignore[return-value]


class _Index:
    def __init__(self, folders: list[Path]) -> None:
        self._folders = folders

    def list_known(self) -> list[Path]:
        return self._folders


class _Locks:
    """Замок папки: помнит, держится ли он сейчас, чтобы проверить запись под замком."""

    def __init__(self) -> None:
        self.held = False

    @asynccontextmanager
    async def for_folder(self, folder: Path) -> AsyncIterator[None]:  # noqa: ARG002
        self.held = True
        try:
            yield
        finally:
            self.held = False


class _Files:
    """Файлы в памяти; пишет только то, что ему велели."""

    def __init__(
        self, files: dict[str, bytes] | None = None, *, write_error: OSError | None = None, locks: _Locks | None = None
    ) -> None:
        self.files = files or {}
        self.locks = locks
        self.written_under_lock: list[bool] = []
        self.writes: list[str] = []
        self._write_error = write_error

    def exists(self, folder: Path, path: str) -> bool:
        return path in self.files

    def read(self, folder: Path, path: str) -> bytes:
        return self.files[path]

    def write(self, folder: Path, path: str, content: bytes) -> None:
        if self._write_error is not None:
            raise self._write_error
        self.files[path] = content
        self.writes.append(path)
        self.written_under_lock.append(self.locks is not None and self.locks.held)


@dataclass
class _Setup:
    project: _Project
    files: _Files
    locks: _Locks

    def preview(self) -> PreviewCiUC:
        return PreviewCiUC(*self._deps())

    def write(self) -> WriteCiUC:
        return WriteCiUC(*self._deps(), self.locks)

    def _deps(self) -> tuple[Any, Any, Any, str]:
        return (
            LocalProjectLocator(_Index([Path("/p")]), _Projects(self.project)),  # type: ignore[arg-type]
            self.files,
            JinjaCiRenderer(),
            _IMAGE,
        )


def _setup(*, files: _Files | None = None, meta: dict[str, Any] | None = None) -> _Setup:
    project = _Project(id=uuid4(), documents=[_Doc("tz"), _Doc("vkr")], meta=meta or {})
    locks = _Locks()
    return _Setup(project=project, files=files or _Files(locks=locks), locks=locks)


def _input(setup: _Setup, **overrides: Any) -> CiInput:
    args: dict[str, Any] = {
        "project_id": setup.project.id,
        "provider": "github",
        "docs": "all",
        "publish": "artifacts",
        "triggers": ["push"],
    }
    args.update(overrides)
    return CiInput(**args)


def _write_input(setup: _Setup, *, overwrite: bool, **overrides: Any) -> CiWriteInput:
    base = _input(setup, **overrides)
    return CiWriteInput(**base.__dict__, overwrite=overwrite)


def _rendered() -> RenderedCiFile:
    """Файл, который по умолчанию ждёт тест: GitHub, все документы, артефакты, push."""
    options = CiOptions(
        provider=CiProvider.github,
        docs=None,
        publish=CiPublish.artifacts,
        triggers=(CiTrigger.push,),
        image=_IMAGE,
    )
    return JinjaCiRenderer().render(options)


async def test__preview__no_file_yet__reports_it_as_new() -> None:
    setup = _setup()

    result = await setup.preview().execute(_input(setup))

    [file] = result.files
    assert (file.path, file.exists, file.same) == (_GITHUB_PATH, False, False)
    assert file.content == _rendered().content
    assert result.command == "hse-doc-studio build . --all --out build"
    assert setup.files.writes == []


async def test__preview__identical_file__is_same_even_with_crlf() -> None:
    content = _rendered().content.replace("\n", "\r\n").encode()
    setup = _setup(files=_Files({_GITHUB_PATH: content}))

    [file] = (await setup.preview().execute(_input(setup))).files

    assert (file.exists, file.same) == (True, True)


async def test__preview__edited_file__exists_but_differs() -> None:
    setup = _setup(files=_Files({_GITHUB_PATH: b"name: mine\n"}))

    [file] = (await setup.preview().execute(_input(setup))).files

    assert (file.exists, file.same) == (True, False)


async def test__preview__binary_garbage_in_place_of_the_file__differs() -> None:
    setup = _setup(files=_Files({_GITHUB_PATH: b"\xff\xfe\x00"}))

    [file] = (await setup.preview().execute(_input(setup))).files

    assert (file.exists, file.same) == (True, False)


async def test__preview__unknown_project__raises_not_found() -> None:
    setup = _setup()

    with pytest.raises(NotFoundError):
        await setup.preview().execute(_input(setup, project_id=uuid4()))


async def test__preview__unknown_document__raises_value_error_naming_it() -> None:
    setup = _setup()

    with pytest.raises(ValueError, match="ghost"):
        await setup.preview().execute(_input(setup, docs=["tz", "ghost"]))


async def test__preview__listed_documents__go_into_the_command() -> None:
    setup = _setup()

    result = await setup.preview().execute(_input(setup, docs=["vkr"]))

    assert result.command == "hse-doc-studio build . --docs vkr --out build"


async def test__preview__github__warns_about_workflow_scope_and_not_about_nda() -> None:
    setup = _setup()

    notes = (await setup.preview().execute(_input(setup))).notes

    assert any("workflow" in note for note in notes)
    assert not any("NDA" in note for note in notes)


async def test__preview__github_release__says_no_token_is_needed() -> None:
    setup = _setup()

    notes = (await setup.preview().execute(_input(setup, publish="release", triggers=["tag"]))).notes

    assert any("токен" in note.lower() or "token" in note.lower() for note in notes)


async def test__preview__gitlab__mentions_docker_on_the_runner_and_not_workflow_scope() -> None:
    setup = _setup()

    result = await setup.preview().execute(_input(setup, provider="gitlab"))

    assert result.files[0].path == ".gitlab-ci.yml"
    assert any("Docker" in note for note in result.notes)
    assert not any("workflow" in note for note in result.notes)


async def test__preview__nda_project__warns_that_content_goes_to_a_third_party() -> None:
    setup = _setup(meta={"nda": True})

    notes = (await setup.preview().execute(_input(setup))).notes

    assert any("NDA" in note for note in notes)


async def test__write__new_file__is_written_and_listed() -> None:
    setup = _setup()

    result = await setup.write().execute(_write_input(setup, overwrite=False))

    assert result.written == [_GITHUB_PATH]
    assert setup.files.files[_GITHUB_PATH].decode() == _rendered().content


async def test__write__same_file__is_not_rewritten() -> None:
    setup = _setup(files=_Files({_GITHUB_PATH: _rendered().content.encode()}))

    result = await setup.write().execute(_write_input(setup, overwrite=True))

    assert result.written == []
    assert setup.files.writes == []


async def test__write__edited_file_without_overwrite__is_left_alone() -> None:
    setup = _setup(files=_Files({_GITHUB_PATH: b"name: mine\n"}))

    result = await setup.write().execute(_write_input(setup, overwrite=False))

    assert result.written == []
    assert setup.files.files[_GITHUB_PATH] == b"name: mine\n"


async def test__write__edited_file_with_overwrite__is_replaced() -> None:
    setup = _setup(files=_Files({_GITHUB_PATH: b"name: mine\n"}))

    result = await setup.write().execute(_write_input(setup, overwrite=True))

    assert result.written == [_GITHUB_PATH]
    assert setup.files.files[_GITHUB_PATH].decode() == _rendered().content


async def test__write__other_files__are_never_touched() -> None:
    other = {"tz/tz.tex": b"x", ".gitlab-ci.yml": b"stages: []\n", "README.md": b"r"}
    setup = _setup(files=_Files(dict(other)))

    await setup.write().execute(_write_input(setup, overwrite=True))

    assert {path: setup.files.files[path] for path in other} == other
    assert setup.files.writes == [_GITHUB_PATH]


async def test__write__disk_refuses__raises_value_error() -> None:
    setup = _setup(files=_Files(write_error=PermissionError("denied")))

    with pytest.raises(ValueError, match="denied"):
        await setup.write().execute(_write_input(setup, overwrite=False))


async def test__write__file_is_written_under_the_folder_lock() -> None:
    # Применение синхронизации держит замок между снимком и записью: запись CI-файла не должна влезать в это окно.
    setup = _setup()

    await setup.write().execute(_write_input(setup, overwrite=False))

    assert setup.files.written_under_lock == [True]
