"""Обмен проектом без сервера через настоящий API: выгрузка в файл, слияние чужого файла, проект из файла.

«Две Студии» это два контейнера со своими data_dir и профилями, файл переходит из одной в другую через
тело запроса, как при отправке по почте. Git настоящий, сети нет.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.schemas.git_sync import (
    ConflictSessionResponse,
    GitErrorBody,
    GitStatusResponse,
    OperationResponse,
)
from hse_doc_studio.infra.git_sync.bundle import GitBundleService
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.git_remote import make_bare_remote, run_git
from tests.integration.api.vcs.conftest import TRACKED_FILE, create_project

pytestmark = pytest.mark.integration

_ANNA = {"name": "Анна Петрова", "email": "a.petrova@edu.hse.ru"}
_BORIS = {"name": "Борис Сидоров", "email": "b.sidorov@edu.hse.ru"}
_ANNA_LINE = "% conflicting line: anna"
_BORIS_LINE = "% conflicting line: boris"
_PASSWORD = "обмен-2026"
_WAIT_S = 60.0
_POLL_S = 0.02
_BUNDLE_REF = "refs/hse/bundle/master"


@dataclass
class Studio:
    client: AsyncClient
    root: Path


async def _open(root: Path, profile: dict[str, str] | None) -> tuple[Studio, Callable[[], Any]]:
    data_dir = root / "data"
    data_dir.mkdir(parents=True)
    container = create_test_container(data_dir)
    client = AsyncClient(transport=ASGITransport(app=create_test_app(container)), base_url="http://test")
    if profile is not None:
        resp = await client.put("/api/v1/profile", json=profile)
        assert resp.status_code == 200, resp.text

    async def close() -> None:
        await client.aclose()
        await container.close()

    return Studio(client, root), close


@pytest_asyncio.fixture
async def anna(tmp_path: Path) -> AsyncIterator[Studio]:
    studio, close = await _open(tmp_path / "anna", _ANNA)
    yield studio
    await close()


@pytest_asyncio.fixture
async def boris(tmp_path: Path) -> AsyncIterator[Studio]:
    studio, close = await _open(tmp_path / "boris", _BORIS)
    yield studio
    await close()


@pytest_asyncio.fixture
async def anonymous(tmp_path: Path) -> AsyncIterator[Studio]:
    studio, close = await _open(tmp_path / "anonymous", None)
    yield studio
    await close()


@pytest_asyncio.fixture
async def project(anna: Studio) -> dict[str, Any]:
    return await create_project(anna.client, anna.root / "work" / "thesis")


# --- помощники ----------------------------------------------------------------------------------------------


def _store(project: dict[str, Any]) -> Path:
    return Path(project["folder"]) / ".hse-studio" / "git"


def _git(project: dict[str, Any], *args: str, check: bool = True) -> str:
    return run_git(*args, git_dir=_store(project), work_tree=Path(project["folder"]), check=check)


def _file(project: dict[str, Any], rel: str = TRACKED_FILE) -> Path:
    return Path(project["folder"]) / rel


def _text(project: dict[str, Any], rel: str = TRACKED_FILE) -> str:
    return _file(project, rel).read_text(encoding="utf-8")


def _commit(project: dict[str, Any], message: str) -> str:
    _git(project, "add", "-A")
    _git(project, "-c", "user.name=T", "-c", "user.email=t@test.local", "commit", "--quiet", "-m", message)
    return _git(project, "rev-parse", "HEAD")


def _write(project: dict[str, Any], rel: str, content: str) -> None:
    path = _file(project, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _state(project: dict[str, Any]) -> dict[str, Any]:
    return json.loads((_store(project) / "hse-sync.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _refs(project: dict[str, Any]) -> list[str]:
    """Ссылки хранилища без снимков версий шаблона (`refs/hse/template/*`): они у проекта есть всегда."""
    refs = _git(project, "for-each-ref", "--format=%(refname)").split()
    return [ref for ref in refs if not ref.startswith("refs/hse/template/")]


def _url(project: dict[str, Any], tail: str) -> str:
    return f"/api/v1/projects/{project['id']}/git/{tail}"


def _error(resp: Any) -> GitErrorBody:
    return GitErrorBody.model_validate(resp.json())


def _scratch() -> Path:
    return Path(app_settings.data_dir) / "tmp" / "git-bundles"


def _leftovers() -> list[str]:
    root = _scratch()
    return sorted(entry.name for entry in root.iterdir()) if root.exists() else []


def _edited(text: str, first: str, last: str) -> str:
    lines = text.splitlines()
    return "\n".join([first, *lines[1:-1], last]) + "\n"


async def _export(studio: Studio, project: dict[str, Any], password: str | None = None) -> Any:
    return await studio.client.post(_url(project, "bundle/export"), json={"password": password} if password else {})


async def _bundle(studio: Studio, project: dict[str, Any], password: str | None = None) -> bytes:
    resp = await _export(studio, project, password)
    assert resp.status_code == 200, resp.text
    return resp.content  # type: ignore[no-any-return]


def _upload(content: bytes, name: str = "project.bundle") -> dict[str, Any]:
    return {"file": (name, content, "application/octet-stream")}


async def _import(studio: Studio, project: dict[str, Any], content: bytes, password: str | None = None) -> Any:
    return await studio.client.post(
        _url(project, "bundle/import"), files=_upload(content), data={"password": password} if password else {}
    )


async def _wait(studio: Studio, operation_id: str) -> OperationResponse:
    async with asyncio.timeout(_WAIT_S):
        while True:
            resp = await studio.client.get(f"/api/v1/git/operations/{operation_id}")
            assert resp.status_code == 200, resp.text
            operation = OperationResponse.model_validate(resp.json())
            if operation.status != "running":
                return operation
            await asyncio.sleep(_POLL_S)


async def _imported(studio: Studio, project: dict[str, Any], content: bytes, password: str | None = None) -> Any:
    resp = await _import(studio, project, content, password)
    assert resp.status_code == 202, resp.text
    operation = await _wait(studio, resp.json()["operation_id"])
    assert operation.status == "succeeded", operation.error
    assert operation.kind == "bundle_import"
    assert operation.result is not None
    return operation.result


async def _clone_from(
    studio: Studio, content: bytes, folder: Path, password: str | None = None, name: str = "project.bundle"
) -> Any:
    return await studio.client.post(
        "/api/v1/git/clone/bundle",
        files=_upload(content, name),
        data={"folder": str(folder), **({"password": password} if password else {})},
    )


async def _cloned(studio: Studio, content: bytes, folder: Path, password: str | None = None) -> dict[str, Any]:
    resp = await _clone_from(studio, content, folder, password)
    assert resp.status_code == 202, resp.text
    operation = await _wait(studio, resp.json()["operation_id"])
    assert operation.status == "succeeded", operation.error
    assert operation.result is not None
    shown = await studio.client.get(f"/api/v1/projects/{operation.result.project_id}")
    assert shown.status_code == 200, shown.text
    return shown.json()  # type: ignore[no-any-return]


@pytest_asyncio.fixture
async def copy(anna: Studio, boris: Studio, project: dict[str, Any]) -> dict[str, Any]:
    """Тот же проект у Бориса: он получил его файлом."""
    return await _cloned(boris, await _bundle(anna, project), boris.root / "work" / "thesis")


async def _status(studio: Studio, project: dict[str, Any]) -> GitStatusResponse:
    resp = await studio.client.get(f"/api/v1/projects/{project['id']}/git")
    assert resp.status_code == 200, resp.text
    return GitStatusResponse.model_validate(resp.json())


async def _conflict(anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]) -> bytes:
    """Обе стороны правят первую и последнюю строку по-разному; возвращает файл Анны."""
    original = _text(project)
    _write(project, TRACKED_FILE, _edited(original, f"{_ANNA_LINE} first", f"{_ANNA_LINE} last"))
    _commit(project, "anna")
    _write(copy, TRACKED_FILE, _edited(original, f"{_BORIS_LINE} first", f"{_BORIS_LINE} last"))
    _commit(copy, "boris")
    return await _bundle(anna, project)


# --- выгрузка -----------------------------------------------------------------------------------------------


async def test__export__sends_a_named_file_with_the_branch_only(anna: Studio, project: dict[str, Any]) -> None:
    head = _git(project, "rev-parse", "master")
    _git(project, "update-ref", "refs/hse/template/1.0.0", head)
    _git(project, "tag", "v1")

    resp = await _export(anna, project)

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/octet-stream"
    assert resp.headers["cache-control"] == "no-store"
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert ".bundle" in disposition
    assert not disposition.rstrip('"').endswith(".hseenc")
    assert resp.content.startswith(b"# v2 git bundle\n")
    header = resp.content.split(b"\n\n", 1)[0].decode()
    assert header.splitlines()[1:] == [f"{head} refs/heads/master"]


async def test__export__unsaved_edit__is_snapshotted_into_the_file(
    anna: Studio, boris: Studio, project: dict[str, Any], tmp_path: Path
) -> None:
    _file(project).write_text(_text(project) + "\n% typed but never saved\n", encoding="utf-8")

    cloned = await _cloned(boris, await _bundle(anna, project), tmp_path / "copy")

    assert "% typed but never saved" in _text(cloned)
    assert _git(project, "status", "--porcelain", "--", ".", ":(exclude)*.pdf") == ""


async def test__export__while_the_bundle_is_being_packed__editor_saves_are_not_blocked(
    anna: Studio, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    original = GitBundleService.create_bundle

    async def slow(service: GitBundleService, *args: Any, **kwargs: Any) -> None:
        entered.set()
        await release.wait()
        await original(service, *args, **kwargs)

    monkeypatch.setattr(GitBundleService, "create_bundle", slow)
    exporting = asyncio.create_task(_export(anna, project))
    async with asyncio.timeout(30):
        await entered.wait()

    async with asyncio.timeout(5):
        saved = await anna.client.put(
            f"/api/v1/projects/{project['id']}/files/{TRACKED_FILE}", content=b"% typed during the export\n"
        )
    release.set()
    resp = await exporting

    assert saved.status_code in (200, 204), saved.text
    assert resp.status_code == 200, resp.text


async def test__export__leaves_no_scratch_files_after_the_response(anna: Studio, project: dict[str, Any]) -> None:
    await _bundle(anna, project)
    await _bundle(anna, project, _PASSWORD)

    assert _leftovers() == []


async def test__export__with_password__is_a_sealed_container(anna: Studio, project: dict[str, Any]) -> None:
    plain = await _bundle(anna, project)

    resp = await _export(anna, project, _PASSWORD)

    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"HSEB1")
    assert b"git bundle" not in resp.content[:200]
    assert resp.headers["content-disposition"].rstrip('"').endswith(".bundle.hseenc")
    assert len(resp.content) > len(plain)


async def test__export__password_is_never_echoed_in_validation_errors(anna: Studio, project: dict[str, Any]) -> None:
    resp = await anna.client.post(_url(project, "bundle/export"), json={"password": ["CANARY-secret"]})

    assert resp.status_code == 422
    assert "CANARY-secret" not in json.dumps(resp.json())


async def test__export__without_profile__still_works(anonymous: Studio) -> None:
    created = await create_project(anonymous.client, anonymous.root / "work" / "thesis")

    resp = await _export(anonymous, created)

    assert resp.status_code == 200, resp.text


async def test__export__off_branch__409(anna: Studio, project: dict[str, Any]) -> None:
    await _bundle(anna, project)
    _git(project, "checkout", "--quiet", "-b", "other")
    _write(project, "notes/o.txt", "x\n")
    _commit(project, "elsewhere")
    state = _store(project) / "hse-sync.json"
    state.write_text(json.dumps({"version": 1, "local_branch": "master", "remote_branch": "main"}), encoding="utf-8")

    resp = await _export(anna, project)

    assert resp.status_code == 409
    assert _error(resp).code == "off_branch"
    assert _leftovers() == []


async def test__export__unknown_project__404(anna: Studio) -> None:
    resp = await anna.client.post("/api/v1/projects/00000000-0000-0000-0000-000000000000/git/bundle/export", json={})

    assert resp.status_code == 404


# --- новый проект из файла ----------------------------------------------------------------------------------


async def test__clone_from_bundle__gives_an_equal_project_without_a_remote(
    anna: Studio, boris: Studio, project: dict[str, Any], tmp_path: Path
) -> None:
    folder = boris.root / "work" / "thesis"
    resp = await _clone_from(boris, await _bundle(anna, project), folder)
    assert resp.status_code == 202, resp.text
    operation = await _wait(boris, resp.json()["operation_id"])

    assert operation.status == "succeeded", operation.error
    assert operation.kind == "clone"
    assert operation.result is not None
    assert (str(operation.result.project_id), operation.result.folder, operation.result.access) == (
        project["id"],
        str(folder),
        "full",
    )
    copy = (await boris.client.get(f"/api/v1/projects/{project['id']}")).json()
    assert _text(copy) == _text(project)
    assert _git(copy, "rev-parse", "HEAD") == _git(project, "rev-parse", "HEAD")
    assert _git(copy, "status", "--porcelain", "--", ".", ":(exclude)*.pdf") == ""
    assert not (folder / ".git").exists()
    # Ни ссылок чужой стороны, ни адреса, ни файла состояния: проект не подключён ни к чему.
    assert _refs(copy) == ["refs/heads/master"]
    assert _git(copy, "config", "--get-regexp", "^remote\\.", check=False) == ""
    assert not (_store(copy) / "hse-sync.json").exists()
    status = await _status(boris, copy)
    assert (status.connected, status.ui_state) == (False, "no_remote")
    assert _leftovers() == []


async def test__clone_from_bundle__encrypted__needs_the_password(
    anna: Studio, boris: Studio, project: dict[str, Any]
) -> None:
    sealed = await _bundle(anna, project, _PASSWORD)
    folder = boris.root / "work" / "thesis"

    missing = await _clone_from(boris, sealed, folder, name="project.bundle.hseenc")
    wrong = await _clone_from(boris, sealed, folder, "не тот пароль")

    assert (missing.status_code, _error(missing).code) == (422, "bundle_password_required")
    assert (wrong.status_code, _error(wrong).code) == (422, "bundle_password_wrong")
    assert not folder.exists()
    assert _leftovers() == []
    cloned = await _cloned(boris, sealed, folder, _PASSWORD)
    assert _text(cloned) == _text(project)


async def test__clone_from_bundle__plain_file_with_a_password__password_is_ignored(
    anna: Studio, boris: Studio, project: dict[str, Any]
) -> None:
    cloned = await _cloned(boris, await _bundle(anna, project), boris.root / "work" / "thesis", _PASSWORD)

    assert _text(cloned) == _text(project)


@pytest.mark.parametrize("content", [b"", b"not a bundle at all", b"# v2 git bundle\ntruncated"])
async def test__clone_from_bundle__garbage__is_refused_and_leaves_nothing(
    boris: Studio, content: bytes, tmp_path: Path
) -> None:
    folder = tmp_path / "clones" / "thesis"

    resp = await _clone_from(boris, content, folder)

    assert resp.status_code == 422
    assert _error(resp).code == "bundle_invalid"
    assert not (tmp_path / "clones").exists()
    assert _leftovers() == []


async def test__clone_from_bundle__damaged_pack__fails_in_the_operation_and_removes_the_folder(
    anna: Studio, boris: Studio, project: dict[str, Any], tmp_path: Path
) -> None:
    content = await _bundle(anna, project)
    cut = content[: content.index(b"PACK") + 40]
    folder = tmp_path / "clones" / "thesis"

    resp = await _clone_from(boris, cut, folder)
    assert resp.status_code == 202, resp.text
    operation = await _wait(boris, resp.json()["operation_id"])

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "bundle_invalid"
    assert not (tmp_path / "clones").exists()
    assert (await boris.client.get("/api/v1/projects")).json() == []
    assert _leftovers() == []


async def test__clone_from_bundle__project_already_open__fails_and_names_its_folder(
    anna: Studio, project: dict[str, Any], tmp_path: Path
) -> None:
    folder = tmp_path / "clones" / "second"

    resp = await _clone_from(anna, await _bundle(anna, project), folder)
    operation = await _wait(anna, resp.json()["operation_id"])

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "project_exists"
    assert project["folder"] in operation.error.detail
    assert not folder.exists()
    assert _leftovers() == []


async def test__clone_from_bundle__incremental_file__lacks_prerequisites(
    anna: Studio, boris: Studio, project: dict[str, Any], tmp_path: Path
) -> None:
    _write(project, "notes/two.txt", "two\n")
    _commit(project, "two")
    incremental = tmp_path / "inc.bundle"
    _git(project, "bundle", "create", str(incremental), "master~1..master")

    resp = await _clone_from(boris, incremental.read_bytes(), boris.root / "work" / "thesis")
    operation = await _wait(boris, resp.json()["operation_id"])

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "bundle_prerequisites_missing"
    assert not (boris.root / "work" / "thesis").exists()


async def test__clone_from_bundle__without_profile__profile_required(
    anna: Studio, anonymous: Studio, project: dict[str, Any]
) -> None:
    resp = await _clone_from(anonymous, await _bundle(anna, project), anonymous.root / "work" / "thesis")

    assert resp.status_code == 409
    assert _error(resp).code == "profile_required"
    assert _leftovers() == []


async def test__clone_from_bundle__relative_folder__is_422(
    anna: Studio, boris: Studio, project: dict[str, Any]
) -> None:
    resp = await _clone_from(boris, await _bundle(anna, project), Path("relative/dir"))

    assert resp.status_code == 422
    assert _leftovers() == []


async def test__clone_from_bundle__file_over_the_size_limit__is_refused(
    anna: Studio, boris: Studio, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    content = await _bundle(anna, project)
    monkeypatch.setattr(app_settings.git, "bundle_max_bytes", len(content) - 1)

    resp = await _clone_from(boris, content, boris.root / "work" / "thesis")

    assert resp.status_code == 422
    assert _error(resp).code == "bundle_invalid"
    assert not (boris.root / "work" / "thesis").exists()
    assert _leftovers() == []


# --- слияние файла с проектом -------------------------------------------------------------------------------


async def test__import__newer_file__fast_forwards_without_a_new_commit(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    _write(project, "notes/from-anna.txt", "hello\n")
    anna_head = _commit(project, "anna adds a note")
    before = _git(copy, "rev-parse", "HEAD")

    result = await _imported(boris, copy, await _bundle(anna, project))

    assert result.outcome == "fast_forwarded"
    assert (result.pulled_commits, result.pushed_commits, result.merge_commit) == (1, 0, None)
    assert [(a.path, a.action) for a in result.auto] == [("notes/from-anna.txt", "take_theirs")]
    assert _git(copy, "rev-parse", "HEAD") == anna_head
    assert _git(copy, "rev-parse", "HEAD^") == before
    assert _text(copy, "notes/from-anna.txt") == "hello\n"
    assert _git(copy, "status", "--porcelain", "--", ".", ":(exclude)*.pdf") == ""
    assert _refs(copy) == ["refs/heads/master"]
    assert not (_store(copy).parent / "update" / "journal.json").exists()
    assert _leftovers() == []


async def test__import__same_file_again__is_up_to_date(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    result = await _imported(boris, copy, await _bundle(anna, project))

    assert result.outcome == "up_to_date"
    assert (result.pulled_commits, result.files_changed) == (0, 0)
    assert _refs(copy) == ["refs/heads/master"]


async def test__import__both_sides_changed_different_files__merge_commit_by_the_importer(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    _write(project, "notes/anna.txt", "from anna\n")
    theirs = _commit(project, "anna")
    _write(copy, "notes/boris.txt", "from boris\n")
    ours = _commit(copy, "boris")

    result = await _imported(boris, copy, await _bundle(anna, project))

    assert result.outcome == "merged"
    assert (result.pulled_commits, result.pushed_commits) == (1, 0)
    merge = result.merge_commit
    assert merge is not None
    assert _git(copy, "rev-list", "--parents", "-n1", merge).split() == [merge, ours, theirs]
    body = _git(copy, "log", "-1", "--format=%B", merge)
    assert "Hse-Kind: sync" in body
    assert "Hse-Sync: " in body
    assert body.startswith("Импорт из файла: слияние с master")
    assert _git(copy, "log", "-1", "--format=%an <%ae>", merge) == "Борис Сидоров <b.sidorov@edu.hse.ru>"
    assert _text(copy, "notes/anna.txt") == "from anna\n"
    assert _text(copy, "notes/boris.txt") == "from boris\n"
    assert _git(copy, "status", "--porcelain", "--", ".", ":(exclude)*.pdf") == ""
    assert _refs(copy) == ["refs/heads/master"]


async def test__import__does_not_touch_sync_history_or_the_remote_state(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any], tmp_path: Path
) -> None:
    remote = make_bare_remote(tmp_path / "remotes" / "origin.git")
    _git(copy, "push", "--quiet", remote.url, "master:refs/heads/main")
    resp = await boris.client.put(_url(copy, "remote"), json={"url": remote.url, "credential_id": None})
    assert resp.status_code == 200, resp.text
    _write(project, "notes/anna.txt", "from anna\n")
    _commit(project, "anna")
    remote_head = remote.head()

    result = await _imported(boris, copy, await _bundle(anna, project))

    assert result.outcome == "fast_forwarded"
    assert remote.head() == remote_head
    assert _state(copy)["last_sync"] is None
    status = await _status(boris, copy)
    assert (status.ui_state, status.ahead, status.behind) == ("ahead", 1, 0)
    assert status.last_sync is None


async def test__import__encrypted_file__round_trip(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    _write(project, "notes/secret.txt", "classified\n")
    _commit(project, "anna")
    sealed = await _bundle(anna, project, _PASSWORD)

    missing = await _import(boris, copy, sealed)
    wrong = await _import(boris, copy, sealed, "не тот пароль")
    result = await _imported(boris, copy, sealed, _PASSWORD)

    assert (missing.status_code, _error(missing).code) == (422, "bundle_password_required")
    assert (wrong.status_code, _error(wrong).code) == (422, "bundle_password_wrong")
    assert result.outcome == "fast_forwarded"
    assert _text(copy, "notes/secret.txt") == "classified\n"
    assert _leftovers() == []


async def test__import__plain_file_with_a_password__password_is_ignored(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    _write(project, "notes/a.txt", "a\n")
    _commit(project, "anna")

    result = await _imported(boris, copy, await _bundle(anna, project), _PASSWORD)

    assert result.outcome == "fast_forwarded"


@pytest.mark.parametrize("content", [b"", b"plain text", b"# v2 git bundle\nbroken"])
async def test__import__garbage__422_and_nothing_started(boris: Studio, copy: dict[str, Any], content: bytes) -> None:
    head = _git(copy, "rev-parse", "HEAD")

    resp = await _import(boris, copy, content)

    assert resp.status_code == 422
    assert _error(resp).code == "bundle_invalid"
    assert _git(copy, "rev-parse", "HEAD") == head
    assert (await _status(boris, copy)).operation is None
    assert _leftovers() == []


async def test__import__damaged_pack__operation_fails_and_the_project_is_untouched(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    _write(project, "notes/a.txt", "a\n")
    _commit(project, "anna")
    content = await _bundle(anna, project)
    head = _git(copy, "rev-parse", "HEAD")

    resp = await _import(boris, copy, content[: content.index(b"PACK") + 40])
    operation = await _wait(boris, resp.json()["operation_id"])

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "bundle_invalid"
    assert _git(copy, "rev-parse", "HEAD") == head
    assert _refs(copy) == ["refs/heads/master"]
    assert _leftovers() == []


async def test__import__file_of_another_project__is_refused_without_adoption(
    anna: Studio, boris: Studio, copy: dict[str, Any]
) -> None:
    other = await create_project(anna.client, anna.root / "work" / "other")
    head = _git(copy, "rev-parse", "HEAD")

    resp = await _import(boris, copy, await _bundle(anna, other))
    operation = await _wait(boris, resp.json()["operation_id"])

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "unrelated_histories"
    assert _git(copy, "rev-parse", "HEAD") == head
    assert _refs(copy) == ["refs/heads/master"]


async def test__import__without_profile__profile_required(
    anna: Studio, anonymous: Studio, project: dict[str, Any]
) -> None:
    content = await _bundle(anna, project)
    created = await create_project(anonymous.client, anonymous.root / "work" / "own")

    resp = await _import(anonymous, created, content)

    assert resp.status_code == 409
    assert _error(resp).code == "profile_required"
    assert _leftovers() == []


async def test__import__unknown_project__404(boris: Studio) -> None:
    resp = await boris.client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/git/bundle/import", files=_upload(b"x")
    )

    assert resp.status_code == 404
    assert _leftovers() == []


async def test__import__while_a_git_operation_runs__sync_busy(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hse_doc_studio.use_cases.git_sync import bundles

    gate = asyncio.Event()
    original = bundles.ImportBundleUC._import

    async def held(self: Any, *args: Any, **kwargs: Any) -> Any:
        await gate.wait()
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(bundles.ImportBundleUC, "_import", held)
    content = await _bundle(anna, project)
    first = await _import(boris, copy, content)
    assert first.status_code == 202, first.text

    second = await _import(boris, copy, content)

    assert second.status_code == 409
    assert _error(second).code == "sync_busy"
    assert second.json()["operation_id"] == first.json()["operation_id"]
    gate.set()
    await _wait(boris, first.json()["operation_id"])
    assert _leftovers() == []


async def test__import__file_over_the_size_limit__is_refused(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    content = await _bundle(anna, project)
    monkeypatch.setattr(app_settings.git, "bundle_max_bytes", len(content) - 1)

    resp = await _import(boris, copy, content)

    assert resp.status_code == 422
    assert _error(resp).code == "bundle_invalid"
    assert _leftovers() == []


# --- конфликты ----------------------------------------------------------------------------------------------


async def test__import__conflict__nothing_written_and_session_is_kept_without_a_remote(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    content = await _conflict(anna, boris, project, copy)
    before = _text(copy)
    head = _git(copy, "rev-parse", "HEAD")

    result = await _imported(boris, copy, content)

    assert result.outcome == "conflicts"
    assert result.conflicts is not None
    assert (result.conflicts.files_total, result.conflicts.files_open) == (1, 1)
    assert _text(copy) == before
    assert _git(copy, "rev-parse", "HEAD") == head
    assert _git(copy, "status", "--porcelain", "--", ".", ":(exclude)*.pdf") == ""
    pending = _state(copy)["pending"]
    assert pending["theirs_ref"] == _BUNDLE_REF
    assert pending["theirs"] == _git(project, "rev-parse", "HEAD")
    assert _git(copy, "rev-parse", _BUNDLE_REF) == pending["theirs"]
    resp = await boris.client.get(_url(copy, "conflicts"))
    assert resp.status_code == 200, resp.text
    session = ConflictSessionResponse.model_validate(resp.json())
    assert session.theirs.commit == pending["theirs"]
    assert session.counts.conflict == 1
    assert [f.path for f in session.files if f.action == "conflict"] == [TRACKED_FILE]


async def test__import__conflict__resolving_theirs_merges_locally_and_never_pushes(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    content = await _conflict(anna, boris, project, copy)
    await _imported(boris, copy, content)
    session = ConflictSessionResponse.model_validate((await boris.client.get(_url(copy, "conflicts"))).json())
    ours = _git(copy, "rev-parse", "HEAD")
    theirs = _git(copy, "rev-parse", _BUNDLE_REF)

    resp = await boris.client.post(
        _url(copy, "conflicts/resolve"),
        json={
            "fingerprint": session.fingerprint,
            "resolutions": {TRACKED_FILE: {"kind": "file", "choice": "theirs"}},
            "push": True,
        },
    )
    assert resp.status_code == 202, resp.text
    operation = await _wait(boris, resp.json()["operation_id"])

    assert operation.status == "succeeded", operation.error
    assert operation.kind == "resolve"
    assert operation.result is not None
    assert (operation.result.outcome, operation.result.pushed_commits) == ("merged", 0)
    merge = operation.result.merge_commit
    assert merge is not None
    assert _git(copy, "rev-list", "--parents", "-n1", merge).split() == [merge, ours, theirs]
    assert _git(copy, "log", "-1", "--format=%s", merge).endswith("конфликты решены")
    assert f"{_ANNA_LINE} first" in _text(copy)
    assert _BORIS_LINE not in _text(copy)
    assert _state(copy)["pending"] is None
    assert _refs(copy) == ["refs/heads/master"]
    assert _git(copy, "status", "--porcelain", "--", ".", ":(exclude)*.pdf") == ""
    assert (await boris.client.get(_url(copy, "conflicts"))).status_code == 404


async def test__import__conflict__resolving_mine_keeps_the_local_text(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    content = await _conflict(anna, boris, project, copy)
    await _imported(boris, copy, content)
    session = ConflictSessionResponse.model_validate((await boris.client.get(_url(copy, "conflicts"))).json())

    resp = await boris.client.post(
        _url(copy, "conflicts/resolve"),
        json={
            "fingerprint": session.fingerprint,
            "resolutions": {TRACKED_FILE: {"kind": "file", "choice": "mine"}},
            "push": False,
        },
    )
    operation = await _wait(boris, resp.json()["operation_id"])

    assert operation.status == "succeeded", operation.error
    assert f"{_BORIS_LINE} first" in _text(copy)
    assert _ANNA_LINE not in _text(copy)
    assert _refs(copy) == ["refs/heads/master"]


async def test__import__conflict__abort_drops_the_session_and_the_staged_branch(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    content = await _conflict(anna, boris, project, copy)
    await _imported(boris, copy, content)
    before = _text(copy)

    resp = await boris.client.delete(_url(copy, "conflicts"))

    assert resp.status_code == 200, resp.text
    assert _state(copy)["pending"] is None
    assert _refs(copy) == ["refs/heads/master"]
    assert _text(copy) == before
    assert (await boris.client.get(_url(copy, "conflicts"))).status_code == 404


async def test__import__conflict__status_of_a_project_without_a_remote_shows_the_open_merge(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    content = await _conflict(anna, boris, project, copy)
    await _imported(boris, copy, content)

    status = await _status(boris, copy)

    assert (status.connected, status.remote, status.relation) == (False, None, "none")
    assert status.ui_state == "conflicts"
    assert status.pending is not None
    assert (status.pending.files_total, status.pending.files_open) == (1, 1)
    aborted = await boris.client.delete(_url(copy, "conflicts"))
    assert aborted.status_code == 200, aborted.text
    after = await _status(boris, copy)
    assert (after.ui_state, after.pending) == ("no_remote", None)


async def test__import__open_merge__second_import_is_refused(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any]
) -> None:
    content = await _conflict(anna, boris, project, copy)
    await _imported(boris, copy, content)

    resp = await _import(boris, copy, content)

    assert resp.status_code == 409
    assert _error(resp).code == "sync_incomplete"
    assert _state(copy)["pending"]["theirs_ref"] == _BUNDLE_REF
    assert _leftovers() == []


async def test__import__conflict_in_a_connected_project__sync_is_refused_until_the_merge_is_closed(
    anna: Studio, boris: Studio, project: dict[str, Any], copy: dict[str, Any], tmp_path: Path
) -> None:
    remote = make_bare_remote(tmp_path / "remotes" / "origin.git")
    _git(copy, "push", "--quiet", remote.url, "master:refs/heads/main")
    resp = await boris.client.put(_url(copy, "remote"), json={"url": remote.url, "credential_id": None})
    assert resp.status_code == 200, resp.text
    content = await _conflict(anna, boris, project, copy)
    await _imported(boris, copy, content)

    status = await _status(boris, copy)
    sync = await boris.client.post(_url(copy, "sync"), json={})

    assert status.ui_state == "conflicts"
    assert status.pending is not None
    assert (sync.status_code, _error(sync).code) == (409, "sync_incomplete")
    assert _state(copy)["pending"]["theirs_ref"] == _BUNDLE_REF
    aborted = await boris.client.delete(_url(copy, "conflicts"))
    assert aborted.status_code == 200, aborted.text
    assert (await _status(boris, copy)).ui_state == "ahead"
