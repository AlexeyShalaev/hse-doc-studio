"""Две Студии и один удалённый репозиторий: общий каркас сквозных тестов Git-синхронизации.

Каждая Студия это отдельный контейнер DI со своим data_dir, своим профилем автора и своими папками проектов, то есть
отдельный «процесс», как у двух коллег. Общее у них только удалённый репозиторий (локальный голый, file://). Всё идёт
через настоящий API; напрямую в хранилище пишутся лишь правки с зафиксированными датами, когда от времени зависит
исход слияния (побеждает более поздний бинарный файл), и проверки результата.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hse_doc_studio.api.schemas.git_sync import (
    ConflictFileDetail,
    ConflictSessionResponse,
    GitErrorBody,
    GitStatusResponse,
    JsonFileDetail,
    OperationResponse,
    SyncResult,
    TextFileDetail,
)
from hse_doc_studio.core.vcs.protocols import IVcsEditThrottle
from hse_doc_studio.use_cases.template_update.recover_template_updates import RecoverTemplateUpdatesUC
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.git_remote import BareRemote, git_env, run_git
from tests.integration.api.vcs.conftest import TRACKED_FILE, create_project

ANNA = ("Анна Петрова", "a.petrova@edu.hse.ru")
BORIS = ("Борис Сидоров", "b.sidorov@edu.hse.ru")
PROJECT_FILE = ".hse-studio/project.json"
# Поля project.json, значения которых принадлежат машине, а не проекту: на перемотке они приезжают чужими.
MACHINE_FIELDS = ("pinned", "archived")
_DETAIL = TypeAdapter(ConflictFileDetail)
_POLL_S = 0.02
_WAIT_S = 60.0
_GIT_SECONDS = 60


def when(day: int, hour: int = 12) -> str:
    """Зафиксированная дата коммита: ход времени в тестах задаём мы, а не часы машины."""
    return f"2030-01-{day:02d}T{hour:02d}:00:00+00:00"


@dataclass
class Studio:
    """Одна Студия: свой контейнер, клиент, профиль и (после создания или клонирования) один проект."""

    name: str
    root: Path
    profile: tuple[str, str]
    container: Any = None
    client: AsyncClient = field(default=None)  # type: ignore[assignment]
    project: dict[str, Any] = field(default_factory=dict)
    # Сколько раз синхронизация этой Студии останавливалась на конфликтах (считает `sync_deciding`).
    stopped_on_conflicts: int = 0

    @classmethod
    async def open(cls, root: Path, name: str, profile: tuple[str, str]) -> Studio:
        studio = cls(name, root, profile)
        (root / "data").mkdir(parents=True, exist_ok=True)
        await studio._start()
        resp = await studio.client.put("/api/v1/profile", json={"name": profile[0], "email": profile[1]})
        assert resp.status_code == 200, resp.text
        return studio

    async def _start(self) -> None:
        self.container = create_test_container(self.root / "data")
        self.client = AsyncClient(transport=ASGITransport(app=create_test_app(self.container)), base_url="http://test")
        # Каждое сохранение файла даёт свой коммит правки: часы, по которым редактор прореживает снимки, выключены.
        throttle = await self.container.get(IVcsEditThrottle)
        throttle._min = 0.0  # noqa: SLF001

    async def close(self) -> None:
        await self.client.aclose()
        await self.container.close()

    async def restart(self) -> None:
        """Процесс умер и поднялся заново на тех же данных; журналы, оставшиеся после смерти, разбирает запуск."""
        await self.close()
        await self._start()

    async def recover(self) -> Any:
        """То, что Студия делает при старте: разобрать прерванные журналы применения."""
        async with self.container() as request:
            return await (await request.get(RecoverTemplateUpdatesUC)).execute()

    async def get[T](self, kind: type[T]) -> T:
        return await self.container.get(kind)  # type: ignore[no-any-return]

    # --- проект и файлы ------------------------------------------------------------------------------------------

    @property
    def id(self) -> str:
        return str(self.project["id"])

    @property
    def folder(self) -> Path:
        return Path(self.project["folder"])

    @property
    def store(self) -> Path:
        return self.folder / ".hse-studio" / "git"

    def file(self, rel: str) -> Path:
        return self.folder / rel

    def read(self, rel: str) -> str:
        return self.file(rel).read_text(encoding="utf-8")

    def write(self, rel: str, content: str | bytes) -> None:
        """Правка на диске в обход API: так появляются бинарные файлы и поля, которые пишет сборка."""
        target = self.file(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())

    async def put(self, rel: str, text: str) -> None:
        """Правка через API, как сохраняет редактор: файл на диске и коммит правки от имени автора профиля."""
        resp = await self.client.put(f"/api/v1/projects/{self.id}/files/{rel}", content=text.encode())
        assert resp.status_code in (200, 204), resp.text

    def project_json(self) -> dict[str, Any]:
        return json.loads(self.read(PROJECT_FILE))  # type: ignore[no-any-return]

    def write_project_json(self, data: dict[str, Any]) -> None:
        self.write(PROJECT_FILE, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def git(self, *args: str, check: bool = True) -> str:
        return run_git(*args, git_dir=self.store, work_tree=self.folder, check=check)

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def commit_count(self) -> int:
        return int(self.git("rev-list", "--count", "HEAD"))

    def commit_dated(self, message: str, at: str) -> str:
        """Закоммитить всё как есть от имени этой Студии с зафиксированной датой."""
        env = git_env(
            {
                "GIT_AUTHOR_NAME": self.profile[0],
                "GIT_AUTHOR_EMAIL": self.profile[1],
                "GIT_COMMITTER_NAME": self.profile[0],
                "GIT_COMMITTER_EMAIL": self.profile[1],
                "GIT_AUTHOR_DATE": at,
                "GIT_COMMITTER_DATE": at,
            }
        )
        base = ["git", "--git-dir", str(self.store), "--work-tree", str(self.folder)]
        for tail in (["add", "-A"], ["commit", "--quiet", "-m", message]):
            done = subprocess.run(  # noqa: S603 — аргументы собирает тест
                [*base, *tail], env=env, capture_output=True, text=True, check=False, timeout=_GIT_SECONDS
            )
            assert done.returncode == 0, done.stderr
        return self.head()

    def tracked(self) -> list[str]:
        return self.git("ls-tree", "-r", "--name-only", "HEAD").splitlines()

    def blob(self, rel: str, rev: str = "HEAD") -> bytes:
        done = subprocess.run(  # noqa: S603
            ["git", "--git-dir", str(self.store), "cat-file", "blob", f"{rev}:{rel}"],  # noqa: S607
            env=git_env(),
            capture_output=True,
            check=True,
            timeout=_GIT_SECONDS,
        )
        return done.stdout

    def tracked_content(self) -> dict[str, bytes]:
        """Содержимое дерева HEAD; в project.json убраны поля машины, чтобы сравнивать проекты, а не компьютеры."""
        content = {rel: self.blob(rel) for rel in self.tracked()}
        content[PROJECT_FILE] = _without_machine_fields(content[PROJECT_FILE])
        return content

    def dirty(self) -> str:
        """Незакоммиченное в рабочей папке; PDF вне истории по умолчанию, поэтому исключены."""
        return self.git("status", "--porcelain", "--", ".", ":(exclude)*.pdf")

    # --- проект: создание, подключение, клонирование -------------------------------------------------------------

    async def create_project(self, folder: Path | None = None) -> dict[str, Any]:
        self.project = await create_project(self.client, folder or self.root / "work" / "thesis")
        return self.project

    async def connect(self, remote: BareRemote) -> GitStatusResponse:
        resp = await self.client.put(
            f"/api/v1/projects/{self.id}/git/remote", json={"url": remote.url, "credential_id": None}
        )
        assert resp.status_code == 200, resp.text
        return GitStatusResponse.model_validate(resp.json())

    async def clone(self, remote: BareRemote, folder: Path | None = None) -> OperationResponse:
        folder = folder or self.root / "work" / "thesis"
        resp = await self.client.post("/api/v1/git/clone", json={"url": remote.url, "folder": str(folder)})
        assert resp.status_code == 202, resp.text
        operation = await self.wait(resp.json()["operation_id"])
        assert operation.status == "succeeded", operation.error
        assert operation.result is not None
        result = operation.result
        shown = await self.client.get(f"/api/v1/projects/{result.project_id}")  # type: ignore[union-attr]
        assert shown.status_code == 200, shown.text
        self.project = shown.json()
        return operation

    async def history(self, **params: Any) -> list[dict[str, Any]]:
        resp = await self.client.get(f"/api/v1/projects/{self.id}/vcs/history", params={"limit": 500, **params})
        assert resp.status_code == 200, resp.text
        return resp.json()  # type: ignore[no-any-return]

    # --- синхронизация -------------------------------------------------------------------------------------------

    def url(self, tail: str) -> str:
        return f"/api/v1/projects/{self.id}/git/{tail}"

    async def status(self) -> GitStatusResponse:
        resp = await self.client.get(f"/api/v1/projects/{self.id}/git")
        assert resp.status_code == 200, resp.text
        return GitStatusResponse.model_validate(resp.json())

    async def wait(self, operation_id: str, *, timeout: float = _WAIT_S) -> OperationResponse:
        async with asyncio.timeout(timeout):
            while True:
                resp = await self.client.get(f"/api/v1/git/operations/{operation_id}")
                assert resp.status_code == 200, resp.text
                operation = OperationResponse.model_validate(resp.json())
                if operation.status != "running":
                    return operation
                await asyncio.sleep(_POLL_S)

    async def start_sync(self) -> Any:
        return await self.client.post(self.url("sync"), json={})

    async def sync(self) -> OperationResponse:
        started = await self.start_sync()
        assert started.status_code == 202, started.text
        return await self.wait(started.json()["operation_id"])

    async def sync_ok(self) -> SyncResult:
        operation = await self.sync()
        assert operation.status == "succeeded", operation.error
        assert isinstance(operation.result, SyncResult)
        return operation.result

    async def session(self) -> ConflictSessionResponse:
        resp = await self.client.get(self.url("conflicts"))
        assert resp.status_code == 200, resp.text
        return ConflictSessionResponse.model_validate(resp.json())

    async def conflict_detail(self, path: str) -> Any:
        resp = await self.client.get(self.url("conflicts/file"), params={"path": path})
        assert resp.status_code == 200, resp.text
        return _DETAIL.validate_python(resp.json())

    async def resolve_all(self, prefer: str, overrides: Mapping[str, str] | None = None) -> SyncResult:
        """Решить каждый конфликт открытой сессии в пользу одной стороны (`mine` или `theirs`) и отправить.

        `overrides` задаёт сторону для отдельных файлов, остальные решаются по `prefer`.
        """
        session = await self.session()
        resolutions: dict[str, Any] = {}
        for item in session.files:
            if item.action != "conflict":
                continue
            side = (overrides or {}).get(item.path, prefer)
            detail = await self.conflict_detail(item.path)
            if isinstance(detail, TextFileDetail):
                hunks = {seg.key: {"choice": side} for seg in detail.segments if seg.type == "hunk"}
                resolutions[item.path] = {"kind": "hunks", "hunks": hunks}
            elif isinstance(detail, JsonFileDetail):
                fields = {f.pointer: {"choice": side} for f in detail.fields if f.status == "conflict"}
                resolutions[item.path] = {"kind": "fields", "fields": fields}
            else:
                resolutions[item.path] = {"kind": "file", "choice": side}
        resp = await self.client.post(
            self.url("conflicts/resolve"),
            json={"fingerprint": session.fingerprint, "resolutions": resolutions, "push": True},
        )
        assert resp.status_code == 202, resp.text
        operation = await self.wait(resp.json()["operation_id"])
        assert operation.status == "succeeded", operation.error
        assert isinstance(operation.result, SyncResult)
        return operation.result

    async def sync_deciding(self, prefer: str) -> SyncResult:
        """Синхронизация, в которой конфликты решаются в пользу `prefer`; итог последнего шага."""
        result = await self.sync_ok()
        if result.outcome == "conflicts":
            self.stopped_on_conflicts += 1
            result = await self.resolve_all(prefer)
        return result


async def share_project(owner: Studio, colleague: Studio, remote: BareRemote) -> None:
    """Владелец создаёт проект, подключает пустой репозиторий и отправляет; коллега клонирует его к себе."""
    await owner.create_project()
    await owner.connect(remote)
    result = await owner.sync_ok()
    assert result.outcome == "pushed"
    await colleague.clone(remote)
    assert colleague.id == owner.id
    assert colleague.head() == owner.head() == remote.head()


def with_line(text: str, number: int, new: str) -> str:
    """Текст с заменённой строкой `number` (с единицы)."""
    lines = text.splitlines(keepends=True)
    lines[number - 1] = new + "\n"
    return "".join(lines)


def error_body(resp: Any) -> GitErrorBody:
    return GitErrorBody.model_validate(resp.json())


def _without_machine_fields(raw: bytes) -> bytes:
    data = json.loads(raw)
    for key in MACHINE_FIELDS:
        data.pop(key, None)
    for doc in data.get("documents", []):
        doc.pop("last_compile_id", None)
    (data.get("meta") or {}).pop("vcs", None)
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1).encode()


async def converge(studios: list[Studio], prefer_of: Callable[[Studio], str], *, rounds: int = 5) -> None:
    """Прогнать синхронизации по кругу, пока все Студии не придут к одной вершине и не затихнут."""
    for _ in range(rounds):
        for studio in studios:
            await studio.sync_deciding(prefer_of(studio))
        heads = {studio.head() for studio in studios}
        if len(heads) == 1:
            quiet = [(await studio.sync_ok()).outcome == "up_to_date" for studio in studios]
            if all(quiet):
                return
    raise AssertionError(f"Студии не сошлись за {rounds} кругов: {[s.head() for s in studios]}")


__all__ = [
    "ANNA",
    "BORIS",
    "PROJECT_FILE",
    "TRACKED_FILE",
    "Studio",
    "converge",
    "error_body",
    "share_project",
    "when",
    "with_line",
]
