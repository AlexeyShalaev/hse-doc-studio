"""Результат версии из git пространства: `work_tree`, `head` и `base` (template-studio-outcome.md, 4.2, срез O2).

Репозиторий паков это голый репозиторий по file:// или https с токеном; клон частичный (без блобов) и разреженный, как
у пространства на сервере и у официальных паков (папка паков внутри большого репозитория). Версии настоящие (ВКР
`hse-cs-se` 2026.1.2, курсовой проект `hse-cs-sse` 2026.1.6) и черновик ВКР, который можно править. `head` и `base`
читаются из хранилища без checkout; недостающие блобы догружаются сетью с доступом пространства.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.pack_studio.protocols import IPackWorkspaceRepository

from tests.fixtures.git_remote import BareRemote, GitHttpServer, make_bare_remote, run_git, seed_remote
from tests.fixtures.tls import make_ca_signed

from .conftest import API, Stand
from .outcome_support import (
    COURSEWORK,
    DRAFT_MANIFEST,
    DRAFT_VKR,
    LANGS,
    REAL_VERSIONS,
    VKR,
    draft_vkr_files,
    edit_manifest,
    get_inputs,
    parse_inputs,
    parse_outcome,
    post_outcome,
    real_files,
)
from .test_git_studio_layout import _drop_pack_with
from .test_git_workspace import _git_workspace, _store

_PROFILE = {"name": "Анна Иванова", "email": "anna@example.org"}
_VKR_MANIFEST = "hse-cs-se/templates/vkr/versions/2026.1.2/version.yaml"
_NEW = ("hse-cs-se", "vkr", "2026.1.10")
_NEW_MANIFEST = "hse-cs-se/templates/vkr/versions/2026.1.10/version.yaml"


def _packs_remote(root: Path) -> BareRemote:
    """Репозиторий как официальный: паки в `packs/`, рядом остальной репозиторий, которого пространству не нужно."""
    remote = make_bare_remote(root / "packs.git")
    remote.git("config", "uploadpack.allowFilter", "true")
    payload: dict[str, str | bytes] = {f"packs/{p}": d for p, d in {**real_files(), **draft_vkr_files()}.items()}
    payload["README.md"] = "Репозиторий паков\n"
    payload["services/api/big.txt"] = "x" * 10_000
    seed_remote(remote, payload)
    return remote


async def _ready(stand: Stand) -> tuple[BareRemote, str]:
    remote = _packs_remote(stand.root)
    resp = await stand.client.put("/api/v1/profile", json=_PROFILE)
    assert resp.status_code == 200, resp.text
    ws = await _git_workspace(stand, remote)
    assert ws["state"] == "ready", ws
    return remote, str(ws["id"])


async def _lang_values(stand: Stand, ws: str, ref: tuple[str, str, str], state: str) -> list[str]:
    inputs = parse_inputs(await get_inputs(stand, ws, ref, state))
    return [v.value for v in next(i for i in inputs.inputs if i.id == "lang").values]


# ── три состояния ────────────────────────────────────────────────────────────


async def test__fresh_clone__all_three_states_answer_the_same_result_with_their_own_etag(stand: Stand) -> None:
    _, ws = await _ready(stand)

    for ref in REAL_VERSIONS:
        answers = {
            state: await post_outcome(stand, ws, ref, {"state": state}) for state in ("work_tree", "head", "base")
        }
        parsed = {state: parse_outcome(resp) for state, resp in answers.items()}

        assert {state: out.state for state, out in parsed.items()} == {s: s for s in answers}
        assert len({out.fingerprint for out in parsed.values()}) == 1
        assert len({out.revision for out in parsed.values()}) == 1
        assert len({resp.headers["ETag"] for resp in answers.values()}) == 3
        # Тела равны с точностью до состояния и времени ответа.
        bodies = [{k: v for k, v in r.json().items() if k not in {"state", "elapsed_ms"}} for r in answers.values()]
        assert bodies[0] == bodies[1] == bodies[2]


async def test__fresh_clone__inputs_in_all_three_states(stand: Stand) -> None:
    _, ws = await _ready(stand)

    for state in ("work_tree", "head", "base"):
        resp = await get_inputs(stand, ws, VKR, state)
        out = parse_inputs(resp)
        assert out.state == state
        assert len(out.inputs) >= 10
    # Состояние выбирает источник: ETag словаря у каждого свой.
    etags = {(await get_inputs(stand, ws, VKR, s)).headers["ETag"] for s in ("work_tree", "head", "base")}
    assert len(etags) == 3


async def test__unsaved_edit__changes_work_tree_only__head_and_base_stay(stand: Stand) -> None:
    _, ws = await _ready(stand)
    assert await _lang_values(stand, ws, DRAFT_VKR, "work_tree") == ["ru", "en"]

    await edit_manifest(stand, ws, LANGS, "langs: [ru]")

    assert await _lang_values(stand, ws, DRAFT_VKR, "work_tree") == ["ru"]
    assert await _lang_values(stand, ws, DRAFT_VKR, "head") == ["ru", "en"]
    assert await _lang_values(stand, ws, DRAFT_VKR, "base") == ["ru", "en"]
    work = await post_outcome(stand, ws, DRAFT_VKR, {"inputs": {"lang": "en"}})
    head = await post_outcome(stand, ws, DRAFT_VKR, {"state": "head", "inputs": {"lang": "en"}})
    base = await post_outcome(stand, ws, DRAFT_VKR, {"state": "base", "inputs": {"lang": "en"}})
    assert (work.status_code, head.status_code, base.status_code) == (400, 200, 200)
    assert work.json()["code"] == "inputs_invalid"


async def test__commit__moves_head_but_not_base(stand: Stand) -> None:
    _, ws = await _ready(stand)
    await edit_manifest(stand, ws, LANGS, "langs: [ru]")
    before_head = parse_outcome(await post_outcome(stand, ws, DRAFT_VKR, {"state": "head"}))

    committed = await stand.client.post(f"{API}/workspaces/{ws}/git/commit", json={})

    assert committed.status_code == 200, committed.text
    assert committed.json()["committed"] is True
    assert await _lang_values(stand, ws, DRAFT_VKR, "head") == ["ru"]
    assert await _lang_values(stand, ws, DRAFT_VKR, "base") == ["ru", "en"]
    after_head = parse_outcome(await post_outcome(stand, ws, DRAFT_VKR, {"state": "head"}))
    assert after_head.revision != before_head.revision
    # `work_tree` теперь равен `head`: правок после коммита нет.
    assert await _lang_values(stand, ws, DRAFT_VKR, "work_tree") == ["ru"]


async def test__base_moved_on_the_server__refresh_moves_base_and_keeps_head(stand: Stand) -> None:
    remote, ws = await _ready(stand)
    before = await post_outcome(stand, ws, DRAFT_VKR, {"state": "base"})
    manifest = draft_vkr_files()[f"{DRAFT_MANIFEST}"].replace(LANGS.encode(), b"langs: [ru]")
    seed_remote(remote, {f"packs/{DRAFT_MANIFEST}": manifest}, message="base moved")
    refreshed = await stand.client.post(f"{API}/workspaces/{ws}/refresh")
    assert refreshed.status_code == 202, refreshed.text
    assert (await stand.settled(ws))["base_sha"] == remote.head("main")

    after = await post_outcome(stand, ws, DRAFT_VKR, {"state": "base"})

    assert before.status_code == 200
    assert after.status_code == 200
    assert after.headers["ETag"] != before.headers["ETag"]
    assert await _lang_values(stand, ws, DRAFT_VKR, "base") == ["ru"]
    assert await _lang_values(stand, ws, DRAFT_VKR, "head") == ["ru", "en"]


async def test__new_version__has_no_head_and_base_until_it_is_committed_and_proposed(stand: Stand) -> None:
    _, ws = await _ready(stand)
    manifest = stand.file_url(ws, _NEW_MANIFEST)
    created = await stand.client.put(manifest, content=b'id: "2026.1.10"\nstatus: beta\nlangs: [ru]\n')
    assert created.status_code == 200, created.text

    work = await post_outcome(stand, ws, _NEW, {"state": "work_tree"})
    head = await post_outcome(stand, ws, _NEW, {"state": "head"})
    base = await post_outcome(stand, ws, _NEW, {"state": "base"})
    inputs_base = await get_inputs(stand, ws, _NEW, "base")

    assert work.status_code == 200, work.text
    for resp in (head, base, inputs_base):
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "diff_base_unavailable"
        assert resp.json()["reason"] == "new_version"
    committed = await stand.client.post(f"{API}/workspaces/{ws}/git/commit", json={})
    assert committed.status_code == 200, committed.text
    assert (await post_outcome(stand, ws, _NEW, {"state": "head"})).status_code == 200
    assert (await post_outcome(stand, ws, _NEW, {"state": "base"})).json()["reason"] == "new_version"


async def test__workspace_without_a_base_branch__base_is_unavailable_but_head_works(stand: Stand) -> None:
    _, ws = await _ready(stand)
    assert stand.container is not None
    repo = await stand.container.get(IPackWorkspaceRepository)
    found = await repo.get(UUID(ws), None)
    assert found is not None
    await repo.update(replace(found, base_branch=None))

    base = await post_outcome(stand, ws, VKR, {"state": "base"})
    head = await post_outcome(stand, ws, VKR, {"state": "head"})

    assert (base.status_code, base.json()["reason"]) == (409, "no_base")
    assert head.status_code == 200


async def test__head_and_base_reads_are_stable_between_requests_and_cached_by_commit(stand: Stand) -> None:
    _, ws = await _ready(stand)
    first = await post_outcome(stand, ws, VKR, {"state": "head"})
    again = await post_outcome(stand, ws, VKR, {"state": "head"}, **{"If-None-Match": first.headers["ETag"]})

    assert first.status_code == 200
    assert again.status_code == 304


# ── частичный клон: блобов нет, догружаются ─────────────────────────────────


async def test__partial_clone__head_and_base_blobs_missing__fetched_by_the_workspace_access(stand: Stand) -> None:
    _, ws = await _ready(stand)
    spec = f"HEAD:packs/{_VKR_MANIFEST}"
    git_dir = _store(stand, ws) / "git"
    _drop_pack_with(stand, ws, spec)
    missing = run_git("rev-list", "--objects", "--missing=print", "--no-walk", "HEAD", git_dir=git_dir)
    blob = run_git("rev-parse", spec, git_dir=git_dir)
    assert f"?{blob}" in missing.splitlines()

    head = await post_outcome(stand, ws, VKR, {"state": "head"})
    base = await post_outcome(stand, ws, VKR, {"state": "base"})
    dictionary = await get_inputs(stand, ws, VKR, "head")

    assert head.status_code == 200, head.text
    assert base.status_code == 200, base.text
    assert dictionary.status_code == 200, dictionary.text
    parse_outcome(head)
    # Недостающие блобы версии догружены: теперь они есть.
    after = run_git("rev-list", "--objects", "--missing=print", "--no-walk", "HEAD", git_dir=git_dir)
    assert f"?{blob}" not in after.splitlines()
    # Остального репозитория (вне папки паков и версий) никто не скачивал.
    assert any(line.startswith("?") for line in after.splitlines())


async def test__https_with_token__head_and_base_after_the_blobs_are_gone(
    stand: Stand, http_git_server_factory: Callable[..., GitHttpServer], tmp_path: Path
) -> None:
    """Через https с токеном: локальный git в сеть не ходит, догрузка идёт запускателем; токен нигде не оседает."""
    tls = make_ca_signed(tmp_path / "tls")
    server = http_git_server_factory(tls=tls)
    bare = server.create_repo("acme/packs.git")
    bare.git("config", "uploadpack.allowFilter", "true")
    seed = _packs_remote(stand.root / "seed")
    run_git("push", "--quiet", bare.url, "refs/heads/main:refs/heads/main", git_dir=seed.path)
    await stand.enable()
    trust = await stand.client.put(
        "/api/v1/git/host-settings", json={"host": "127.0.0.1", "port": server.port, "ca_pem": tls.ca_pem}
    )
    assert trust.status_code == 200, trust.text
    credential = await stand.client.post(
        "/api/v1/git/credentials", json={"kind": "pat", "label": "Токен", "host": "127.0.0.1", "token": server.token}
    )
    assert credential.status_code == 201, credential.text
    created = await stand.client.post(
        f"{API}/workspaces",
        json={"kind": "git", "url": server.url("acme/packs.git"), "credential_id": credential.json()["id"]},
    )
    assert created.status_code == 202, created.text
    ws_state = await stand.settled(created.json()["id"])
    assert ws_state["state"] == "ready", ws_state
    ws = str(ws_state["id"])
    _drop_pack_with(stand, ws, f"HEAD:packs/{_VKR_MANIFEST}")

    head = await post_outcome(stand, ws, VKR, {"state": "head"})
    base = await post_outcome(stand, ws, COURSEWORK, {"state": "base"})

    assert head.status_code == 200, head.text
    assert base.status_code == 200, base.text
    token = str(server.token)
    assert token not in head.text
    assert token not in base.text
    store = _store(stand, ws)
    assert [p for p in store.rglob("*") if p.is_file() and token.encode() in p.read_bytes()] == []


# ── безопасность чтения ──────────────────────────────────────────────────────


async def test__symlink_in_a_commit__is_not_read_as_a_file_of_the_version(stand: Stand) -> None:
    """Ссылка в дереве коммита не читается как файл версии: в хранилище это блоб с путём, а не файл."""
    remote, ws = await _ready(stand)
    seed_remote(remote, {"packs/hse-cs-se/templates/vkr/versions/2026.1.9/files/notes.txt": "plain\n"}, message="x")
    work = remote.path.parent / "link.seed"
    run_git("clone", "--quiet", remote.url, str(work))
    link = work / "packs/hse-cs-se/templates/vkr/versions/2026.1.9/files/evil"
    link.symlink_to("/etc/passwd")
    run_git("add", "-A", cwd=work)
    run_git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "--quiet", "-m", "link", cwd=work)
    run_git("push", "--quiet", "origin", "HEAD:main", cwd=work)
    refreshed = await stand.client.post(f"{API}/workspaces/{ws}/refresh")
    assert refreshed.status_code == 202, refreshed.text
    await stand.settled(ws)

    base = await post_outcome(stand, ws, DRAFT_VKR, {"state": "base"})

    assert base.status_code == 200, base.text
    assert "root:" not in base.text


async def test__timing_of_head_and_base_reads_on_real_versions(stand: Stand) -> None:
    """Не предел, а след: первый ответ по `head` и `base` (чтение из git, разбор) и повторный из кэша."""
    _, ws = await _ready(stand)
    measured: dict[str, float] = {}
    for state in ("head", "base"):
        for label, ref in (("vkr", VKR), ("coursework", COURSEWORK)):
            for attempt in ("cold", "cached"):
                started = time.perf_counter()
                resp = await post_outcome(stand, ws, ref, {"state": state, "inputs": {"lang": "ru"}})
                measured[f"{state}/{label}/{attempt}"] = (time.perf_counter() - started) * 1000
                assert resp.status_code == 200, resp.text
    print({k: round(v, 1) for k, v in measured.items()})  # noqa: T201 — след для описания PR
    assert all(ms < 20_000 for ms in measured.values())
