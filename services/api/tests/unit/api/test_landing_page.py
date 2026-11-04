"""Корень сервера для ссылок в мессенджерах: теги Open Graph, язык, экранирование, выключенный лендинг."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hse_doc_studio.api.landing_page import OG_IMAGE_PATH, install_landing_root, render_landing_index
from hse_doc_studio.core.identity.instance_settings import (
    KEY_LANDING_ENABLED,
    KEY_NAME,
    KEY_PUBLIC_URL,
    InstanceEnvOverrides,
)
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.mode import StudioMode

INDEX = """<!doctype html>
<html lang="ru">
  <head>
    <meta name="description" content="старое описание" />
    <title>старый заголовок</title>
  </head>
  <body><div id="root"></div></body>
</html>
"""


class _Repo:
    def __init__(self, values: dict[str, object] | None = None, *, broken: bool = False) -> None:
        self.values = values or {}
        self.broken = broken

    async def get_all(self) -> dict[str, object]:
        if self.broken:
            raise RuntimeError("db is down")
        return dict(self.values)


def _provider(repo: _Repo) -> Provider:
    class _P(Provider):
        scope = Scope.APP

        @provide
        def repo(self) -> IInstanceSettingsRepository:
            return repo  # type: ignore[return-value]

        @provide
        def env(self) -> InstanceEnvOverrides:
            return InstanceEnvOverrides()

    return _P()


def _client(tmp_path: Path, repo: _Repo, mode: StudioMode = StudioMode.server) -> TestClient:
    # Байтами: write_text на Windows превратил бы \n в \r\n, и ответ перестал бы совпадать с INDEX.
    (tmp_path / "index.html").write_bytes(INDEX.encode("utf-8"))
    (tmp_path / "og-landing.png").write_bytes(b"\x89PNG-fake")
    app = FastAPI()
    install_landing_root(app, mode=mode, static_dir=tmp_path)
    setup_dishka(make_async_container(_provider(repo), FastapiProvider()), app)
    return TestClient(app)


def _meta(html: str) -> dict[str, str]:
    pairs = re.findall(r'<meta\s+(?:property|name)="([^"]+)"\s+content="([^"]*)"', html)
    return dict(pairs)


def test__render__sets_title_description_and_open_graph_with_absolute_image() -> None:
    html = render_landing_index(INDEX, lang="ru", name="Studio ВШЭ", origin="https://studio.hse.example")

    meta = _meta(html)
    assert "<title>Studio ВШЭ:" in html
    assert "старый заголовок" not in html
    assert "старое описание" not in html
    assert meta["og:title"].startswith("Studio ВШЭ:")
    assert meta["og:image"] == f"https://studio.hse.example{OG_IMAGE_PATH}"
    assert meta["og:url"] == "https://studio.hse.example/"
    assert (meta["og:image:width"], meta["og:image:height"]) == ("1200", "630")
    assert meta["og:locale"] == "ru_RU"
    assert html.count('name="description"') == 1


def test__render__english_and_unknown_language_fall_back_to_russian() -> None:
    en = render_landing_index(INDEX, lang="en", name="Studio", origin="https://s.example")
    other = render_landing_index(INDEX, lang="de", name="Studio", origin="https://s.example")

    assert '<html lang="en">' in en
    assert _meta(en)["og:locale"] == "en_US"
    assert '<html lang="ru">' in other
    assert _meta(other)["og:locale"] == "ru_RU"


def test__render__escapes_the_installation_name() -> None:
    html = render_landing_index(INDEX, lang="ru", name='"><script>alert(1)</script>', origin="https://s.example")

    assert "<script>" not in html


def test__root__serves_tags_for_the_configured_name_and_public_url(tmp_path: Path) -> None:
    repo = _Repo({KEY_NAME: "Студия кафедры", KEY_PUBLIC_URL: "https://studio.hse.example"})

    response = _client(tmp_path, repo).get("/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["vary"] == "Accept-Language"
    assert _meta(response.text)["og:image"] == "https://studio.hse.example/og-landing.png"
    assert "Студия кафедры" in response.text


def test__root__without_public_url_uses_the_requested_host_and_never_leaks_internals(tmp_path: Path) -> None:
    response = _client(tmp_path, _Repo()).get("/", headers={"Accept-Language": "en-US,en;q=0.9"})

    meta = _meta(response.text)
    assert meta["og:image"] == "http://testserver/og-landing.png"
    assert meta["og:locale"] == "en_US"
    assert not re.search(r"\d+\.\d+\.\d+", response.text)


def test__root__language_query_wins_over_accept_language(tmp_path: Path) -> None:
    response = _client(tmp_path, _Repo()).get("/?lang=en", headers={"Accept-Language": "ru"})

    assert _meta(response.text)["og:locale"] == "en_US"


@pytest.mark.parametrize(
    ("repo", "mode"),
    [
        (_Repo({KEY_LANDING_ENABLED: False}), StudioMode.server),
        (_Repo(broken=True), StudioMode.server),
        (_Repo(), StudioMode.local),
    ],
    ids=["disabled", "settings_unreadable", "local_mode"],
)
def test__root__serves_the_plain_index_when_there_is_no_landing(tmp_path: Path, repo: _Repo, mode: StudioMode) -> None:
    response = _client(tmp_path, repo, mode).get("/")

    assert response.status_code == 200
    assert response.text == INDEX


def test__image__is_served_with_a_cache_header_and_404_when_missing(tmp_path: Path) -> None:
    client = _client(tmp_path, _Repo())

    ok = client.get(OG_IMAGE_PATH)
    (tmp_path / "og-landing.png").unlink()

    assert ok.content == b"\x89PNG-fake"
    assert "max-age" in ok.headers["cache-control"]
    assert client.get(OG_IMAGE_PATH).status_code == 404


def test__root_and_image__answer_head_requests_for_link_preview_bots(tmp_path: Path) -> None:
    client = _client(tmp_path, _Repo())

    assert client.head("/").status_code == 200
    assert client.head(OG_IMAGE_PATH).status_code == 200
