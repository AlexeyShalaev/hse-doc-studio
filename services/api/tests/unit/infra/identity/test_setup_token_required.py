from __future__ import annotations

import pytest
from hse_doc_studio.infra.di.providers.server_identity import setup_token_required


def _required(
    *,
    override: bool | None = None,
    host: str = "127.0.0.1",
    public_url: str | None = None,
    proxies: list[str] | None = None,
) -> bool:
    return setup_token_required(override=override, host=host, public_url=public_url, trusted_proxies=proxies or [])


@pytest.mark.unit
@pytest.mark.parametrize(
    "public_url", [None, "", "http://localhost:8000", "http://127.0.0.1:8000", "http://studio.localhost"]
)
def test__loopback_without_external_address__token_not_required(public_url: str | None) -> None:
    assert _required(public_url=public_url) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("host", "public_url", "proxies"),
    [
        ("0.0.0.0", None, []),  # noqa: S104 — проверяем именно такой адрес
        ("127.0.0.1", "https://studio.example.org", []),
        ("127.0.0.1", None, ["10.0.0.0/8"]),
        ("::1", "https://studio.example.org/app", []),
    ],
)
def test__exposed_instance__token_required_even_on_loopback_bind(
    host: str, public_url: str | None, proxies: list[str]
) -> None:
    assert _required(host=host, public_url=public_url, proxies=proxies) is True


@pytest.mark.unit
def test__explicit_override__wins() -> None:
    assert _required(override=True) is True
    assert _required(override=False, host="0.0.0.0", public_url="https://studio.example.org") is False  # noqa: S104
