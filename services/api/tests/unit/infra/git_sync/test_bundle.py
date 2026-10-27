"""Переносной файл проекта над настоящим git: выгрузка одной ветки, шифрование, разбор чужого файла."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.bundle_crypto import BundleFormat
from hse_doc_studio.core.git_sync.bundle_header import parse_bundle_header
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.infra.git_sync.bundle import GitBundleService
from hse_doc_studio.infra.git_sync.git_remote_runner import GitRemoteRunner

from tests.unit.infra.git_sync.conftest import Repo

pytestmark = pytest.mark.unit

_PASSWORD = Secret("пароль для обмена")


class _NoCredentials:
    """Локальные команды секретов не просят."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"credentials are not used by local commands: {name}")


@pytest.fixture
def service() -> GitBundleService:
    config = GitConfig()
    return GitBundleService(GitRemoteRunner(config, _NoCredentials(), local_mode=True), config)  # type: ignore[arg-type]


@pytest.fixture
def target(tmp_path: Path) -> Repo:
    """Второе хранилище, куда приезжает файл: тот же проект, но без последних правок."""
    folder = tmp_path / "target"
    (folder / ".hse-studio").mkdir(parents=True)
    other = Repo(folder)
    other.git.run(other.folder, ["init", "--quiet", "--initial-branch=master"])
    return other


def _code(caught: pytest.ExceptionInfo[GitSyncError]) -> GitErrorCode:
    return caught.value.code


def _refs(repo: Repo) -> list[str]:
    return repo.git.text(repo.folder, ["for-each-ref", "--format=%(refname)"]).split()


async def _export(service: GitBundleService, repo: Repo, tmp_path: Path, name: str = "out.bundle") -> Path:
    dest = tmp_path / name
    await service.create_bundle(repo.folder, branch="master", dest=dest)
    return dest


# --- выгрузка -----------------------------------------------------------------------------------------------


async def test__create__only_the_named_branch_leaves(service: GitBundleService, repo: Repo, tmp_path: Path) -> None:
    repo.snap("work", vkr__extra="x\n")
    head = repo.head()
    repo.branch("side", switch=False)
    repo.git.run(repo.folder, ["update-ref", "refs/hse/template/1.0.0", head])
    repo.git.run(repo.folder, ["update-ref", "refs/remotes/origin/main", head])
    repo.git.run(repo.folder, ["tag", "v1"])

    dest = await _export(service, repo, tmp_path)

    header = parse_bundle_header(dest.read_bytes()[:4096])
    assert header is not None
    assert [(h.ref, h.sha) for h in header.heads] == [("refs/heads/master", head)]
    assert header.prerequisites == ()


async def test__create__branch_that_does_not_exist__is_refused(
    service: GitBundleService, repo: Repo, tmp_path: Path
) -> None:
    with pytest.raises(GitSyncError):
        await service.create_bundle(repo.folder, branch="nope", dest=tmp_path / "x.bundle")


async def test__create__branch_name_that_looks_like_an_option__is_refused(
    service: GitBundleService, repo: Repo, tmp_path: Path
) -> None:
    with pytest.raises(GitSyncError) as caught:
        await service.create_bundle(repo.folder, branch="--all", dest=tmp_path / "x.bundle")
    assert _code(caught) is GitErrorCode.branch_missing


# --- шифрование и вид файла ---------------------------------------------------------------------------------


async def test__encrypted_round_trip__gives_the_same_bytes(
    service: GitBundleService, repo: Repo, tmp_path: Path
) -> None:
    plain = await _export(service, repo, tmp_path)
    sealed = tmp_path / "out.bundle.hseenc"
    service.encrypt_bundle(plain, sealed, _PASSWORD)
    work = tmp_path / "work"
    work.mkdir()

    assert service.check_upload(sealed, _PASSWORD) is BundleFormat.encrypted
    opened = service.unpack(sealed, work, _PASSWORD)

    assert opened != sealed
    assert opened.read_bytes() == plain.read_bytes()
    assert sealed.read_bytes()[:5] == b"HSEB1"
    assert plain.read_bytes()[:20] not in sealed.read_bytes()


async def test__check_upload__encrypted_without_password__asks_for_it(
    service: GitBundleService, repo: Repo, tmp_path: Path
) -> None:
    sealed = tmp_path / "s.hseenc"
    service.encrypt_bundle(await _export(service, repo, tmp_path), sealed, _PASSWORD)

    with pytest.raises(GitSyncError) as caught:
        service.check_upload(sealed, None)

    assert _code(caught) is GitErrorCode.bundle_password_required


async def test__check_upload__wrong_password__is_told_at_once(
    service: GitBundleService, repo: Repo, tmp_path: Path
) -> None:
    sealed = tmp_path / "s.hseenc"
    service.encrypt_bundle(await _export(service, repo, tmp_path), sealed, _PASSWORD)

    with pytest.raises(GitSyncError) as caught:
        service.check_upload(sealed, Secret("другой"))

    assert _code(caught) is GitErrorCode.bundle_password_wrong


async def test__check_upload__plain_file_with_password__password_is_ignored(
    service: GitBundleService, repo: Repo, tmp_path: Path
) -> None:
    plain = await _export(service, repo, tmp_path)
    work = tmp_path / "work"
    work.mkdir()

    assert service.check_upload(plain, _PASSWORD) is BundleFormat.plain
    assert service.unpack(plain, work, _PASSWORD) == plain
    assert list(work.iterdir()) == []


@pytest.mark.parametrize("content", [b"", b"hello", b"PK\x03\x04zip", b"# v2 git bundle\nbroken"])
def test__check_upload__not_a_bundle__is_invalid(service: GitBundleService, tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "x"
    path.write_bytes(content)

    with pytest.raises(GitSyncError) as caught:
        service.check_upload(path, None)

    assert _code(caught) is GitErrorCode.bundle_invalid


async def test__unpack__damaged_container__is_invalid_not_wrong_password(
    service: GitBundleService, repo: Repo, tmp_path: Path
) -> None:
    sealed = tmp_path / "s.hseenc"
    service.encrypt_bundle(await _export(service, repo, tmp_path), sealed, _PASSWORD)
    sealed.write_bytes(sealed.read_bytes()[:-7])
    work = tmp_path / "work"
    work.mkdir()

    with pytest.raises(GitSyncError) as caught:
        service.unpack(sealed, work, _PASSWORD)

    assert _code(caught) is GitErrorCode.bundle_invalid


# --- чужой файл ---------------------------------------------------------------------------------------------


def test__read_header__other_object_format__is_invalid(service: GitBundleService, tmp_path: Path) -> None:
    path = tmp_path / "x.bundle"
    path.write_bytes(f"# v3 git bundle\n@object-format=sha256\n{'a' * 40} refs/heads/m\n\n".encode())

    with pytest.raises(GitSyncError) as caught:
        service.read_header(path)

    assert _code(caught) is GitErrorCode.bundle_invalid


def test__read_header__partial_clone_filter__is_invalid(service: GitBundleService, tmp_path: Path) -> None:
    path = tmp_path / "x.bundle"
    path.write_bytes(f"# v3 git bundle\n@filter=blob:none\n{'a' * 40} refs/heads/m\n\n".encode())

    with pytest.raises(GitSyncError):
        service.read_header(path)


async def test__stage__puts_the_branch_in_its_own_ref_and_nothing_else(
    service: GitBundleService, repo: Repo, target: Repo, tmp_path: Path
) -> None:
    repo.snap("one", vkr__one="1\n")
    head = repo.head()
    plain = await _export(service, repo, tmp_path)

    await service.verify(target.folder, plain)
    tip = await service.stage_branch(target.folder, plain, branch="master", ref="refs/hse/bundle/master")

    assert tip == head
    assert _refs(target) == ["refs/hse/bundle/master"]
    assert target.git.text(target.folder, ["cat-file", "-t", head]).strip() == "commit"
    assert target.show(head, "vkr/one") == b"1\n"


async def test__stage__tags_and_other_refs_in_the_file_are_ignored(
    service: GitBundleService, repo: Repo, target: Repo, tmp_path: Path
) -> None:
    repo.git.run(repo.folder, ["tag", "v1"])
    repo.branch("side", switch=False)
    plain = tmp_path / "all.bundle"
    repo.git.run(repo.folder, ["bundle", "create", str(plain), "--all"])

    header = service.read_header(plain)
    assert len(header.heads) >= 3

    await service.stage_branch(target.folder, plain, branch="master", ref="refs/hse/bundle/master")

    assert _refs(target) == ["refs/hse/bundle/master"]


async def test__verify__incremental_file_in_a_store_without_history__lacks_prerequisites(
    service: GitBundleService, repo: Repo, target: Repo, tmp_path: Path
) -> None:
    repo.snap("two", vkr__two="2\n")
    plain = tmp_path / "inc.bundle"
    repo.git.run(repo.folder, ["bundle", "create", str(plain), "master~1..master"])

    with pytest.raises(GitSyncError) as caught:
        await service.verify(target.folder, plain)

    assert _code(caught) is GitErrorCode.bundle_prerequisites_missing


async def test__verify__garbage_after_a_valid_header__is_invalid(
    service: GitBundleService, repo: Repo, target: Repo, tmp_path: Path
) -> None:
    plain = await _export(service, repo, tmp_path)
    cut = plain.read_bytes()
    plain.write_bytes(cut[: cut.index(b"PACK") + 12])

    with pytest.raises(GitSyncError) as caught:
        await service.stage_branch(target.folder, plain, branch="master", ref="refs/hse/bundle/master")

    assert _code(caught) is GitErrorCode.bundle_invalid
    assert _refs(target) == []


async def test__stage__ref_stays_in_the_bundle_namespace_for_odd_branch_names(
    service: GitBundleService, repo: Repo, target: Repo, tmp_path: Path
) -> None:
    plain = await _export(service, repo, tmp_path)

    with pytest.raises(GitSyncError) as caught:
        await service.stage_branch(target.folder, plain, branch="a..b", ref="refs/hse/bundle/a..b")

    assert _code(caught) is GitErrorCode.branch_missing
