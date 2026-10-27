"""Демо-стенд Git-синхронизации: настоящий API без GitHub, вся сеть локальная.

Поднимает две настоящие Студии (два процесса API со своими data_dir, профилями и папками проектов), общие
удалённые репозитории (голые file:// и git http-backend на 127.0.0.1) и раскладывает по ним проекты во всех состояниях,
которые рисует интерфейс: не подключён, всё отправлено, есть что отправить, есть новое у коллеги, расхождение с
конфликтами (текст, поля project.json, бинарный файл, удаление против правки), отказ доступа, нет связи, репозиторий
исчез. Фронт запускается без VITE_GIT_DEMO и ходит на первую Студию как на обычный бэкенд.

Запуск из services/api:

    uv run --all-extras python scripts/git_sync_demo.py            # стенд в каталоге во временной папке
    uv run --all-extras python scripts/git_sync_demo.py --root /tmp/hse-git-demo --port 17800

Дальше в другом терминале (из services/web-app):

    VITE_API_BASE_URL=http://localhost:17800 pnpm dev

Студия Анны слушает на --port, Студия Бориса на --port + 1, управление стендом на --port + 2:

    POST /server/<ключ>/mode/<ok|hang|drop|push_403>   режим http-сервера (hang показывает идущую синхронизацию)
    POST /server/<ключ>/token/<значение>                сменить токен сервера
    POST /colleague/push/<ключ проекта>                 Борис правит проект и отправляет (у Анны появляются входящие)
    GET  /state                                         адреса, идентификаторы проектов и пути (то же в seed.json)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

_SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SERVICE_ROOT))

from hse_doc_studio.core.git_sync.policy import FETCH_DEBOUNCE_S  # noqa: E402
from tests.fixtures.git_remote import (  # noqa: E402
    BareRemote,
    GitHttpServer,
    http_backend_available,
    make_bare_remote,
    seed_remote,
)

ANNA = ("Анна Петрова", "a.petrova@edu.hse.ru")
BORIS = ("Борис Сидоров", "b.sidorov@edu.hse.ru")
TOKEN = "demo-token-0123456789"  # noqa: S105 — токен локального демо-сервера
THESIS = "thesis/thesis.tex"
PLAN = "notes/plan.md"
OLD = "notes/old.txt"
DIAGRAM = "figures/diagram.png"
_READY_S = 90.0
_OP_S = 120.0
_ANNA_PNG = b"\x89PNG\r\n\x1a\nanna-diagram"
_BORIS_PNG = b"\x89PNG\r\n\x1a\nboris-diagram-newer"

_PLAN_BASE = "# План\n\n1. Обзор литературы\n2. Постановка задачи\n3. Эксперименты\n4. Выводы\n"


def _payload(name: str, folder: Path) -> dict[str, Any]:
    return {
        "name": name,
        "folder": str(folder),
        "pack_id": "hse-cs-se",
        "template_id": "vkr",
        "version": "2026.1",
        "engine": "xelatex",
        "kind": "research",
        "staffing": "solo",
        "lang": "ru",
        "authors": [{"name": ANNA[0], "group": None, "email": ANNA[1]}],
        "supervisor": None,
        "co_supervisor": None,
        "meta": {},
    }


@dataclass
class Studio:
    """Один настоящий процесс API со своим data_dir; ходим к нему по HTTP, как фронт."""

    key: str
    root: Path
    port: int
    profile: tuple[str, str]
    allow_origins: list[str]
    process: subprocess.Popen[bytes] | None = None
    client: httpx.Client = field(default=None)  # type: ignore[assignment]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        (self.root / "data").mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "PYTHONPATH": "",
            "HSE_STUDIO__DATA_DIR": str(self.root / "data"),
            "HSE_STUDIO__SERVER__HOST": "127.0.0.1",
            "HSE_STUDIO__SERVER__PORT": str(self.port),
            "HSE_STUDIO__UPDATE_FEED_URL": "off",
            "HSE_STUDIO__COMPILE__PREFETCH_IMAGE": "false",
            "HSE_STUDIO__AGENT__DEBUG_TRACE": "false",
            "HSE_STUDIO__LOGGING__LEVEL": "WARNING",
            "HSE_STUDIO__GIT__ALLOW_INSECURE_HTTP": "true",
            "HSE_STUDIO__CORS__ALLOW_ORIGINS": json.dumps(self.allow_origins),
        }
        log = (self.root / "api.log").open("wb")
        self.process = subprocess.Popen(  # noqa: S603 — фиксированная команда стенда
            [sys.executable, "-m", "hse_doc_studio.api.entrypoint"],
            cwd=_SERVICE_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.client = httpx.Client(base_url=self.url, timeout=60.0)
        deadline = time.monotonic() + _READY_S
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"API {self.key} завершился, см. {self.root / 'api.log'}")
            with contextlib.suppress(httpx.HTTPError):
                if self.client.get("/api/v1/profile").status_code == 200:
                    break
            time.sleep(0.3)
        else:
            raise RuntimeError(f"API {self.key} не ответил за {_READY_S:.0f} с")
        self.call("PUT", "/api/v1/profile", json={"name": self.profile[0], "email": self.profile[1]})

    def stop(self) -> None:
        if self.client is not None:
            self.client.close()
        if self.process is not None and self.process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.process.pid, signal.SIGKILL)

    def call(self, method: str, path: str, *, ok: tuple[int, ...] = (200, 201, 202, 204), **kw: Any) -> Any:
        resp = self.client.request(method, path, **kw)
        if resp.status_code not in ok:
            raise RuntimeError(f"{self.key} {method} {path} -> {resp.status_code}: {resp.text[:400]}")
        return (
            resp.json()
            if resp.content and resp.headers.get("content-type", "").startswith("application/json")
            else None
        )

    def wait(self, operation_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + _OP_S
        while time.monotonic() < deadline:
            op = self.call("GET", f"/api/v1/git/operations/{operation_id}")
            if op["status"] != "running":
                return op  # type: ignore[no-any-return]
            time.sleep(0.2)
        raise RuntimeError(f"операция {operation_id} не закончилась")

    # --- проекты ---------------------------------------------------------------------------------------------------

    def create_project(self, name: str, folder: Path) -> dict[str, Any]:
        folder.mkdir(parents=True, exist_ok=True)
        return self.call("POST", "/api/v1/projects", json=_payload(name, folder))  # type: ignore[no-any-return]

    def put(self, project: dict[str, Any], rel: str, text: str) -> None:
        self.call("PUT", f"/api/v1/projects/{project['id']}/files/{rel}", content=text.encode())

    def write(self, project: dict[str, Any], rel: str, content: bytes) -> None:
        target = Path(project["folder"]) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def read(self, project: dict[str, Any], rel: str) -> str:
        return (Path(project["folder"]) / rel).read_text(encoding="utf-8")

    def snapshot(self, project: dict[str, Any], message: str) -> None:
        self.call("POST", f"/api/v1/projects/{project['id']}/vcs/snapshots", json={"message": message})

    def rename(self, project: dict[str, Any], name: str) -> None:
        self.call("PATCH", f"/api/v1/projects/{project['id']}", json={"name": name})

    def connect(self, project: dict[str, Any], url: str, **body: Any) -> dict[str, Any]:
        return self.call(  # type: ignore[no-any-return]
            "PUT", f"/api/v1/projects/{project['id']}/git/remote", json={"url": url, "credential_id": None, **body}
        )

    def sync(self, project: dict[str, Any]) -> dict[str, Any]:
        started = self.call("POST", f"/api/v1/projects/{project['id']}/git/sync", json={})
        return self.wait(started["operation_id"])

    def fetch(self, project: dict[str, Any]) -> dict[str, Any]:
        return self.call("POST", f"/api/v1/projects/{project['id']}/git/fetch", ok=(200, 409, 502))  # type: ignore[no-any-return]

    def clone(self, url: str, folder: Path, **body: Any) -> dict[str, Any]:
        started = self.call("POST", "/api/v1/git/clone", json={"url": url, "folder": str(folder), **body})
        op = self.wait(started["operation_id"])
        if op["status"] != "succeeded":
            raise RuntimeError(f"клонирование не удалось: {op['error']}")
        return self.call("GET", f"/api/v1/projects/{op['result']['project_id']}")  # type: ignore[no-any-return]

    def status(self, project: dict[str, Any]) -> dict[str, Any]:
        return self.call("GET", f"/api/v1/projects/{project['id']}/git")  # type: ignore[no-any-return]


def _line(text: str, number: int, new: str) -> str:
    lines = text.splitlines(keepends=True)
    lines[number - 1] = new + "\n"
    return "".join(lines)


@dataclass
class Demo:
    root: Path
    anna: Studio
    boris: Studio
    remotes: dict[str, BareRemote] = field(default_factory=dict)
    servers: dict[str, GitHttpServer] = field(default_factory=dict)
    projects: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Те же проекты у Бориса (если он их клонировал).
    peers: dict[str, dict[str, Any]] = field(default_factory=dict)
    pushes: dict[str, int] = field(default_factory=dict)

    def remote(self, key: str) -> BareRemote:
        self.remotes[key] = make_bare_remote(self.root / "remotes" / f"{key}.git")
        return self.remotes[key]

    def http_server(self, key: str, *, token: str | None = TOKEN) -> GitHttpServer:
        server = GitHttpServer(root=self.root / "http" / key, token=token)
        server.root.mkdir(parents=True)
        server.start()
        self.servers[key] = server
        return server

    def folder(self, studio: Studio, slug: str) -> Path:
        return studio.root / "work" / slug

    # --- сценарии --------------------------------------------------------------------------------------------------

    def seed_all(self) -> None:
        self.local_only()
        self.in_sync()
        self.ahead()
        self.behind()
        self.diverged()
        self.auth_failed()
        self.offline()
        self.slow()
        self.gone()
        self.spare_remotes()
        # Выборка по просьбе человека не чаще раза в FETCH_DEBOUNCE_S после удачной: ждём окно и узнаём новости.
        time.sleep(FETCH_DEBOUNCE_S + 1)
        for key in ("behind", "diverged", "auth", "offline", "gone"):
            self.anna.fetch(self.projects[key])

    def local_only(self) -> None:
        project = self.anna.create_project("Заметки: только у меня", self.folder(self.anna, "notes-local"))
        self.projects["local"] = project

    def _publish(self, key: str, name: str, slug: str) -> dict[str, Any]:
        """Проект Анны, отправленный в новый пустой репозиторий: общая отправная точка сценариев."""
        project = self.anna.create_project(name, self.folder(self.anna, slug))
        self.anna.put(project, PLAN, _PLAN_BASE)
        self.anna.put(project, OLD, "Черновые заметки\nвторая строка\n")
        self.anna.write(project, DIAGRAM, b"\x89PNG\r\n\x1a\nbase-diagram")
        self.anna.snapshot(project, "Заготовка плана")
        remote = self.remote(key)
        self.anna.connect(project, remote.url)
        result = self.anna.sync(project)
        if result["status"] != "succeeded":
            raise RuntimeError(f"первая отправка {key}: {result['error']}")
        self.projects[key] = project
        return project

    def in_sync(self) -> None:
        self._publish("synced", "Курсовая: всё отправлено", "coursework-synced")

    def ahead(self) -> None:
        project = self._publish("ahead", "Реферат: есть что отправить", "essay-ahead")
        self.anna.put(project, PLAN, _line(_PLAN_BASE, 3, "1. Обзор литературы и рынка"))
        self.anna.put(project, "notes/ideas.md", "# Идеи\n\n- сравнить подходы\n")
        self.anna.snapshot(project, "Правки плана и идеи")

    def behind(self) -> None:
        self._publish("behind", "Отчёт по практике: у коллеги новое", "practice-behind")
        peer = self.boris.clone(self.remotes["behind"].url, self.folder(self.boris, "practice-behind"))
        self.peers["behind"] = peer
        self.colleague_push("behind")

    def colleague_push(self, key: str) -> None:
        """Борис правит проект и отправляет: у Анны появляется очередное входящее изменение."""
        peer = self.peers[key]
        n = self.pushes.get(key, 0) + 1
        self.pushes[key] = n
        self.boris.put(peer, f"notes/boris-{n}.md", f"# Заметка Бориса {n}\n\nДописал выводы по разделу.\n")
        self.boris.put(peer, PLAN, _line(self.boris.read(peer, PLAN), 6, f"4. Выводы и план работ, правка {n}"))
        result = self.boris.sync(peer)
        if result["status"] != "succeeded":
            raise RuntimeError(f"Борис не отправил {key}: {result['error']}")

    def diverged(self) -> None:
        project = self._publish("diverged", "Диплом: сети доверия", "thesis-diverged")
        peer = self.boris.clone(self.remotes["diverged"].url, self.folder(self.boris, "thesis-diverged"))
        self.peers["diverged"] = peer
        thesis = self.anna.read(project, THESIS)
        # Анна: введение (сольётся само), пункт плана, название проекта, удаление черновика, схема.
        self.anna.put(project, THESIS, _line(thesis, 3, "% Анна: введение переписано"))
        self.anna.put(project, PLAN, _line(_PLAN_BASE, 4, "2. Постановка задачи: версия Анны"))
        self.anna.rename(project, "Диплом: версия Анны")
        self.anna.call("DELETE", f"/api/v1/projects/{project['id']}/files/{OLD}")
        self.anna.write(project, DIAGRAM, _ANNA_PNG)
        self.anna.snapshot(project, "Анна: схема и удаление черновика")
        # Борис: пояснение далеко от правки Анны, тот же пункт плана, название, правка черновика, более новая схема.
        self.boris.put(peer, THESIS, _line(self.boris.read(peer, THESIS), 15, "% Борис: пояснение дописано"))
        self.boris.put(peer, PLAN, _line(_PLAN_BASE, 4, "2. Постановка задачи: версия Бориса"))
        self.boris.rename(peer, "Диплом: версия Бориса")
        self.boris.put(peer, OLD, "Черновые заметки\nвторая строка\nБорис дописал третью\n")
        time.sleep(1.1)
        self.boris.write(peer, DIAGRAM, _BORIS_PNG)
        self.boris.snapshot(peer, "Борис: схема и правки")
        result = self.boris.sync(peer)
        if result["status"] != "succeeded":
            raise RuntimeError(f"Борис не отправил diverged: {result['error']}")

    def _http_project(self, key: str, name: str, slug: str) -> tuple[dict[str, Any], GitHttpServer, str]:
        server = self.http_server(key)
        bare = server.create_repo("origin.git")
        project = self.anna.create_project(name, self.folder(self.anna, slug))
        credential = self.anna.call(
            "POST",
            "/api/v1/git/credentials",
            json={"kind": "pat", "label": f"Токен ({key})", "host": "127.0.0.1", "token": TOKEN},
        )
        self.anna.connect(project, server.url("origin.git"), credential_id=credential["id"], insecure_http=True)
        result = self.anna.sync(project)
        if result["status"] != "succeeded":
            raise RuntimeError(f"первая отправка {key}: {result['error']}")
        self.remotes[key] = bare
        self.projects[key] = project
        return project, server, credential["id"]

    def auth_failed(self) -> None:
        _, server, _ = self._http_project("auth", "Статья: токен отозван", "paper-auth")
        server.token = "rotated-token-abcdefghij"  # noqa: S105

    def offline(self) -> None:
        _, server, _ = self._http_project("offline", "Магистерская: нет связи", "master-offline")
        server.stop()

    def slow(self) -> None:
        self._http_project("slow", "Проект: медленная сеть", "project-slow")

    def gone(self) -> None:
        self._publish("gone", "Эссе: репозиторий удалён", "essay-gone")
        shutil.rmtree(self.remotes["gone"].path)

    def spare_remotes(self) -> None:
        """Репозитории, к которым Анна ещё не подключена: пустой, чужой (не Студия) и проект Бориса для клонирования."""
        self.remote("empty")
        plain = self.remote("plain")
        seed_remote(plain, {"README.md": "# Просто репозиторий\n\nЗдесь нет проекта Студии.\n"})
        project = self.boris.create_project(
            "Проект коллеги: можно клонировать", self.folder(self.boris, "shared-by-boris")
        )
        self.boris.put(project, PLAN, _PLAN_BASE)
        self.boris.snapshot(project, "Заготовка плана")
        self.remote("clone")
        self.boris.connect(project, self.remotes["clone"].url)
        result = self.boris.sync(project)
        if result["status"] != "succeeded":
            raise RuntimeError(f"Борис не отправил clone: {result['error']}")

    # --- управление ------------------------------------------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        return {
            "anna_url": self.anna.url,
            "boris_url": self.boris.url,
            "root": str(self.root),
            "token": TOKEN,
            "projects": {
                key: {"id": p["id"], "name": p["name"], "folder": p["folder"]} for key, p in self.projects.items()
            },
            "remotes": {
                key: self.servers[key].url("origin.git") if key in self.servers else r.url
                for key, r in self.remotes.items()
            },
            "servers": {key: s.base_url for key, s in self.servers.items()},
        }

    def control(self, method: str, path: str) -> tuple[int, Any]:  # noqa: PLR0911
        parts = [p for p in path.split("/") if p]
        if method == "GET" and parts == ["state"]:
            return 200, self.state()
        if method != "POST":
            return 405, {"detail": "method"}
        if len(parts) == 4 and parts[0] == "server" and parts[1] in self.servers:
            server = self.servers[parts[1]]
            if parts[2] == "mode":
                server._release.set()  # noqa: SLF001 — отпустить зависшие запросы перед сменой режима
                server._release.clear()  # noqa: SLF001
                server.mode = parts[3]
                return 200, {"mode": server.mode}
            if parts[2] == "token":
                server.token = parts[3]
                return 200, {"ok": True}
        if len(parts) == 3 and parts[:2] == ["colleague", "push"] and parts[2] in self.peers:
            self.colleague_push(parts[2])
            return 200, {"pushes": self.pushes[parts[2]]}
        return 404, {"detail": "unknown"}


def _serve_control(demo: Demo, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def _answer(self) -> None:
            try:
                status, body = demo.control(self.command, self.path)
            except Exception as exc:  # noqa: BLE001 — отдать причину тому, кто дёргает стенд
                status, body = 500, {"detail": str(exc)}
            payload = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = _answer  # noqa: N815
        do_POST = _answer  # noqa: N815

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=None, help="каталог стенда (по умолчанию временный)")
    parser.add_argument("--port", type=int, default=17800, help="порт Студии Анны; Бориса +1, управления +2")
    parser.add_argument(
        "--origins",
        default="http://localhost:3000,http://localhost:5173,http://localhost:4173",
        help="адреса фронта для CORS через запятую",
    )
    parser.add_argument("--keep", action="store_true", help="не удалять каталог стенда при выходе")
    args = parser.parse_args()

    if shutil.which("git") is None or not http_backend_available():
        print("нужен git с http-backend", file=sys.stderr)
        return 2
    root = (args.root or Path(tempfile.mkdtemp(prefix="hse-git-demo-"))).resolve()
    if args.root is not None and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    origins = [o for o in args.origins.split(",") if o]
    demo = Demo(
        root=root,
        anna=Studio("anna", root / "anna", args.port, ANNA, origins),
        boris=Studio("boris", root / "boris", args.port + 1, BORIS, origins),
    )
    control: ThreadingHTTPServer | None = None
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        print("Поднимаю две Студии…", flush=True)
        demo.anna.start()
        demo.boris.start()
        print("Раскладываю проекты по состояниям…", flush=True)
        demo.seed_all()
        control = _serve_control(demo, args.port + 2)
        state = demo.state()
        (root / "seed.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print()
        print(f"Студия Анны (для интерфейса): {demo.anna.url}")
        print(f"Студия Бориса (коллега):       {demo.boris.url}")
        print(f"Управление стендом:            http://127.0.0.1:{args.port + 2}/state")
        print(f"Каталог стенда:                {root}")
        print(f"Интерфейс: VITE_API_BASE_URL=http://localhost:{args.port} pnpm dev  (из services/web-app)")
        print()
        for key, project in demo.projects.items():
            print(f"  {key:9} {project['name']}")
        print("\nCtrl+C останавливает стенд.", flush=True)
        while True:
            time.sleep(1)
            for studio in (demo.anna, demo.boris):
                if studio.process is not None and studio.process.poll() is not None:
                    print(f"Студия {studio.key} завершилась, см. {studio.root / 'api.log'}", file=sys.stderr)
                    return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if control is not None:
            control.shutdown()
        for server in demo.servers.values():
            server.stop()
        demo.anna.stop()
        demo.boris.stop()
        if args.root is None and not args.keep:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
