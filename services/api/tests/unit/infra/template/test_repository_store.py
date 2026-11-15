"""Каталог шаблонов с несколькими корнями (срез T17): вшитые паки плюс хранилище, перезагрузка без рестарта."""

from __future__ import annotations

import shutil
from pathlib import Path

from hse_doc_studio.core.catalog import PackOriginKind
from hse_doc_studio.infra.pack_catalog.store import PacksStore
from hse_doc_studio.infra.project_init.template_renderer import version_files_dir
from hse_doc_studio.infra.template.packs_source import FilesystemPacksSource
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository

from tests.fixtures.pack_catalog import subscribe, write_pack


def _repo(tmp_path: Path, *, recheck_s: float = 0.0) -> tuple[YamlTemplateRepository, PacksStore, Path]:
    builtin = tmp_path / "builtin"
    write_pack(builtin, "core-pack", released=("2026.1.0",))
    store = PacksStore(tmp_path / "store")
    repo = YamlTemplateRepository(builtin, store=store, recheck_s=recheck_s)
    repo.load()
    return repo, store, builtin


def test__subscribed_pack__appears_with_origin_and_dir_in_the_store(tmp_path: Path) -> None:
    repo, store, _ = _repo(tmp_path)
    subscribe(store, write_pack(tmp_path / "src", released=("2026.1.0", "2026.1.1")))

    packs = {p.id: p for p in repo.list_packs()}
    version_dir = repo.version_dir("acme", "report", "2026.1.1")

    assert set(packs) == {"core-pack", "acme"}
    assert packs["acme"].origin.kind is PackOriginKind.subscribed
    assert packs["acme"].origin.source_id == "src-1"
    assert packs["core-pack"].origin.kind is PackOriginKind.builtin
    assert sorted(repo.list_versions("acme", "report")) == ["2026.1.0", "2026.1.1"]
    assert version_dir is not None
    assert version_dir.is_relative_to(store.root)
    assert repo.get_version("acme", "report", "2026.1.1") is not None
    assert repo.content_digest("acme", "report", "2026.1.1") == "sha256:" + version_dir.name.split("@")[1]
    assert repo.subscribed_keys() == {("acme", "report", "2026.1.0"), ("acme", "report", "2026.1.1")}
    assert repo.revision == 1


def test__another_process_applies__this_one_notices_the_new_revision(tmp_path: Path) -> None:
    repo, store, _ = _repo(tmp_path)
    assert repo.get_version("acme", "report", "2026.1.0") is None

    # Второй процесс: свой экземпляр каталога над тем же хранилищем.
    subscribe(store, write_pack(tmp_path / "src"))

    assert repo.get_version("acme", "report", "2026.1.0") is not None
    assert repo.revision == 1


def test__recheck_interval__catalog_is_not_reread_on_every_call(tmp_path: Path) -> None:
    repo, store, _ = _repo(tmp_path, recheck_s=3600.0)
    subscribe(store, write_pack(tmp_path / "src"))

    assert repo.get_version("acme", "report", "2026.1.0") is None
    assert repo.reload() == 1
    assert repo.get_version("acme", "report", "2026.1.0") is not None


def test__unlisted_pack__stays_for_projects_but_is_marked(tmp_path: Path) -> None:
    repo, store, _ = _repo(tmp_path)
    subscribe(store, write_pack(tmp_path / "src"), listed=False)

    pack = next(p for p in repo.list_packs() if p.id == "acme")

    assert not pack.listed
    assert repo.get_version("acme", "report", "2026.1.0") is not None


def test__replace_builtin__subscribed_meta_wins_and_builtin_only_versions_are_hidden(tmp_path: Path) -> None:
    repo, store, builtin = _repo(tmp_path)
    # Источник несёт тот же пак: вшитая 2026.1.0 байт в байт и своя 2026.1.1.
    src = tmp_path / "src"
    shutil.copytree(builtin / "core-pack", src / "core-pack")
    write_pack(src, "core-pack", released=("2026.1.0", "2026.1.1"), name="Новое имя")
    write_pack(builtin, "core-pack", released=("2026.1.0", "2025.9.0"))
    repo.load()

    subscribe(store, src / "core-pack", replaces_builtin=True)

    pack = next(p for p in repo.list_packs() if p.id == "core-pack")
    template = pack.templates[0]
    assert pack.name["ru"] == "Новое имя"
    assert pack.origin.replaces_builtin
    assert template.hidden_versions == {"2025.9.0"}
    assert repo.version_dir("core-pack", "report", "2026.1.1") is not None
    assert repo.version_dir("core-pack", "report", "2025.9.0").is_relative_to(builtin)  # type: ignore[union-attr]


def test__collision_without_replace__builtin_wins_and_store_versions_are_hidden(tmp_path: Path) -> None:
    repo, store, builtin = _repo(tmp_path)
    src = tmp_path / "src"
    write_pack(src, "core-pack", released=("2026.1.0", "2026.2.0"), body="другой")

    subscribe(store, src / "core-pack")

    pack = next(p for p in repo.list_packs() if p.id == "core-pack")
    assert pack.origin.kind is PackOriginKind.builtin
    assert pack.templates[0].hidden_versions == {"2026.2.0"}
    assert repo.version_dir("core-pack", "report", "2026.1.0").is_relative_to(builtin)  # type: ignore[union-attr]


def test__broken_store_entry__drops_only_that_version(tmp_path: Path) -> None:
    repo, store, _ = _repo(tmp_path)
    subscribe(store, write_pack(tmp_path / "src", released=("2026.1.0", "2026.1.1")))
    broken = repo.version_dir("acme", "report", "2026.1.0")
    assert broken is not None
    shutil.rmtree(broken)

    repo.reload()

    assert repo.get_version("acme", "report", "2026.1.0") is None
    assert repo.get_version("acme", "report", "2026.1.1") is not None


def test__template_renderer__finds_files_of_a_subscribed_version(tmp_path: Path) -> None:
    repo, store, _ = _repo(tmp_path)
    subscribe(store, write_pack(tmp_path / "src"))
    version = repo.get_version("acme", "report", "2026.1.0")
    assert version is not None

    files = version_files_dir(repo, version)

    assert files is not None
    assert (files / "report" / "main.tex").is_file()


def test__packs_source__lists_subscribed_versions_on_a_new_revision(tmp_path: Path) -> None:
    repo, store, builtin = _repo(tmp_path)
    source = FilesystemPacksSource(builtin, repo, manifest=None)
    assert not source.describe().subscribed

    subscribe(store, write_pack(tmp_path / "src"))

    described = source.describe()
    assert {(k.pack_id, k.version) for k in described.subscribed} == {("acme", "2026.1.0")}
    assert any(k.pack_id == "acme" for k in described.available)
