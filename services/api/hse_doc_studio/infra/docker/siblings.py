"""Как продукт-контейнер достаёт до соседних контейнеров, которые сам и поднимает.

Продукт поставляется контейнером, но соседей (LanguageTool, Gotenberg, ONLYOFFICE,
Ollama) он запускает на ХОСТОВОМ докере через смонтированный сокет. Раньше сосед
поднимался с `-p 127.0.0.1:<порт>:<порт>`, и бэкенд набирал `http://127.0.0.1:<порт>` —
это верно ровно для нативного запуска. В контейнере `127.0.0.1` — он сам, поэтому
LanguageTool оказывался «поднят и здоров», но недостижим: проверки молча не
выполнялись, а каждая сборка минутами висела на попытках соединения.

Решение — общая пользовательская docker-сеть: приложение заводит `hse-studio-net`,
подключает в неё себя и каждого соседа, и ходит по ИМЕНИ контейнера на его
внутренний порт. Наружу при этом не публикуется ничего (раньше порт висел хотя бы
на loopback хоста), а имена в docker DNS разрешаются одинаково на Windows, macOS и
Linux — в отличие от `host.docker.internal`, которого на Linux без костыля нет.

Нативный запуск ничего не меняет: сети нет, публикация и `127.0.0.1` как прежде.
"""

from __future__ import annotations

import structlog

from hse_doc_studio.infra.docker.cli import published_host_port, run_docker
from hse_doc_studio.infra.runtime.environment import in_container, self_container_ref

logger = structlog.get_logger()

# Имя сети намеренно фиксированное, а не из настроек: она — деталь реализации
# связи, а не то, что пользователь настраивает. Совпадает с сетью dev-стенда.
SIBLING_NETWORK = "hse-studio-net"

_NETWORK_TIMEOUT_S = 15.0

# Docker Desktop резолвит это имя в хост; на Linux оно появляется только с
# `--add-host=host.docker.internal:host-gateway` (его ставит compose продукта).
HOST_GATEWAY = "host.docker.internal"


def host_gateway_url(url: str) -> str:
    """Переписать loopback-адрес на хостовый шлюз.

    Нужно для служб, которые пользователь поднял САМ на своей машине (нативная
    Ollama): их не подключить в нашу сеть, они живут на loopback хоста.
    """
    for loopback in ("127.0.0.1", "localhost", "0.0.0.0"):  # noqa: S104 — список для ЗАМЕНЫ, не bind
        if f"//{loopback}:" in url or url.endswith(f"//{loopback}"):
            return url.replace(f"//{loopback}", f"//{HOST_GATEWAY}", 1)
    return url


def outbound_url(url: str | None) -> str | None:
    """Адрес, введённый ПОЛЬЗОВАТЕЛЕМ, — пригодный для исходящего запроса отсюда.

    Пользователь настраивает провайдера в браузере на своей машине и пишет то,
    что видит у себя: `http://localhost:1234` для локального LM Studio или vLLM.
    Для процесса внутри контейнера это его собственный loopback — запрос уходит
    в никуда. Переписываем на хостовый шлюз; при нативном запуске адрес остаётся
    ровно таким, каким его ввели.

    Хранится и показывается в интерфейсе всегда ОРИГИНАЛ: подменять то, что
    человек напечатал, нельзя — он не узнает свою настройку.
    """
    if not url or not in_container():
        return url
    return host_gateway_url(url)


async def ensure_sibling_network() -> str | None:
    """Создать общую сеть и подключить к ней себя. Возвращает имя сети или None.

    None означает «работаем по-старому»: либо запуск нативный, либо докер не дал
    создать/подключить сеть — тогда соседи поднимаются с публикацией порта, как
    раньше, и это по-прежнему рабочий сценарий для нативного бэкенда.
    """
    self_ref = self_container_ref()
    if self_ref is None:
        return None

    # `network create` для уже существующей сети возвращает ошибку — это норма,
    # отдельной идемпотентной команды у докера нет.
    rc, _out, err = await run_docker(["network", "create", SIBLING_NETWORK], timeout=_NETWORK_TIMEOUT_S)
    if rc != 0 and "already exists" not in err.lower():
        logger.warning("siblings: cannot create network", network=SIBLING_NETWORK, err=err.strip())
        return None

    rc, _out, err = await run_docker(["network", "connect", SIBLING_NETWORK, self_ref], timeout=_NETWORK_TIMEOUT_S)
    if rc != 0 and "already exists" not in err.lower():
        logger.warning("siblings: cannot join network", network=SIBLING_NETWORK, err=err.strip())
        return None

    logger.info("siblings: shared network ready", network=SIBLING_NETWORK, self_ref=self_ref)
    return SIBLING_NETWORK


async def connect_to_network(container: str, network: str) -> bool:
    """Подключить уже запущенного соседа к сети (для усыновления старых контейнеров)."""
    rc, _out, err = await run_docker(["network", "connect", network, container], timeout=_NETWORK_TIMEOUT_S)
    if rc == 0 or "already exists" in err.lower():
        return True
    logger.warning("siblings: cannot attach container to network", container=container, err=err.strip())
    return False


async def container_on_network(container: str, network: str) -> bool:
    """Уже ли контейнер в этой сети — чтобы не переподключать на каждой проверке.

    Перечисляем ИМЕНА сетей, а не индексируем словарь по ключу: на отсутствующем
    ключе docker печатает `<nil>` — непустую строку, которую легко принять за
    «сеть есть». Ровно на этом контейнер молча оставался вне сети, и обращение по
    имени падало с `Temporary failure in name resolution`.
    """
    template = "{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}\n{{end}}"
    rc, out, _err = await run_docker(["inspect", "--format", template, container], timeout=_NETWORK_TIMEOUT_S)
    if rc != 0:
        return False
    return network in {line.strip() for line in out.splitlines() if line.strip()}


class SiblingNetwork:
    """Единая точка ответа на вопрос «как достучаться до соседа».

    Живёт в APP-скоупе: подключение себя к сети — процессный факт, выяснять его
    на каждую проверку незачем. Все менеджеры соседей спрашивают только это, и
    поэтому ведут себя одинаково и в контейнере, и при нативном запуске.
    """

    def __init__(self) -> None:
        self._network: str | None = None
        self._resolved = False

    @classmethod
    def disabled(cls) -> SiblingNetwork:
        """Экземпляр, заранее решивший «сети нет» — поведение нативного запуска.

        Нужен там, где докера заведомо нет и спрашивать его бессмысленно: тесты
        и любой нативный сценарий, который не хочет ждать `docker network`.
        """
        instance = cls()
        instance._resolved = True
        return instance

    async def ensure(self) -> str | None:
        """Имя общей сети (создав её и подключив себя), либо None для нативного запуска."""
        if not self._resolved:
            self._network = await ensure_sibling_network()
            self._resolved = True
        return self._network

    def publish_args(self, host_port: int, container_port: int) -> list[str]:
        """Аргументы `docker run`, делающие соседа достижимым.

        В сетевом режиме порт наружу НЕ публикуется вовсе: сосед виден только
        участникам общей сети. Вызывать после `ensure()`.
        """
        if self._network is not None:
            return ["--network", self._network]
        return ["-p", f"127.0.0.1:{host_port}:{container_port}"]

    async def self_base_url(self, port: int) -> str | None:
        """Наш собственный адрес — таким его наберёт СОСЕД, чтобы прийти К НАМ.

        Нужно тем соседям, которые не просто принимают запрос, а ходят обратно:
        ONLYOFFICE Document Server сам скачивает документ у бэкенда и сам отдаёт
        сохранение колбэком. Внутри общей сети такой адрес ровно один — имя
        нашего контейнера на ВНУТРЕННЕМ порту.

        Опубликованный наружу порт здесь не годится: он живёт на хосте и вовсе
        не обязан совпадать с тем, что слушает процесс (compose продукта
        публикует 17240 на слушающий 8000). Имя же контейнера docker резолвит
        одинаково на всех ОС.

        None — общей сети нет: тогда обращаться к нам придётся через хостовый
        шлюз, см. `Reachability`.
        """
        network = await self.ensure()
        self_ref = self_container_ref()
        if network is None or self_ref is None:
            return None
        return f"http://{self_ref}:{port}"

    async def resolve_url(self, container_name: str, container_port: int) -> str | None:
        """URL соседа по имени контейнера; None — значит смотреть опубликованный порт.

        Уже запущенного соседа (поднятого до появления сети или прошлой версией
        приложения) при необходимости доподключаем — иначе усыновление вернуло бы
        имя, которое не резолвится.
        """
        network = await self.ensure()
        if network is None:
            return None
        if not await container_on_network(container_name, network):
            await connect_to_network(container_name, network)
        return f"http://{container_name}:{container_port}"


class Reachability:
    """Как СОСЕДНИЙ контейнер придёт К НАМ — один ответ на весь процесс.

    Обратное направление связи нужно не всем соседям: LanguageTool и Gotenberg
    получают запрос и отвечают в том же соединении. А ONLYOFFICE Document Server
    ходит в бэкенд САМ — скачать документ и отдать сохранение колбэком, — и
    поэтому обязан знать наш адрес. Случая три, и путать их нельзя:

    1. Мы в контейнере, общая сеть поднялась — зовут по имени нашего контейнера
       на ВНУТРЕННЕМ порту. Лучший путь: не зависит ни от публикации портов, ни
       от host-gateway и одинаково работает на всех ОС.
    2. Мы в контейнере, сети нет — остаётся хостовый шлюз, и порт тогда нужен
       ОПУБЛИКОВАННЫЙ. Он не обязан совпадать со слушающим: compose продукта
       публикует 17240 на слушающий 8000, и адрес со слушающим портом ведёт в
       никуда. Спрашиваем публикацию у докера про самих себя.
    3. Нативный запуск — хостовый шлюз, и там опубликованный порт равен
       слушающему, потому что публикации нет вовсе.

    Ответ кэшируется: сменить его может только пересоздание контейнера, а оно
    убивает процесс.
    """

    def __init__(self, siblings: SiblingNetwork, *, gateway_host: str, listen_port: int) -> None:
        self._siblings = siblings
        self._gateway_host = gateway_host
        self._listen_port = listen_port
        self._base_url: str | None = None

    async def base_url(self) -> str:
        if self._base_url is None:
            self._base_url = await self._resolve()
            logger.info("reachability: address for sibling containers", url=self._base_url)
        return self._base_url

    async def _resolve(self) -> str:
        via_network = await self._siblings.self_base_url(self._listen_port)
        if via_network is not None:
            return via_network
        return f"http://{self._gateway_host}:{await self._gateway_port()}"

    async def _gateway_port(self) -> int:
        """Порт, на который сосед постучится через хостовый шлюз.

        В контейнере это опубликованная наружу проекция нашего слушающего порта;
        не найдя её, честно откатываемся на слушающий и пишем предупреждение —
        молчаливая подстановка неверного порта выглядит как «редактор не
        открывается» без единой зацепки в логах.
        """
        self_ref = self_container_ref()
        if self_ref is None:
            return self._listen_port
        published = await published_host_port(self_ref, self._listen_port)
        if published is None:
            logger.warning(
                "reachability: cannot read own published port, falling back to the listening one",
                listen_port=self._listen_port,
            )
            return self._listen_port
        return published
