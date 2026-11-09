"""Опись вшитых паков и распознавание подменённого каталога шаблонов."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from hse_doc_studio.core.template_packs import PacksKind, TemplateKey
from hse_doc_studio.infra.template.packs_source import (
    FilesystemPacksSource,
    is_mounted_over,
    main,
    mount_points,
    read_manifest,
    write_manifest,
)
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository

from tests.fixtures.template_pack import PACK_ID, TEMPLATE_ID, V1, V2, build_update_pack

_MOUNTINFO = """\
1259 1 0:50 / / rw,relatime master:1 - overlay overlay rw
1550 1259 0:52 /Users/anna/hse-doc-studio/packs /app/packs ro,nosuid,nodev,relatime - fakeowner /run/host_mark/Users rw
1551 1259 0:52 /Users/anna/My\\040Data /data rw,relatime - fakeowner /run/host_mark/Users rw
"""


def _repo(packs_dir: Path) -> YamlTemplateRepository:
    repo = YamlTemplateRepository(packs_dir)
    repo.load()
    return repo


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    """Опись образа, в который вшиты обе версии шаблона."""
    builtin = tmp_path / "builtin"
    build_update_pack(builtin)
    out = tmp_path / "packs-manifest.json"
    write_manifest(builtin, out)
    return out


@pytest.fixture
def stale_dir(tmp_path: Path) -> Path:
    """Подключённый каталог, в котором ещё нет второй версии."""
    packs = tmp_path / "stale"
    template_dir = build_update_pack(packs)
    shutil.rmtree(template_dir / "versions" / V2)
    return packs


@pytest.mark.unit
def test__mount_points__reads_the_fifth_field_and_unescapes_spaces() -> None:
    assert mount_points(_MOUNTINFO) == ["/", "/app/packs", "/data"]


@pytest.mark.unit
def test__is_mounted_over__the_dir_itself_or_a_parent_but_not_root() -> None:
    points = mount_points(_MOUNTINFO)

    assert is_mounted_over("/app/packs", points)
    assert is_mounted_over("/data/packs", points)
    assert not is_mounted_over("/app/static", points)


@pytest.mark.unit
def test__write_manifest__lists_every_version(manifest: Path) -> None:
    data = json.loads(manifest.read_text(encoding="utf-8"))

    assert {(t["pack_id"], t["template_id"], t["version"]) for t in data["templates"]} == {
        (PACK_ID, TEMPLATE_ID, V1),
        (PACK_ID, TEMPLATE_ID, V2),
    }
    assert data["studio_version"]


@pytest.mark.unit
def test__read_manifest__missing_file__none(tmp_path: Path) -> None:
    assert read_manifest(tmp_path / "nope.json") is None
    assert read_manifest(None) is None


@pytest.mark.unit
def test__read_manifest__broken_file__none(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")

    assert read_manifest(broken) is None


@pytest.mark.unit
def test__source__dir_from_another_path__external_and_lagging(manifest: Path, stale_dir: Path, tmp_path: Path) -> None:
    source = FilesystemPacksSource(stale_dir, _repo(stale_dir), manifest, tmp_path / "no-mountinfo").describe()

    assert source.kind is PacksKind.external
    assert source.lags_for(TemplateKey(PACK_ID, TEMPLATE_ID, V2))
    assert not source.lags_for(TemplateKey(PACK_ID, TEMPLATE_ID, V1))
    assert source.missing_builtin == (TemplateKey(PACK_ID, TEMPLATE_ID, V2),)


@pytest.mark.unit
def test__source__mounted_over_the_builtin_path__external(tmp_path: Path) -> None:
    # Ровно случай оверлея compose.build.yml: путь тот же, что у вшитых паков, но поверх смонтирована папка хоста.
    packs = tmp_path / "packs"
    build_update_pack(packs)
    out = tmp_path / "packs-manifest.json"
    write_manifest(packs, out)
    mountinfo = tmp_path / "mountinfo"
    # Таблица монтирования бывает только на Linux, пути в ней всегда POSIX (и на Windows-раннере тестов тоже).
    mountinfo.write_text(
        f"1550 1259 0:52 /host/packs {packs.as_posix()} ro,relatime - fakeowner x rw\n", encoding="utf-8"
    )

    source = FilesystemPacksSource(packs, _repo(packs), out, mountinfo).describe()

    assert source.kind is PacksKind.external
    assert source.mounted
    assert source.missing_builtin == ()


@pytest.mark.unit
def test__source__builtin_dir__builtin(manifest: Path, tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"

    source = FilesystemPacksSource(builtin, _repo(builtin), manifest, tmp_path / "no-mountinfo").describe()

    assert source.kind is PacksKind.builtin
    assert not source.lags_for(TemplateKey(PACK_ID, TEMPLATE_ID, V2))


@pytest.mark.unit
def test__source__no_manifest__source_run(stale_dir: Path, tmp_path: Path) -> None:
    source = FilesystemPacksSource(stale_dir, _repo(stale_dir), None, tmp_path / "no-mountinfo").describe()

    assert source.kind is PacksKind.source
    assert not source.lags_for(TemplateKey(PACK_ID, TEMPLATE_ID, V2))


@pytest.mark.unit
def test__main__writes_the_manifest_of_the_repo_packs(tmp_path: Path) -> None:
    packs = Path(__file__).resolve().parents[6] / "packs"
    out = tmp_path / "packs-manifest.json"

    assert main([str(packs), str(out)]) == 0
    assert read_manifest(out) is not None


@pytest.mark.unit
def test__main__empty_packs_dir__fails(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    assert main([str(tmp_path / "empty"), str(tmp_path / "m.json")]) == 1
