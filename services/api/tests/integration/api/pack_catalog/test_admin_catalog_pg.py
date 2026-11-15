"""«Каталоги паков» в админке сервера (template-studio.md, 10.3, срез T17): архив, проверка, применение, история,
выключение, аудит каждого действия, мастер проекта видит пак с источником. Настоящий `create_app` на Postgres."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.pack_catalog import write_pack
from tests.integration.api.pack_studio.test_pack_studio_server_pg import _admin, _audit, _author, server

pytestmark = [pytest.mark.pg, pytest.mark.timeout(180)]

ADMIN = "/api/admin/pack-catalog"

__all__ = ["server"]


def _zip(root: Path, *, released: tuple[str, ...] = ("2026.1.0",), extra: dict[str, bytes] | None = None) -> bytes:
    stage = root / f"stage-{len(released)}"
    write_pack(stage / "packs", released=released)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                zf.write(path, f"acme-packs-main/{path.relative_to(stage).as_posix()}")
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return buffer.getvalue()


def _upload(admin: Any, body: bytes, **query: Any) -> Any:
    return admin.post(
        f"{ADMIN}/sources/archive",
        params={"name": "acme-packs.zip", **query},
        content=body,
        headers={"Content-Type": "application/octet-stream"},
    )


def test__archive__check_apply_wizard_history_and_audit(server: TestClient, tmp_path: Path) -> None:
    admin = _admin(server)

    created = _upload(admin, _zip(tmp_path), label="Паки Acme")
    assert created.status_code == 201, created.text
    source = created.json()
    check = admin.post(f"{ADMIN}/sources/{source['id']}/check")
    assert check.status_code == 200, check.text
    report = check.json()
    applied = admin.post(f"{ADMIN}/sources/{source['id']}/apply", json={"revision": report["revision"]})
    overview = admin.get(ADMIN).json()
    history = admin.get(f"{ADMIN}/sources/{source['id']}/history").json()
    packs = admin.get("/api/v1/catalog/packs").json()

    assert source["kind"] == "archive"
    assert source["archive_name"] == "acme-packs.zip"
    assert report["ok"], report
    assert report["revision"] == source["archive_digest"]
    assert applied.status_code == 200, applied.text
    assert applied.json()["added"] == ["acme/report@2026.1.0"]
    assert overview["sources"][0]["applied_revision"] == report["revision"]
    assert overview["sources"][0]["packs"][0]["id"] == "acme"
    assert [e["action"] for e in history] == ["apply", "check", "add"]
    acme = next(p for p in packs if p["id"] == "acme")
    assert acme["origin"] == {
        "kind": "subscribed",
        "source_kind": "archive",
        "label": "Паки Acme",
        "url": None,
        "ref": None,
        "revision": report["revision"],
        "replaces_builtin": False,
    }
    for action in ("pack_catalog.source_add", "pack_catalog.check", "pack_catalog.apply"):
        (event,) = _audit(admin, action)
        assert event["target"] == source["id"]

    off = admin.patch(f"{ADMIN}/sources/{source['id']}", json={"enabled": False})
    assert off.status_code == 200, off.text
    assert "acme" not in {p["id"] for p in admin.get("/api/v1/catalog/packs").json()}
    assert _audit(admin, "pack_catalog.source_disable")
    gone = admin.request("DELETE", f"{ADMIN}/sources/{source['id']}")
    assert gone.status_code == 204
    assert _audit(admin, "pack_catalog.source_remove")


def test__archive__new_revision_and_unsafe_archive(server: TestClient, tmp_path: Path) -> None:
    admin = _admin(server)
    source = _upload(admin, _zip(tmp_path)).json()
    first = admin.post(f"{ADMIN}/sources/{source['id']}/check").json()
    admin.post(f"{ADMIN}/sources/{source['id']}/apply", json={"revision": first["revision"]})

    replaced = admin.put(
        f"{ADMIN}/sources/{source['id']}/archive",
        params={"name": "acme-2.zip"},
        content=_zip(tmp_path, released=("2026.1.0", "2026.1.1")),
        headers={"Content-Type": "application/octet-stream"},
    )
    second = admin.post(f"{ADMIN}/sources/{source['id']}/check").json()
    unsafe = _upload(admin, _zip(tmp_path, extra={"../evil.txt": b"x"}))
    unsafe_check = admin.post(f"{ADMIN}/sources/{unsafe.json()['id']}/check")

    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["checked_revision"] is None
    assert {v["version"]: v["verdict"] for v in second["packs"][0]["versions"]} == {
        "2026.1.0": "present",
        "2026.1.1": "new",
    }
    assert unsafe_check.status_code == 400
    assert unsafe_check.json()["code"] == "archive_unsafe"


def test__archive__not_an_archive_is_refused(server: TestClient) -> None:
    garbage = _upload(_admin(server), b"not an archive at all")

    assert garbage.status_code == 400
    assert garbage.json()["code"] == "archive_invalid"


def test__catalog__only_for_instance_admin(server: TestClient) -> None:
    _, author = _author(server)

    assert author.get(ADMIN).status_code == 404
    assert author.post(f"{ADMIN}/sources", json={"url": "https://example.org/x.git"}).status_code == 404
