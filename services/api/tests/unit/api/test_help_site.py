"""Справка по /help/: сборка по аудитории, общие медиа, выход за пределы сборки, язык по умолчанию."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from hse_doc_studio.api import help_site
from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.help_site import (
    HelpAudience,
    install_help_site,
    pick_language,
    resolve_help_file,
    safe_relative,
)
from starlette.datastructures import Headers


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def help_root(tmp_path: Path) -> Path:
    for audience in ("user", "admin"):
        _write(tmp_path / audience / "ru" / "index.html", f"{audience} home")
        _write(tmp_path / audience / "ru" / "help-map.json", f'{{"audience": "{audience}"}}')
        _write(tmp_path / audience / "404.html", f"{audience} 404")
        _write(tmp_path / audience / "_astro" / "app.css", "css")
    _write(tmp_path / "admin" / "ru" / "admin" / "runners" / "index.html", "runners")
    _write(tmp_path / "media" / "runbooks" / "x" / "step-01.ru.light.webp", "img")
    return tmp_path


def _client(help_root: Path, monkeypatch: pytest.MonkeyPatch, audience: HelpAudience = "user") -> TestClient:
    async def fake_audience(_request: Request, _cfg: Settings) -> HelpAudience:
        return audience

    monkeypatch.setattr(help_site, "help_audience", fake_audience)
    cfg = Settings()
    monkeypatch.setattr(cfg, "help_dir", help_root)
    app = FastAPI()
    assert install_help_site(app, cfg)
    return TestClient(app, follow_redirects=False)


@pytest.mark.parametrize("path", ["../secret", "ru/../../etc/passwd", "a\\b", "x\x00y"])
def test__path_leaving_the_build__is_refused(path: str) -> None:
    assert safe_relative(path) is None


def test__user_build__has_no_admin_articles(help_root: Path) -> None:
    assert resolve_help_file(help_root, "user", "ru/admin/runners/") is None
    assert resolve_help_file(help_root, "admin", "ru/admin/runners/") == help_root / "admin/ru/admin/runners/index.html"


def test__media__is_shared_between_audiences(help_root: Path) -> None:
    rel = "media/runbooks/x/step-01.ru.light.webp"
    assert resolve_help_file(help_root, "user", rel) == resolve_help_file(help_root, "admin", rel)


def test__help_map__depends_on_the_reader(help_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _client(help_root, monkeypatch, "user").get("/help/ru/help-map.json").json() == {"audience": "user"}
    admin = _client(help_root, monkeypatch, "admin").get("/help/ru/help-map.json")
    assert admin.json() == {"audience": "admin"}
    assert admin.headers["cache-control"] == "private, no-cache"


def test__admin_page_for_a_user__is_the_404_page(help_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(help_root, monkeypatch, "user").get("/help/ru/admin/runners/")
    assert response.status_code == 404
    assert response.text == "user 404"


def test__directory_without_slash__redirects(help_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(help_root, monkeypatch).get("/help/ru")
    assert response.status_code == 301
    assert response.headers["location"] == "/help/ru/"


def test__root__redirects_to_the_interface_language(help_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(help_root, monkeypatch).get("/help/", headers={"x-interface-language": "en"})
    assert response.headers["location"] == "/help/en/"


def test__assets__are_immutable(help_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(help_root, monkeypatch).get("/help/_astro/app.css")
    assert "immutable" in response.headers["cache-control"]


def test__no_build__no_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = Settings()
    monkeypatch.setattr(cfg, "help_dir", tmp_path / "missing")
    assert not install_help_site(FastAPI(), cfg)


@pytest.mark.parametrize(
    ("query", "headers", "expected"),
    [
        ("lang=en", {}, "en"),
        ("", {"accept-language": "en-US,en;q=0.9"}, "en"),
        ("", {"accept-language": "de-DE"}, "ru"),
    ],
)
def test__language_pick(query: str, headers: dict[str, str], expected: str) -> None:
    scope = {
        "type": "http",
        "query_string": query.encode(),
        "headers": Headers(headers).raw,
        "method": "GET",
        "path": "/help/",
    }
    assert pick_language(Request(scope)) == expected


async def test__local_studio__reads_the_user_build() -> None:
    cfg = Settings()
    assert cfg.mode.value == "local"
    assert await help_site.help_audience(Request({"type": "http", "headers": []}), cfg) == "user"
