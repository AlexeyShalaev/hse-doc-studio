"""Перенос из локальной Студии на сервер: проект из zip (id, история git, чаты, отказы) и данные пользователя (CLI)."""

from __future__ import annotations

import json
import subprocess
import zipfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from hse_doc_studio import cli_import
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import AIProvider, ChatContentBlock, ChatMessage, ChatSession
from hse_doc_studio.core.enums import AIProviderType, ChatContentKind, ChatMessageRole
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.projects.importer import ProjectImportCode, ProjectImportError
from hse_doc_studio.core.repositories import IAIProviderRepository, IChatRepository, ISettingsRepository
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.use_cases.projects.import_project import ImportProjectInput, ImportProjectUC
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user
from tests.factories import make_project
from tests.fixtures.actors import as_actor

pytestmark = pytest.mark.pg

ANNA = Actor.user("anna", name="Анна", email="anna@example.test")
BORIS = Actor.user("boris", name="Борис", email="boris@example.test")
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@dataclass
class World:
    container: object
    sessions: SessionProvider
    root: Path
    local: Path

    def projects(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir()) if self.root.exists() else []

    async def rows(self) -> list[ProjectRow]:
        async with self.sessions.use() as session:
            return list((await session.execute(select(ProjectRow))).scalars().all())


@pytest_asyncio.fixture
async def world(
    pg_migrated_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[World]:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings.server, "projects_root", tmp_path / "projects")
    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    await users.add(make_user("anna", "anna@example.test"))
    await users.add(make_user("boris", "boris@example.test"))
    container = create_container(StudioMode.server, engine=pg_migrated_engine)
    try:
        yield World(container, sessions, tmp_path / "projects", tmp_path / "local")
    finally:
        await container.close()


def git(folder: Path, *args: str) -> str:
    store = folder / ".hse-studio" / "git"
    env = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
    }
    done = subprocess.run(  # noqa: S603 — тест гоняет git по своей временной папке
        ["git", f"--git-dir={store}", f"--work-tree={folder}", "-c", "user.name=T", "-c", "user.email=t@t.test", *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return done.stdout


async def make_local_project(world: World, *, with_chat: bool = False) -> tuple[Path, UUID]:
    """Папка как у локальной Студии: project.json, исходники, git-хранилище с двумя коммитами и чат агента."""
    folder = world.local
    folder.mkdir(parents=True)
    project = make_project(folder=folder, name="Локальная курсовая")
    JsonProjectRepository().save(project)
    (folder / "main.tex").write_text("one", encoding="utf-8")
    (folder / "chapters").mkdir()
    (folder / "chapters" / "intro.tex").write_text("intro", encoding="utf-8")
    git(folder, "init", "-q")
    git(folder, "add", "-A")
    git(folder, "commit", "-q", "-m", "первый")
    (folder / "main.tex").write_text("two", encoding="utf-8")
    git(folder, "add", "-A")
    git(folder, "commit", "-q", "-m", "второй")
    if with_chat:
        chats = JsonChatRepository()
        session = ChatSession(
            id=uuid4(), project_folder=folder, title="Про введение", doc_id=None, created_at=T0, updated_at=T0
        )
        await chats.save_session(session)
        for text in ("привет", "ответ"):
            message = ChatMessage(
                id=uuid4(),
                session_id=session.id,
                run_id=None,
                seq=-1,
                role=ChatMessageRole.user,
                blocks=[ChatContentBlock(kind=ChatContentKind.text, text=text)],
                created_at=T0,
            )
            await chats.append_message(folder, message)
    return folder, project.id


def zip_of(folder: Path, target: Path) -> Path:
    cli_import.zip_folder(folder, target)
    return target


async def do_import(world: World, archive: Path, actor: Actor = ANNA) -> object:
    async with world.container() as request:  # type: ignore[operator]
        uc = await request.get(ImportProjectUC)
        with as_actor(actor):
            return await uc.execute(ImportProjectInput(archive=archive))


async def test__import_project__keeps_free_id_files_and_git_history(world: World, tmp_path: Path) -> None:
    folder, original_id = await make_local_project(world)
    history = git(folder, "log", "--format=%H")

    report = await do_import(world, zip_of(folder, tmp_path / "p.zip"))

    assert report.project_id == original_id
    assert report.id_regenerated is False
    target = world.root / str(original_id)
    assert (target / "main.tex").read_text(encoding="utf-8") == "two"
    assert (target / "chapters" / "intro.tex").read_text(encoding="utf-8") == "intro"
    assert git(target, "log", "--format=%H") == history
    assert git(target, "show", "HEAD~1:main.tex") == "one"
    [row] = await world.rows()
    assert (row.id, row.owner_user_id, row.name) == (original_id, "anna", "Локальная курсовая")


async def test__import_project__same_archive_twice__second_gets_new_consistent_id(world: World, tmp_path: Path) -> None:
    folder, original_id = await make_local_project(world)
    archive = zip_of(folder, tmp_path / "p.zip")

    first = await do_import(world, archive)
    second = await do_import(world, archive)

    assert (first.project_id, second.id_regenerated) == (original_id, True)
    assert second.project_id != original_id
    assert world.projects() == sorted([str(original_id), str(second.project_id)])
    stored = JsonProjectRepository().get(world.root / str(second.project_id))
    assert stored is not None
    assert stored.id == second.project_id
    assert len(await world.rows()) == 2


async def test__import_project__other_user_with_same_id__gets_new_id_and_own_row(world: World, tmp_path: Path) -> None:
    folder, original_id = await make_local_project(world)
    archive = zip_of(folder, tmp_path / "p.zip")
    await do_import(world, archive, ANNA)

    boris = await do_import(world, archive, BORIS)

    assert boris.id_regenerated is True
    owners = {str(r.id): r.owner_user_id for r in await world.rows()}
    assert owners == {str(original_id): "anna", str(boris.project_id): "boris"}


async def test__import_project__chats_move_to_owner_only(world: World, tmp_path: Path) -> None:
    folder, _ = await make_local_project(world, with_chat=True)

    report = await do_import(world, zip_of(folder, tmp_path / "p.zip"))

    assert report.chats == 1
    target = world.root / str(report.project_id)
    assert not (target / ".hse-studio" / "chats").exists()
    async with world.container() as request:  # type: ignore[operator]
        chats = await request.get(IChatRepository)
        with as_actor(ANNA):
            [session] = await chats.list_sessions(target)
            messages = await chats.list_messages(target, session.id)
        with as_actor(BORIS):
            assert await chats.list_sessions(target) == []
    assert (session.title, session.project_id) == ("Про введение", report.project_id)
    assert [m.seq for m in messages] == [0, 1]


async def test__import_project__same_chat_twice__ids_do_not_collide(world: World, tmp_path: Path) -> None:
    folder, _ = await make_local_project(world, with_chat=True)
    archive = zip_of(folder, tmp_path / "p.zip")

    await do_import(world, archive)
    second = await do_import(world, archive)

    assert second.chats == 1


async def test__import_project__rejected_archive__nothing_written(world: World, tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(".hse-studio/project.json", json.dumps({"id": str(uuid4()), "name": "x"}))
        zf.writestr("../escape.txt", "x")

    with pytest.raises(ProjectImportError) as caught:
        await do_import(world, archive)

    assert caught.value.code is ProjectImportCode.archive_unsafe
    assert world.projects() == []
    assert await world.rows() == []
    assert not (tmp_path / "escape.txt").exists()


async def test__import_project__failure_after_allocation__folder_and_rows_rolled_back(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _ = await make_local_project(world, with_chat=True)
    archive = zip_of(folder, tmp_path / "p.zip")

    async def boom(*_: object, **__: object) -> int:
        raise RuntimeError("chat transfer failed")

    from hse_doc_studio.infra.projects.local_history import LocalChatHistory

    monkeypatch.setattr(LocalChatHistory, "transfer_chats", boom)

    with pytest.raises(RuntimeError, match="chat transfer failed"):
        await do_import(world, archive)

    assert world.projects() == []
    assert await world.rows() == []


async def test__import_project__remote_and_records__reported_as_warnings(world: World, tmp_path: Path) -> None:
    folder, _ = await make_local_project(world)
    git(folder, "remote", "add", "origin", "https://example.test/r.git")
    (folder / ".hse-studio" / "compiles").mkdir()
    (folder / ".hse-studio" / "compiles" / "a.json").write_text("{}", encoding="utf-8")

    report = await do_import(world, zip_of(folder, tmp_path / "p.zip"))

    codes = {w.code.value for w in report.warnings}
    assert {"remote_needs_access", "records_skipped"} <= codes
    assert not (world.root / str(report.project_id) / ".hse-studio" / "compiles").exists()


async def test__import_project__symlink_in_folder__cli_zip_refuses(world: World, tmp_path: Path) -> None:
    folder, _ = await make_local_project(world)
    (folder / "link").symlink_to("/etc")

    with pytest.raises(cli_import.ImportCliError):
        zip_of(folder, tmp_path / "p.zip")


async def test__cli_import_project__dry_run_writes_nothing_then_real_run_imports(world: World, tmp_path: Path) -> None:
    folder, original_id = await make_local_project(world)

    dry = await cli_import.import_project(world.container, email="anna@example.test", source=folder, dry_run=True)  # type: ignore[arg-type]
    assert dry is None
    assert world.projects() == []

    real = await cli_import.import_project(world.container, email="anna@example.test", source=folder, dry_run=False)  # type: ignore[arg-type]
    assert real is not None
    assert real.project_id == original_id
    assert current_actor() is None


async def test__cli_import_project__unknown_user__usage_error(world: World) -> None:
    folder, _ = await make_local_project(world)

    with pytest.raises(cli_import.ImportCliError, match="не найден"):
        await cli_import.import_project(world.container, email="nobody@example.test", source=folder, dry_run=False)  # type: ignore[arg-type]


def local_data_dir(tmp_path: Path, *, providers: list[AIProvider] | None = None) -> Path:
    data = tmp_path / "local-data"
    data.mkdir()
    (data / "config.json").write_text(
        json.dumps({"interface_language": "en", "unknown_key": 1, "ollama_base_url": "x"}), encoding="utf-8"
    )
    items = [
        {
            "id": str(p.id),
            "name": p.name,
            "type": str(p.type),
            "api_key": p.api_key,
            "base_url": p.base_url,
            "models": list(p.models),
            "created_at": T0.isoformat(),
        }
        for p in providers or []
    ]
    (data / "ai_providers.json").write_text(json.dumps(items), encoding="utf-8")
    (data / "git").mkdir()
    (data / "git" / "credentials.json").write_text(json.dumps([{"id": "x"}]), encoding="utf-8")
    return data


def provider(name: str = "OpenAI") -> AIProvider:
    return AIProvider(
        id=uuid4(),
        name=name,
        type=AIProviderType.openai,
        api_key="sk-secret-123",
        base_url="",
        models=["gpt"],
        created_at=T0,
    )


async def stored(world: World, actor: Actor) -> tuple[dict[str, object], list[AIProvider]]:
    async with world.container() as request:  # type: ignore[operator]
        with as_actor(actor):
            current = await (await request.get(ISettingsRepository)).get()
            listed = await (await request.get(IAIProviderRepository)).list_all()
    return current, listed


async def test__cli_import_data__moves_providers_and_user_settings_and_is_idempotent(
    world: World, tmp_path: Path
) -> None:
    keep = provider()
    data = local_data_dir(tmp_path, providers=[keep])

    async def run(*, dry_run: bool) -> cli_import.ImportUserDataReport:
        return await cli_import.import_user_data(
            world.container,
            email="anna@example.test",
            data_dir=data,
            dry_run=dry_run,
            include_instance=False,  # type: ignore[arg-type]
        )

    dry = await run(dry_run=True)
    assert (dry.providers_created, dry.settings_created) == (1, 1)
    assert await stored(world, ANNA) == ({}, [])

    first = await run(dry_run=False)
    settings_after, providers_after = await stored(world, ANNA)
    assert (first.providers_created, first.providers_kept) == (1, 0)
    assert [p.id for p in providers_after] == [keep.id]
    assert providers_after[0].api_key == "sk-secret-123"
    assert settings_after["interface_language"] == "en"
    assert "unknown_key" not in settings_after

    second = await run(dry_run=False)
    assert (second.providers_created, second.providers_kept, second.settings_created) == (0, 1, 0)
    assert len((await stored(world, ANNA))[1]) == 1
    assert await stored(world, BORIS) == ({}, [])
    assert {n.subject for n in first.notes if n.code.value == "not_transferred"} == {"git_credentials"}


async def test__cli_import_data__unknown_user_or_dir__usage_error(world: World, tmp_path: Path) -> None:
    with pytest.raises(cli_import.ImportCliError, match="не найден"):
        await cli_import.import_user_data(
            world.container,
            email="nobody@example.test",
            data_dir=tmp_path,
            dry_run=True,
            include_instance=False,  # type: ignore[arg-type]
        )
    with pytest.raises(cli_import.ImportCliError, match="каталог"):
        await cli_import.import_user_data(
            world.container,
            email="anna@example.test",
            data_dir=tmp_path / "none",
            dry_run=True,
            include_instance=False,  # type: ignore[arg-type]
        )
