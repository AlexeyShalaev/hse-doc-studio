"""Статика интерфейса: кэш index.html и чанков, 404 на устаревший чанк, запасной маршрут для адресов интерфейса."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hse_doc_studio.api.spa_static import (
    IMMUTABLE_CACHE,
    REVALIDATE_CACHE,
    install_spa_fallback,
    looks_like_asset,
    mount_assets,
)

INDEX = '<!doctype html><html><body><div id="root"></div></body></html>'


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "admin-BnUkldQj.js").write_text("export default 1;", encoding="utf-8")
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    (tmp_path / "version.json").write_text('{"version":"1.2.3"}', encoding="utf-8")
    app = FastAPI()
    mount_assets(app, tmp_path)
    install_spa_fallback(app, tmp_path)
    return TestClient(app)


def test_existing_chunk_is_immutable(client: TestClient) -> None:
    response = client.get("/assets/admin-BnUkldQj.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == IMMUTABLE_CACHE


def test_missing_chunk_is_404_not_index(client: TestClient) -> None:
    for path in ("/assets/admin-OLDHASH.js", "/assets/old.css", "/assets/nested/gone.js"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert "<html" not in response.text
        assert response.headers["cache-control"] == "no-store"


def test_missing_file_outside_assets_is_404(client: TestClient) -> None:
    assert client.get("/gone.js").status_code == 404
    assert client.get("/static/app.css").status_code == 404


def test_index_is_revalidated(client: TestClient) -> None:
    for path in ("/index.html", "/projects/abc/files", "/admin/users", "/s/some-token"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.text == INDEX
        assert response.headers["cache-control"] == REVALIDATE_CACHE


def test_version_json_is_served_not_cached(client: TestClient) -> None:
    response = client.get("/version.json")
    assert response.status_code == 200
    assert response.json() == {"version": "1.2.3"}
    assert response.headers["cache-control"] == "no-store"


def test_version_json_missing_is_404(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    app = FastAPI()
    mount_assets(app, tmp_path)
    install_spa_fallback(app, tmp_path)
    assert TestClient(app).get("/version.json").status_code == 404


@pytest.mark.parametrize(
    ("path", "expected"),
    [("assets/a.js", True), ("x/y.CSS", True), ("projects/p/files", False), ("admin", False), ("", False)],
)
def test_looks_like_asset(path: str, expected: bool) -> None:
    assert looks_like_asset(path) is expected
