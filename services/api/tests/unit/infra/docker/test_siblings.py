from __future__ import annotations

import pytest
from hse_doc_studio.infra.docker import siblings
from hse_doc_studio.infra.docker.siblings import (
    Reachability,
    SiblingNetwork,
    container_on_network,
    host_gateway_url,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        pytest.param("http://127.0.0.1:11434", "http://host.docker.internal:11434", id="loopback_ip"),
        pytest.param("http://localhost:11434", "http://host.docker.internal:11434", id="localhost"),
        pytest.param("http://ollama.lan:11434", "http://ollama.lan:11434", id="remote_host_untouched"),
    ],
)
def test__host_gateway_url__rewrites_only_loopback(url: str, expected: str) -> None:
    assert host_gateway_url(url) == expected


@pytest.mark.unit
def test__sibling_network_disabled__publish_args__publishes_the_port() -> None:
    # Нативный запуск: сети нет, поведение как до её появления.
    assert SiblingNetwork.disabled().publish_args(58334, 8010) == ["-p", "127.0.0.1:58334:8010"]


@pytest.mark.unit
async def test__sibling_network_disabled__resolve_url__returns_none() -> None:
    assert await SiblingNetwork.disabled().resolve_url("hse-languagetool", 8010) is None


@pytest.mark.unit
async def test__container_on_network__docker_prints_nil_for_missing_key__reports_absent(monkeypatch) -> None:
    # Регрессия: `index .Networks "<name>"` на отсутствующем ключе печатает `<nil>`,
    # и контейнер молча оставался вне сети.
    async def fake_run(args: list[str], timeout: float = 0) -> tuple[int, str, str]:
        return 0, "bridge\n", ""

    monkeypatch.setattr(siblings, "run_docker", fake_run)

    assert await container_on_network("hse-languagetool", "hse-studio-net") is False


@pytest.mark.unit
async def test__container_on_network__name_listed__reports_present(monkeypatch) -> None:
    async def fake_run(args: list[str], timeout: float = 0) -> tuple[int, str, str]:
        return 0, "bridge\nhse-studio-net\n", ""

    monkeypatch.setattr(siblings, "run_docker", fake_run)

    assert await container_on_network("hse-languagetool", "hse-studio-net") is True


@pytest.mark.unit
def test__outbound_url__native_run__keeps_the_url_the_user_typed(monkeypatch) -> None:
    monkeypatch.setattr(siblings, "in_container", lambda: False)

    assert siblings.outbound_url("http://localhost:1234/v1") == "http://localhost:1234/v1"


@pytest.mark.unit
def test__outbound_url__in_container__rewrites_loopback_to_the_host(monkeypatch) -> None:
    # Пользователь настраивает локальный LM Studio, глядя на СВОЮ машину.
    monkeypatch.setattr(siblings, "in_container", lambda: True)

    assert siblings.outbound_url("http://localhost:1234/v1") == "http://host.docker.internal:1234/v1"


@pytest.mark.unit
def test__outbound_url__in_container__remote_provider_untouched(monkeypatch) -> None:
    monkeypatch.setattr(siblings, "in_container", lambda: True)

    assert siblings.outbound_url("https://api.openai.com/v1") == "https://api.openai.com/v1"


@pytest.mark.unit
def test__outbound_url__empty__stays_empty(monkeypatch) -> None:
    monkeypatch.setattr(siblings, "in_container", lambda: True)

    assert siblings.outbound_url(None) is None
    assert siblings.outbound_url("") == ""


# ── Reachability: каким адресом сосед придёт К НАМ ──────────────────────────
#
# Регрессия, ради которой этот блок и написан: адрес для ONLYOFFICE собирался
# как `host.docker.internal:<ПОРТ СЛУШАНИЯ>`, а compose продукта слушает 8000 и
# публикует 17240 — то есть DS стучался на хостовый порт, где никто не отвечает,
# и редактор не мог ни скачать документ, ни сохранить правку.


def _reachability(siblings_network: SiblingNetwork, listen_port: int = 8000) -> Reachability:
    return Reachability(siblings_network, gateway_host="host.docker.internal", listen_port=listen_port)


@pytest.mark.unit
async def test__reachability__shared_network_is_up__uses_our_container_name_and_listening_port(
    monkeypatch,
) -> None:
    # В общей сети сосед зовёт нас по имени контейнера, и там виден ВНУТРЕННИЙ
    # порт — публикация наружу к этому пути отношения не имеет.
    network = SiblingNetwork.disabled()
    monkeypatch.setattr(network, "ensure", lambda: _async("hse-studio-net"))
    monkeypatch.setattr(siblings, "self_container_ref", lambda: "9ab1733108da")

    assert await _reachability(network).base_url() == "http://9ab1733108da:8000"


@pytest.mark.unit
async def test__reachability__in_container_without_network__uses_the_published_port(monkeypatch) -> None:
    # Сети нет — идём через хостовый шлюз, и порт обязан быть ОПУБЛИКОВАННЫМ.
    monkeypatch.setattr(siblings, "self_container_ref", lambda: "9ab1733108da")

    async def fake_published(name: str, container_port: int, timeout: float = 0) -> int:
        assert (name, container_port) == ("9ab1733108da", 8000)
        return 17240

    monkeypatch.setattr(siblings, "published_host_port", fake_published)

    assert await _reachability(SiblingNetwork.disabled()).base_url() == "http://host.docker.internal:17240"


@pytest.mark.unit
async def test__reachability__native_run__uses_the_listening_port(monkeypatch) -> None:
    # Нативно публикации нет вовсе, слушающий порт и есть достижимый.
    monkeypatch.setattr(siblings, "self_container_ref", lambda: None)

    assert await _reachability(SiblingNetwork.disabled(), 17240).base_url() == "http://host.docker.internal:17240"


@pytest.mark.unit
async def test__reachability__published_port_unreadable__falls_back_to_the_listening_one(monkeypatch) -> None:
    monkeypatch.setattr(siblings, "self_container_ref", lambda: "9ab1733108da")

    async def fake_published(name: str, container_port: int, timeout: float = 0) -> None:
        return None

    monkeypatch.setattr(siblings, "published_host_port", fake_published)

    assert await _reachability(SiblingNetwork.disabled()).base_url() == "http://host.docker.internal:8000"


@pytest.mark.unit
async def test__reachability__asked_twice__resolves_once(monkeypatch) -> None:
    # Ответ — процессный факт: сменить его может только пересоздание контейнера,
    # а оно убивает процесс. Каждое открытие редактора дёргать докер незачем.
    monkeypatch.setattr(siblings, "self_container_ref", lambda: None)
    calls = 0

    network = SiblingNetwork.disabled()
    original = network.self_base_url

    async def counting(port: int) -> str | None:
        nonlocal calls
        calls += 1
        return await original(port)

    monkeypatch.setattr(network, "self_base_url", counting)
    reachability = _reachability(network)

    await reachability.base_url()
    await reachability.base_url()

    assert calls == 1


async def _async(value: str) -> str:
    return value
