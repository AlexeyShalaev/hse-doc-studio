from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.infra.git_sync.credential_usage import StoreConfigCredentialUsage, read_bound_credential

_ID = UUID("9a8b7c6d-1e2f-4a3b-8c4d-5e6f7a8b9c0d")


def _config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "text",
    [
        f"[hse]\n\tcredential = {_ID}\n",
        f'[hse]\n\tcredential = "{_ID}"\n',
        f"[core]\n\tbare = true\n[HSE]\n\tCredential = {_ID} # комментарий\n",
        f'[remote "origin"]\n\turl = https://github.com/o/r\n[hse]\n\tlocalBranch = master\n\tcredential={_ID}\n',
        f"[hse] credential = {_ID}\n",
    ],
)
def test__read_bound_credential__finds_the_binding(tmp_path: Path, text: str) -> None:
    assert read_bound_credential(_config(tmp_path, text)) == _ID


@pytest.mark.parametrize(
    "text",
    [
        "",
        "[core]\n\tbare = true\n",
        f"[remote]\n\tcredential = {_ID}\n",
        "[hse]\n\tcredential = not-a-uuid\n",
        "[hse]\n\tlocalBranch = master\n",
        "\x00\x01 not a config",
    ],
)
def test__read_bound_credential__no_valid_binding__is_none(tmp_path: Path, text: str) -> None:
    assert read_bound_credential(_config(tmp_path, text)) is None


def test__read_bound_credential__missing_file__is_none(tmp_path: Path) -> None:
    assert read_bound_credential(tmp_path / "absent") is None


class _Index:
    def __init__(self, folders: list[Path]) -> None:
        self._folders = folders

    async def list_all(self) -> list[Path]:
        return self._folders


class _Project:
    def __init__(self, name: str) -> None:
        self.id = uuid4()
        self.name = name


class _Projects:
    def __init__(self, projects: dict[Path, _Project]) -> None:
        self._projects = projects

    def get(self, folder: Path) -> _Project | None:
        if folder.name == "broken":
            raise ValueError("project.json is broken")
        return self._projects.get(folder)


def _store(folder: Path, credential: UUID | None) -> None:
    git_dir = folder / ".hse-studio" / "git"
    git_dir.mkdir(parents=True)
    body = "[core]\n\tbare = false\n"
    if credential is not None:
        body += f"[hse]\n\tcredential = {credential}\n"
    (git_dir / "config").write_text(body, encoding="utf-8")


async def test__by_credential__groups_projects_and_skips_unbound_and_broken(tmp_path: Path) -> None:
    first, second, unbound, broken = (tmp_path / n for n in ("first", "second", "unbound", "broken"))
    other = uuid4()
    for folder, credential in ((first, _ID), (second, _ID), (unbound, None), (broken, other)):
        _store(folder, credential)
    projects = {first: _Project("Первый"), second: _Project("Второй"), unbound: _Project("Без доступа")}
    usage = StoreConfigCredentialUsage(_Index([first, second, unbound, broken]), _Projects(projects))  # type: ignore[arg-type]

    result = await usage.by_credential()

    assert set(result) == {_ID}
    assert [(u.project_id, u.name) for u in result[_ID]] == [
        (projects[first].id, "Первый"),
        (projects[second].id, "Второй"),
    ]


async def test__by_credential__folder_without_store__is_ignored(tmp_path: Path) -> None:
    usage = StoreConfigCredentialUsage(_Index([tmp_path / "gone"]), _Projects({}))  # type: ignore[arg-type]

    assert await usage.by_credential() == {}
