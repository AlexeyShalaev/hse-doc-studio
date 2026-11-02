"""Фейковый docker-хост со стеком compose (api + runner): достаточно честный, чтобы прогнать сценарии апдейтера.

Команды разбираются так же, как их собирает `plan`: ps, inspect, stop, rm, tag, pull, `run -d` (пересоздание),
`run --rm ... hse-doc-studio db ...` (одноразовые) и cosign. Ручки-«поломки» лежат в полях класса.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from hse_doc_studio.infra.update.server_updater.docker import Result

REPO = "ghcr.io/alexeyshalaev/hse-doc-studio"
NEW_DIGEST = "sha256:" + "a" * 64


class FakeHost:
    def __init__(self, data_dir: Path, *, old_rev: str = "r1", new_rev: str = "r2") -> None:
        self.data_dir = data_dir
        self.old_rev, self.new_rev = old_rev, new_rev
        self.db_rev = old_rev
        self.images: dict[str, dict[str, Any]] = {
            "sha256:old": self._image("sha256:old", old_rev, []),
            "sha256:new": self._image("sha256:new", new_rev, [f"{REPO}@{NEW_DIGEST}"]),
        }
        self.refs = {f"{REPO}:0.3.1": "sha256:old", f"{REPO}:0.4.0": "sha256:new"}
        self.registry = {f"{REPO}:0.4.0"}
        self.services: dict[str, dict[str, Any]] = {
            "api": self._svc("api", ["api", "abcdef123456"]),
            "runner": self._svc("runner", ["runner", "fedcba654321"]),
        }
        self.log: list[list[str]] = []
        # поломки
        self.snapshot_ok = True
        self.migration_ok = True
        self.new_image_healthy = True
        self.old_image_healthy = True
        self.restore_ok = True
        self.pull_ok = True
        self.cosign_ok = True
        self.snapshot_rev: str | None = None

    @staticmethod
    def _image(image_id: str, head: str, digests: list[str]) -> dict[str, Any]:
        return {
            "Id": image_id,
            "RepoDigests": digests,
            "Head": head,
            "Config": {"Env": ["PYTHONUNBUFFERED=1"], "Cmd": None},
        }

    @staticmethod
    def _svc(name: str, aliases: list[str]) -> dict[str, Any]:
        return {
            "name": f"hse-{name}-1",
            "image_id": "sha256:old",
            "image_ref": f"{REPO}:0.3.1",
            "running": True,
            "restarts": 0,
            "aliases": aliases,
        }

    # ---- helpers ----

    def _resolve(self, ref: str) -> str | None:
        if ref in self.images:
            return ref
        return self.refs.get(ref)

    def _by_name(self, name: str) -> tuple[str, dict[str, Any]] | None:
        for key, svc in self.services.items():
            if name in {svc["name"], key, f"id-{key}"}:
                return key, svc
        return None

    def _healthy(self, image_id: str) -> bool:
        return self.new_image_healthy if image_id == "sha256:new" else self.old_image_healthy

    def container(self, key: str) -> dict[str, Any]:
        s = self.services[key]
        healthy = self._healthy(s["image_id"])
        state: dict[str, Any] = {"Running": s["running"], "Status": "running" if s["running"] else "exited"}
        if key == "api":
            state["Health"] = {"Status": "healthy" if healthy else "unhealthy"}
        return {
            "Id": f"id-{key}" + "0" * 20,
            "Name": "/" + s["name"],
            "Image": s["image_id"],
            "Config": {
                "Image": s["image_ref"],
                "Env": ["HSE_STUDIO__DB__DSN=postgresql://u:p@postgres/studio", "PATH=/bin"],
                "Labels": {"com.docker.compose.project": "stack", "com.docker.compose.service": key},
                "Cmd": ["hse-doc-studio", "runner"] if key == "runner" else None,
            },
            "HostConfig": {"NetworkMode": "stack_default", "RestartPolicy": {"Name": "unless-stopped"}},
            "Mounts": [],
            "NetworkSettings": {"Networks": {"stack_default": {"Aliases": s["aliases"]}}},
            "State": state,
            "RestartCount": s["restarts"],
        }

    @property
    def stack_healthy(self) -> bool:
        return all(s["running"] and self._healthy(s["image_id"]) for s in self.services.values())

    def versions(self) -> dict[str, str]:
        return {k: s["image_id"] for k, s in self.services.items()}

    # ---- IDocker ----

    def run(self, args: Sequence[str], timeout: float = 120.0) -> Result:  # noqa: C901, PLR0911, PLR0912
        a = list(args)
        self.log.append(a)
        cmd = a[0]
        if cmd == "ps":
            service = next((x.split("=", 2)[2] for x in a if x.startswith("label=com.docker.compose.service=")), None)
            return Result(0, f"id-{service}\n" if service in self.services else "")
        if cmd == "inspect":
            ref = a[1]
            found = self._by_name(ref)
            if found:
                return Result(0, json.dumps([self.container(found[0])]))
            image_id = self._resolve(ref)
            if image_id:
                return Result(0, json.dumps([self.images[image_id]]))
            return Result(1, "", "no such object")
        if cmd == "stop":
            found = self._by_name(a[-1])
            if found:
                found[1]["running"] = False
            return Result(0)
        if cmd == "rm":
            found = self._by_name(a[-1])
            if found:
                found[1]["running"] = False
                found[1]["removed"] = True
            return Result(0)
        if cmd == "tag":
            self.refs[a[2]] = a[1]
            return Result(0)
        if cmd == "pull":
            if not self.pull_ok or a[1] not in self.registry:
                return Result(1, "", "manifest unknown")
            return Result(0)
        if cmd == "run" and "-d" in a:
            return self._recreate(a)
        if cmd == "run" and "cosign" in " ".join(a[:4]):
            return Result(0 if self.cosign_ok else 1, "", "" if self.cosign_ok else "no signatures found")
        if cmd == "run" and "--rm" in a:
            return self._oneshot(a)
        return Result(1, "", f"unsupported: {a}")

    def _recreate(self, a: list[str]) -> Result:
        name = a[a.index("--name") + 1]
        found = self._by_name(name)
        assert found is not None
        key, svc = found
        image_ref = next(x for x in a if x.startswith(("sha256:", REPO)))
        image_id = self._resolve(image_ref)
        if image_id is None:
            return Result(1, "", "no such image")
        svc.update(image_id=image_id, image_ref=image_ref if not image_ref.startswith("sha256:") else svc["image_ref"])
        svc["running"] = True
        svc.pop("removed", None)
        aliases = [a[i + 1] for i, x in enumerate(a) if x == "--network-alias"]
        assert key in aliases, "пересозданный контейнер обязан сохранить имя сервиса в сети"
        return Result(0, "newid")

    def _oneshot(self, a: list[str]) -> Result:  # noqa: C901, PLR0911
        image_id = next((r for r in (self._resolve(x) for x in a) if r), "")
        tail = a[a.index("hse-doc-studio") + 1 :] if "hse-doc-studio" in a else []
        head = self.images[image_id]["Head"] if image_id else "?"
        if tail[:2] == ["db", "current"]:
            return Result(0, f"current: {self.db_rev}\nhead: {head}\n")
        if tail[:2] == ["db", "upgrade"]:
            if not self.migration_ok:
                return Result(1, "", "migration boom")
            self.db_rev = head
            return Result(0, f"ok: {head}\n")
        if tail[:2] == ["db", "snapshot"]:
            if not self.snapshot_ok:
                return Result(1, "", "pg_dump failed")
            out = a[a.index("--out") + 1].replace("/snap/", str(self.data_dir) + "/")
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_text("dump", encoding="utf-8")
            self.snapshot_rev = self.db_rev
            return Result(0)
        if tail[:2] == ["db", "restore-snapshot"]:
            if not self.restore_ok:
                return Result(1, "", "pg_restore failed")
            self.db_rev = self.snapshot_rev or self.db_rev
            return Result(0)
        return Result(1, "", f"unsupported oneshot {tail}")


def digest_doc(version: str = "0.4.0", digest: str = NEW_DIGEST) -> str:
    return json.dumps({"image": REPO, "version": version, "digest": digest})
