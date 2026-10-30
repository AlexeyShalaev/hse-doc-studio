"""Приём zip из локальной Студии: что принимается и что отвергается целиком до записи на том."""

from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.projects.importer import ImportLimits, ProjectImportCode, ProjectImportError
from hse_doc_studio.infra.projects.archive import ZipProjectArchive
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume

LIMITS = ImportLimits(max_unpacked_bytes=10 * 1024 * 1024, max_files=100)
PROJECT_ID = uuid4()


def project_json(**extra: object) -> str:
    base = {
        "id": str(PROJECT_ID),
        "name": "Курсовая",
        "lock": {"pack_id": "p", "template_id": "t", "version": "1", "engine": "xelatex"},
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    return json.dumps({**base, **extra})


def make_zip(path: Path, entries: dict[str, str | bytes], *, prefix: str = "") -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{prefix}.hse-studio/project.json", project_json())
        for name, data in entries.items():
            zf.writestr(f"{prefix}{name}", data)
    return path


def refused(archive: Path, code: ProjectImportCode, limits: ImportLimits = LIMITS) -> ProjectImportError:
    with pytest.raises(ProjectImportError) as caught:
        ZipProjectArchive().inspect(archive, limits)
    assert caught.value.code is code
    return caught.value


@pytest.fixture
def archive_path(tmp_path: Path) -> Path:
    return tmp_path / "in.zip"


def test__inspect__plain_project__reads_manifest(archive_path: Path) -> None:
    make_zip(archive_path, {"main.tex": "x", "img/a.png": b"\x89PNG"})

    manifest = ZipProjectArchive().inspect(archive_path, LIMITS)

    assert (manifest.project_id, manifest.name, manifest.prefix) == (PROJECT_ID, "Курсовая", "")
    assert manifest.files == 3
    assert (manifest.junk, manifest.records, manifest.has_remote) == (0, 0, False)


def test__inspect__single_top_folder__is_stripped(archive_path: Path) -> None:
    make_zip(archive_path, {"main.tex": "x"}, prefix="my-thesis/")

    manifest = ZipProjectArchive().inspect(archive_path, LIMITS)

    assert manifest.prefix == "my-thesis/"


def test__inspect__junk_and_records__counted_not_kept(archive_path: Path) -> None:
    make_zip(
        archive_path,
        {
            ".DS_Store": "x",
            "__MACOSX/._main.tex": "x",
            ".hse-studio/compiles/a/record.json": "{}",
            ".hse-studio/submissions/s.json": "{}",
            ".hse-studio/git/hooks/pre-commit": "#!/bin/sh",
            ".hse-studio/git/config": '[remote "origin"]\n\turl = https://example.test/r.git\n',
            "main.tex": "x",
        },
    )

    manifest = ZipProjectArchive().inspect(archive_path, LIMITS)

    assert (manifest.junk, manifest.records, manifest.has_remote) == (2, 2, True)
    # project.json, git/config и main.tex: хуки, записи и мусор на том не едут
    assert manifest.files == 3


@pytest.mark.parametrize(
    "name",
    [
        "../evil.tex",
        "a/../../evil.tex",
        "/etc/passwd",
        "C:/Windows/evil.tex",
        "a\\b.tex",
        "a//b.tex",
        "./x.tex",
    ],
)
def test__inspect__unsafe_path__whole_archive_refused(archive_path: Path, name: str) -> None:
    make_zip(archive_path, {"main.tex": "ok", name: "x"})

    refused(archive_path, ProjectImportCode.archive_unsafe)


def test__inspect__symlink_member__refused(archive_path: Path) -> None:
    make_zip(archive_path, {"main.tex": "ok"})
    with zipfile.ZipFile(archive_path, "a") as zf:
        link = zipfile.ZipInfo("link.tex")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, "/etc/passwd")

    refused(archive_path, ProjectImportCode.archive_unsafe)


def test__inspect__device_member__refused(archive_path: Path) -> None:
    make_zip(archive_path, {"main.tex": "ok"})
    with zipfile.ZipFile(archive_path, "a") as zf:
        node = zipfile.ZipInfo("dev")
        node.external_attr = (stat.S_IFCHR | 0o666) << 16
        zf.writestr(node, "")

    refused(archive_path, ProjectImportCode.archive_unsafe)


def test__inspect__duplicate_names_differing_in_case__refused(archive_path: Path) -> None:
    make_zip(archive_path, {"Main.tex": "a", "main.tex": "b"})

    refused(archive_path, ProjectImportCode.archive_unsafe)


def test__inspect__encrypted_member__refused(archive_path: Path) -> None:
    make_zip(archive_path, {"main.tex": "ok"})
    raw = bytearray(archive_path.read_bytes())
    # флаг шифрования в центральном каталоге у каждой записи
    marker = b"PK\x01\x02"
    at = 0
    while (at := raw.find(marker, at)) != -1:
        raw[at + 8] |= 0x01
        at += 4
    archive_path.write_bytes(bytes(raw))

    refused(archive_path, ProjectImportCode.archive_unsafe)


def test__inspect__not_a_zip__invalid(archive_path: Path) -> None:
    archive_path.write_bytes(b"this is not a zip")

    refused(archive_path, ProjectImportCode.archive_invalid)


def test__inspect__no_project_json__no_project(archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("main.tex", "x")

    refused(archive_path, ProjectImportCode.no_project)


def test__inspect__project_json_not_object__no_project(archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr(".hse-studio/project.json", "[1, 2]")

    refused(archive_path, ProjectImportCode.no_project)


def test__inspect__project_in_two_top_folders__no_project(archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("a/.hse-studio/project.json", project_json())
        zf.writestr("b/readme.txt", "x")

    refused(archive_path, ProjectImportCode.no_project)


def test__inspect__newer_schema__refused(archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "w") as zf:
        schema = {"version": 99, "read_compat": 1, "write_compat": 99, "written_by": "9.9.9"}
        zf.writestr(".hse-studio/project.json", project_json(schema=schema))

    error = refused(archive_path, ProjectImportCode.project_newer)

    assert "9.9.9" in error.message


def test__inspect__declared_size_over_limit__too_large(archive_path: Path) -> None:
    make_zip(archive_path, {"big.bin": b"0" * 4096})

    refused(archive_path, ProjectImportCode.too_large, ImportLimits(max_unpacked_bytes=1024))


def test__inspect__too_many_files__too_large(archive_path: Path) -> None:
    make_zip(archive_path, {f"f{i}.tex": "x" for i in range(10)})

    refused(archive_path, ProjectImportCode.too_large, ImportLimits(max_unpacked_bytes=10**6, max_files=5))


def test__extract__lying_header__stops_at_declared_size(tmp_path: Path, archive_path: Path) -> None:
    make_zip(archive_path, {"main.tex": "x" * 1000})
    manifest = ZipProjectArchive().inspect(archive_path, LIMITS)
    raw = bytearray(archive_path.read_bytes())
    # занижаем размер в локальном заголовке и центральном каталоге: данных в потоке больше заявленного
    for marker, offset in ((b"PK\x03\x04", 22), (b"PK\x01\x02", 24)):
        at = 0
        while (at := raw.find(marker, at)) != -1:
            size = int.from_bytes(raw[at + offset : at + offset + 4], "little")
            if size == 1000:
                raw[at + offset : at + offset + 4] = (10).to_bytes(4, "little")
            at += 4
    archive_path.write_bytes(bytes(raw))
    volume = LocalDiskProjectVolume(tmp_path / "vol")
    folder = volume.allocate(PROJECT_ID)

    with pytest.raises(ProjectImportError) as caught:
        ZipProjectArchive().extract(archive_path, manifest, volume, folder)

    assert caught.value.code is ProjectImportCode.archive_invalid


def test__extract__writes_files_skips_hooks_records_and_junk(tmp_path: Path, archive_path: Path) -> None:
    make_zip(
        archive_path,
        {
            "main.tex": "hello",
            "chapters/one.tex": "one",
            ".DS_Store": "x",
            ".hse-studio/compiles/a.json": "{}",
            ".hse-studio/git/hooks/pre-commit": "#!/bin/sh",
        },
        prefix="thesis/",
    )
    archive = ZipProjectArchive()
    manifest = archive.inspect(archive_path, LIMITS)
    volume = LocalDiskProjectVolume(tmp_path / "vol")
    folder = volume.allocate(PROJECT_ID)

    result = archive.extract(archive_path, manifest, volume, folder)

    written = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    assert written == [".hse-studio/project.json", "chapters/one.tex", "main.tex"]
    assert result.files == 3
    assert (folder / "chapters" / "one.tex").read_text() == "one"


def test__extract__target_has_symlinked_dir__refused(tmp_path: Path, archive_path: Path) -> None:
    make_zip(archive_path, {"sub/main.tex": "x"})
    archive = ZipProjectArchive()
    manifest = archive.inspect(archive_path, LIMITS)
    volume = LocalDiskProjectVolume(tmp_path / "vol")
    folder = volume.allocate(PROJECT_ID)
    outside = tmp_path / "outside"
    outside.mkdir()
    (folder / "sub").symlink_to(outside)

    with pytest.raises(ProjectImportError) as caught:
        archive.extract(archive_path, manifest, volume, folder)

    assert caught.value.code is ProjectImportCode.archive_unsafe
    assert list(outside.iterdir()) == []
