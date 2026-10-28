from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from hse_doc_studio.api.auth_cookie import (
    clear_session_cookie,
    is_secure_public_url,
    public_origin,
    set_session_cookie,
)
from hse_doc_studio.api.security_headers import SecurityHeadersMiddleware, content_disposition
from httpx import ASGITransport, AsyncClient

_SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _app(*, hsts: bool = False) -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/projects/{project_id}/files/{path:path}")
    async def get_file(project_id: str, path: str) -> Response:  # noqa: ARG001
        kinds = {
            "a.svg": ("image/svg+xml", _SVG),
            "a.html": ("text/html; charset=utf-8", b"<script>1</script>"),
            "a.pdf": ("application/pdf", b"%PDF"),
            "a.tex": ("text/plain; charset=utf-8", b"x"),
            "я.png": ("image/png", b"\x89PNG"),
        }
        media, body = kinds[path]
        return Response(content=body, media_type=media)

    @app.get("/api/v1/projects/{project_id}/git/conflicts/blob")
    async def blob(project_id: str) -> Response:  # noqa: ARG001
        return Response(b"<b>", media_type="text/html", headers={"Content-Disposition": "inline; filename=x.html"})

    @app.get("/api/v1/other")
    async def other() -> dict[str, int]:
        return {"a": 1}

    app.add_middleware(SecurityHeadersMiddleware, frame_ancestors=["https://office.example"], hsts=hsts)
    return app


async def _get(path: str, *, hsts: bool = False) -> Response:
    async with AsyncClient(transport=ASGITransport(app=_app(hsts=hsts)), base_url="http://t") as client:
        return await client.get(path)


@pytest.mark.parametrize("name", ["a.svg", "a.html"])
async def test__active_content__attachment_with_sandbox_csp(name: str) -> None:
    response = await _get(f"/api/v1/projects/p/files/{name}")

    csp = response.headers["content-security-policy"]
    assert csp.startswith("sandbox;")
    assert "default-src 'none'" in csp
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["x-content-type-options"] == "nosniff"


async def test__svg_with_script__cannot_run_as_a_page() -> None:
    response = await _get("/api/v1/projects/p/files/a.svg")

    assert response.content == _SVG
    assert "script-src" not in response.headers["content-security-policy"]
    assert "sandbox" in response.headers["content-security-policy"]
    assert response.headers["content-disposition"].startswith("attachment")


async def test__plain_text__inline_with_filename_and_sandbox() -> None:
    response = await _get("/api/v1/projects/p/files/a.tex")

    assert response.headers["content-disposition"].startswith('inline; filename="a.tex"')
    assert "sandbox" in response.headers["content-security-policy"]


async def test__pdf__inline_without_sandbox() -> None:
    response = await _get("/api/v1/projects/p/files/a.pdf")

    assert response.headers["content-disposition"].startswith("inline")
    assert "sandbox" not in response.headers["content-security-policy"]
    assert "default-src 'none'" in response.headers["content-security-policy"]


async def test__non_ascii_filename__is_encoded() -> None:
    response = await _get("/api/v1/projects/p/files/я.png")

    assert "filename*=UTF-8''%D1%8F.png" in response.headers["content-disposition"]


async def test__route_inline_for_html__becomes_attachment() -> None:
    response = await _get("/api/v1/projects/p/git/conflicts/blob")

    assert response.headers["content-disposition"] == "attachment; filename=x.html"


async def test__other_routes__get_base_headers_with_office_ancestors() -> None:
    response = await _get("/api/v1/other")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["content-security-policy"] == "frame-ancestors 'self' https://office.example"
    assert "content-disposition" not in response.headers
    assert "strict-transport-security" not in response.headers


async def test__hsts_only_when_enabled() -> None:
    response = await _get("/api/v1/other", hsts=True)

    assert response.headers["strict-transport-security"].startswith("max-age=")


def test__content_disposition_strips_quotes() -> None:
    assert content_disposition("attachment", 'a"b.txt').startswith('attachment; filename="ab.txt"')


def test__public_origin_and_secure_flag() -> None:
    assert public_origin("https://Studio.Example.org/app") == "https://studio.example.org"
    assert public_origin("not a url") is None
    assert public_origin(None) is None
    assert is_secure_public_url("https://x.org")
    assert not is_secure_public_url("http://x.org")
    assert not is_secure_public_url(None)


def test__session_cookie_attributes__https() -> None:
    response = Response()
    set_session_cookie(response, "v", secure=True, max_age_s=60)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-hse_session=v")
    for part in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=60"):
        assert part in cookie
    assert "Domain" not in cookie


def test__session_cookie_attributes__http() -> None:
    response = Response()
    set_session_cookie(response, "v", secure=False, max_age_s=60)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("hse_session=v")
    assert "HttpOnly" in cookie
    assert "Secure" not in cookie


def test__clear_cookie__expires_it() -> None:
    response = Response()
    clear_session_cookie(response, secure=True)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith('__Host-hse_session=""') or cookie.startswith("__Host-hse_session=;")
    assert "Max-Age=0" in cookie
