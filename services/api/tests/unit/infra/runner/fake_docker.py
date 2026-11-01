"""Поддельный docker CLI для тестов сборки: пишет argv в журнал и имитирует latexmk, texcount и image inspect."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

_SCRIPT = """#!{python}
import json, os, sys, time
from pathlib import Path

argv = sys.argv[1:]
log = Path(os.environ["FAKE_DOCKER_LOG"])
with log.open("a") as fh:
    fh.write(json.dumps(argv) + "\\n")
mode = os.environ.get("FAKE_DOCKER_MODE", "ok")
if argv[:1] == ["version"]:
    print("27.0.0")
elif argv[:2] == ["image", "inspect"]:
    if mode == "no_image":
        sys.exit(1)
    print(json.dumps([{{"Id": "sha256:1", "Size": 10, "Created": "2026-01-01"}}]))
elif argv[:1] == ["run"] and "latexmk" in argv:
    mount = next(a for a in argv if a.endswith(":/work:z"))
    host = Path(mount.split(":")[0])
    workdir = argv[argv.index("-w") + 1]
    outdir = next(a for a in argv if a.startswith("-output-directory=")).split("=", 1)[1]
    stem = Path(argv[-1]).stem
    base = host / workdir.removeprefix("/work").lstrip("/") / outdir
    if mode == "hang":
        Path(os.environ["FAKE_DOCKER_PID"]).write_text(str(os.getpid()))
        print("started", flush=True)
        time.sleep(60)
    if mode == "fail":
        print("! LaTeX Error: boom")
        sys.exit(12)
    base.mkdir(parents=True, exist_ok=True)
    (base / (stem + ".pdf")).write_bytes(b"%PDF-1.5 built")
    (base / (stem + ".log")).write_text("Output written on x.pdf (3 pages, 100 bytes).\\n")
    print("latexmk ok")
elif argv[:1] == ["run"]:
    print("5+1+0 (1/0/0/0) Total")
    print("___HSE_TEXCOUNT_SEP___")
    print("50+10+0 (1/0/0/0) Total")
"""


def install_fake_docker(directory: Path) -> Path:
    path = directory / "docker"
    path.write_text(_SCRIPT.format(python=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def recorded_calls(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]
