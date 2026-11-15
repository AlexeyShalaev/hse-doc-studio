"""Источник каталога git (template-studio.md, 10.3): тег, ветка, sha, отказ по несуществующему ref, отслеживание.

Git настоящий, удалённый репозиторий локальный голый (`file://`), сеть не нужна. Сервис берётся из DI стенда
локального режима (тот же конвейер, что у админки сервера).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.pack_catalog.errors import CatalogError, CatalogErrorCode
from hse_doc_studio.core.pack_catalog.plan import Verdict
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.infra.pack_catalog.sources import JsonCatalogSourceRepository
from hse_doc_studio.use_cases.pack_catalog.service import PackCatalogService, SourceInput

from tests.fixtures.app import create_test_container
from tests.fixtures.git_remote import BareRemote, make_bare_remote, seed_remote
from tests.fixtures.pack_catalog import write_pack

pytestmark = pytest.mark.timeout(180)

LOCAL = Actor.local()


@dataclass
class Env:
    service: PackCatalogService
    templates: ITemplateRepository
    remote: BareRemote
    root: Path
    data_dir: Path

    def push(self, versions: tuple[str, ...], *, tag: str | None = None) -> str:
        stage = self.root / f"stage-{len(versions)}"
        write_pack(stage, released=versions)
        files: dict[str, str | bytes] = {
            f"packs/{p.relative_to(stage).as_posix()}": p.read_bytes() for p in stage.rglob("*") if p.is_file()
        }
        files["README.md"] = "репозиторий паков\n"
        sha = seed_remote(self.remote, files, message=f"packs {versions[-1]}")
        if tag:
            self.remote.git("tag", tag, sha)
        return sha


@pytest_asyncio.fixture
async def env(tmp_path: Path) -> AsyncIterator[Env]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    remote = make_bare_remote(tmp_path / "packs.git")
    remote.git("config", "uploadpack.allowFilter", "true")
    remote.git("config", "uploadpack.allowAnySHA1InWant", "true")
    container = create_test_container(data_dir)
    set_current_actor(LOCAL)
    try:
        yield Env(
            await container.get(PackCatalogService),
            await container.get(ITemplateRepository),
            remote,
            tmp_path,
            data_dir,
        )
    finally:
        await container.close()


def _verdicts(view) -> dict[str, Verdict]:  # type: ignore[no-untyped-def]
    return {v.version: v.verdict for p in view.plan.packs for v in p.versions}


async def test__git__tag_then_branch_then_sha(env: Env) -> None:
    first = env.push(("2026.1.0",), tag="v1")
    second = env.push(("2026.1.0", "2026.1.1"))

    source = await env.service.add_git(LOCAL, SourceInput(url=env.remote.url, ref="v1"))
    by_tag = await env.service.check(LOCAL, source.id)
    applied = await env.service.apply(LOCAL, source.id, by_tag.plan.revision)

    assert source.packs_path == "packs"
    assert by_tag.plan.revision == first
    assert _verdicts(by_tag) == {"2026.1.0": Verdict.new}
    assert applied.added == ("acme/report@2026.1.0",)
    assert env.templates.get_version("acme", "report", "2026.1.0") is not None
    assert env.templates.get_version("acme", "report", "2026.1.1") is None

    await env.service.update(LOCAL, source.id, SourceInput(ref="main"))
    by_branch = await env.service.check(LOCAL, source.id)
    assert by_branch.plan.revision == second
    assert _verdicts(by_branch) == {"2026.1.0": Verdict.present, "2026.1.1": Verdict.new}

    await env.service.update(LOCAL, source.id, SourceInput(ref=first))
    by_sha = await env.service.check(LOCAL, source.id)
    assert by_sha.plan.revision == first


async def test__git__unknown_ref_is_refused_and_recorded(env: Env) -> None:
    env.push(("2026.1.0",))
    source = await env.service.add_git(LOCAL, SourceInput(url=env.remote.url, ref="no-such-tag"))

    with pytest.raises(CatalogError) as exc:
        await env.service.check(LOCAL, source.id)

    stored = await env.service.source(LOCAL, source.id)
    history = await env.service.history(LOCAL, source.id)
    assert exc.value.code is CatalogErrorCode.ref_not_found
    assert stored.source.error is not None
    assert stored.source.error.code == "ref_not_found"
    assert [(e.action.value, e.ok) for e in history] == [("check", False), ("add", True)]


async def test__git__apply_without_check_or_after_move_is_refused(env: Env) -> None:
    env.push(("2026.1.0",))
    source = await env.service.add_git(LOCAL, SourceInput(url=env.remote.url))

    with pytest.raises(CatalogError) as unchecked:
        await env.service.apply(LOCAL, source.id, "0" * 40)
    view = await env.service.check(LOCAL, source.id)
    with pytest.raises(CatalogError) as moved:
        await env.service.apply(LOCAL, source.id, "f" * 40)

    assert unchecked.value.code is CatalogErrorCode.not_checked
    assert moved.value.code is CatalogErrorCode.revision_moved
    assert view.plan.ok


async def test__git__tracking_applies_new_released_versions(env: Env) -> None:
    env.push(("2026.1.0",))
    source = await env.service.add_git(LOCAL, SourceInput(url=env.remote.url, track=True))
    view = await env.service.check(LOCAL, source.id)
    await env.service.apply(LOCAL, source.id, view.plan.revision)
    env.push(("2026.1.0", "2026.1.1"))

    assert await env.service.track_due() == 0  # проверен меньше суток назад
    repo = JsonCatalogSourceRepository(env.data_dir / "packs-store")
    stale = await repo.get(source.id)
    assert stale is not None
    await repo.update(replace(stale, checked_at=datetime.now(UTC) - timedelta(days=2)))

    assert await env.service.track_due() == 1
    assert env.templates.get_version("acme", "report", "2026.1.1") is not None
    actions = [e.action.value for e in await env.service.history(LOCAL, source.id)]
    assert actions[:3] == ["track", "apply", "check"]


async def test__git__disable_and_remove_keep_versions_for_projects(env: Env) -> None:
    env.push(("2026.1.0",))
    source = await env.service.add_git(LOCAL, SourceInput(url=env.remote.url))
    view = await env.service.check(LOCAL, source.id)
    await env.service.apply(LOCAL, source.id, view.plan.revision)

    await env.service.set_enabled(LOCAL, source.id, False)
    hidden = next(p for p in env.templates.list_packs() if p.id == "acme")
    with pytest.raises(CatalogError) as off:
        await env.service.apply(LOCAL, source.id, view.plan.revision)
    await env.service.remove(LOCAL, source.id)
    overview = await env.service.overview(LOCAL)

    assert not hidden.listed
    assert off.value.code is CatalogErrorCode.source_disabled
    assert env.templates.get_version("acme", "report", "2026.1.0") is not None
    assert overview.sources == ()
    assert [p.id for p in overview.packs if p.origin_kind == "subscribed"] == ["acme"]
