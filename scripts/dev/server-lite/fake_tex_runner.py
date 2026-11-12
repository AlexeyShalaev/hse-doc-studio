"""Общий раннер стенда server-lite с поддельным TeX: для e2e, которым нужны собранный PDF и проверка подписей.

На стенде server-lite раннеров нет, а маршрут подписания (e2e/tests/signing-route.spec.ts) не обойтись без
собранного PDF (`compiled_sha256`) и без проверки открепленной подписи (задача `signature.verify_detached` идёт
только на общий раннер). Этот процесс и есть настоящий раннер (клиент протокола, цикл, рабочие папки, проверка
подписей gpg, выгрузка выходов), у которого заменён только исполнитель TeX: вместо контейнера TeX Live он кладёт
рядом с исходником одностраничный PDF A4 (строки исходника на латинице печатаются на нём, а SyncTeX ведёт с них к
исходнику). PDF зависит только от исходников документа (каталог главного файла),
поэтому сборка без правок даёт тот же sha, как настоящая воспроизводимая сборка (R12), а правка исходника даёт
другой PDF. Многогигабайтный образ TeX стенду не нужен.

Запускается в образе api (`docker compose --profile runner up -d runner`, см. `make server-lite-runner-up`):
токен регистрации кладётся в базу тем же путём, что `HSE_STUDIO__JOBS__RUNNER_BOOTSTRAP_TOKEN` у api, поэтому
окружение api не меняется. Раннер общий: пока он запущен, сборки всех людей стенда идут на нём; сценарии, которые
проверяют стенд без раннеров (M1), идут до него.
"""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import hashlib
import logging
import os
import re
import secrets
import signal
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from pathlib import Path

from dishka import make_async_container, provide
from hse_doc_studio.core.jobs.protocols import ProcessHandle
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.compile.backend import BuildBackend
from hse_doc_studio.infra.compile.docker_image_manager import DockerStatus, ImageInfo
from hse_doc_studio.infra.compile.latexmk import SENTINEL_DONE, SENTINEL_PAGES
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.infra.di.containers.runner import RunnerProvider
from hse_doc_studio.infra.runner.config import RunnerConfig
from hse_doc_studio.infra.runner.loop import RunnerLoop
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from pydantic import SecretStr
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

logger = logging.getLogger("fake-tex-runner")

_SKIP_SUFFIXES = (".pdf", ".log", ".aux", ".synctex.gz", ".fls", ".fdb_latexmk", ".xdv")


def sources_digest(source: Path) -> str:
    """Отпечаток исходников документа: файлы каталога главного файла по путям, без выходов сборки."""
    folder = source.parent
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and not p.name.endswith(_SKIP_SUFFIXES)):
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


# Строки исходника, похожие на обычный текст на латинице: поддельная сборка печатает их на странице и кладёт
# SyncTeX, который ведёт с них к строкам исходника (e2e комментариев из превью PDF, pdf-comments.spec.ts).
_PROSE = re.compile(r"^[A-Za-z][A-Za-z0-9 ,.;:'()-]{23,110}$")
_PROSE_MAX = 6
_PROSE_SIZE = 11
_PROSE_TOP_MM = 240
_PROSE_STEP_MM = 9
_SP_PER_BP = 65536 * 72.27 / 72


def prose_lines(source: Path) -> list[tuple[int, str]]:
    """(номер строки, текст) строк исходника, которые поддельная сборка печатает как абзац."""
    found = []
    for number, line in enumerate(source.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        text = line.strip()
        if _PROSE.match(text):
            found.append((number, text))
    return found[:_PROSE_MAX]


def _prose_baseline_mm(index: int) -> float:
    return _PROSE_TOP_MM - index * _PROSE_STEP_MM


def render_pdf(target: Path, doc_id: str, digest: str, prose: list[tuple[int, str]] | None = None) -> None:
    """Одна страница A4 без даты и случайного /ID (`invariant`): одинаковый вход даёт одинаковые байты."""
    pdf = canvas.Canvas(str(target), pagesize=A4, invariant=1)
    pdf.setTitle(doc_id)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(25 * mm, 270 * mm, f"Fake TeX build: {doc_id}")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(25 * mm, 262 * mm, f"sources sha256 {digest}")
    pdf.setStrokeGray(0.75)
    for row in range(12):
        y = (250 - row * 9) * mm
        pdf.line(25 * mm, y, 185 * mm, y)
    pdf.setFont("Helvetica", _PROSE_SIZE)
    for index, (_number, text) in enumerate(prose or []):
        pdf.drawString(25 * mm, _prose_baseline_mm(index) * mm + 2.5 * mm, text)
    pdf.showPage()
    pdf.save()


def write_synctex(target: Path, source_file: str, prose: list[tuple[int, str]]) -> None:
    """SyncTeX как у latexmk в контейнере (`/work/<путь>`): по строке набора на запись с номером строки исходника."""
    height_bp = float(A4[1])

    def sp(bp: float) -> int:
        return round(bp * _SP_PER_BP)

    records = []
    for index, (number, text) in enumerate(prose):
        baseline = height_bp - (_prose_baseline_mm(index) * mm + 2.5 * mm)
        width = pdfmetrics.stringWidth(text, "Helvetica", _PROSE_SIZE)
        box = f"{sp(25 * mm)},{sp(baseline)}:{sp(width)},{sp(_PROSE_SIZE * 0.75)},{sp(_PROSE_SIZE * 0.25)}"
        records += [f"(1,{number}:{box}", f"h1,{number}:{box}", ")"]
    body = "\n".join(
        [
            "SyncTeX Version:1",
            f"Input:1:/work/{source_file}",
            "Output:pdf",
            "Magnification:1000",
            "Unit:1",
            "X Offset:0",
            "Y Offset:0",
            "Content:",
            "{1",
            *records,
            "}1",
            "Postamble:",
            "",
        ]
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(gzip.compress(body.encode(), mtime=0))


class FakeTexExecutor:
    """`ITexBuildExecutor`: PDF рядом с исходником и те же строки-сентинелы, что у `latexmk.py`."""

    async def run(  # noqa: PLR0913 — сигнатура порта
        self,
        project_folder: Path,
        source_file: str,
        engine: str,
        max_iterations: int,
        doc_id: str,
        compile_id: uuid.UUID,
        image: str | None = None,
        on_process_started: Callable[[ProcessHandle], None] | None = None,
        project_id: uuid.UUID | None = None,
    ) -> AsyncGenerator[str, None]:
        source = project_folder / source_file

        async def lines() -> AsyncGenerator[str, None]:
            digest = await asyncio.to_thread(sources_digest, source)
            prose = await asyncio.to_thread(prose_lines, source)
            await asyncio.to_thread(render_pdf, source.with_suffix(".pdf"), doc_id, digest, prose)
            synctex = source.parent / ".build" / doc_id / f"{source.stem}.synctex.gz"
            await asyncio.to_thread(write_synctex, synctex, source_file, prose)
            yield f"fake-tex: {source_file} ({engine}) -> {source.with_suffix('.pdf').name}, sources {digest[:12]}"
            yield f"{SENTINEL_PAGES}1"
            yield SENTINEL_DONE

        return lines()


class FakeTexEnvironment:
    """`IBuildEnvironment`: «docker доступен, образ на месте»."""

    async def docker_status(self) -> DockerStatus:
        return DockerStatus(available=True, version="fake-tex", detail=None)

    async def inspect(self, image: str) -> ImageInfo | None:
        return ImageInfo(image=image, id="sha256:fake-tex", size_bytes=0, created="")


async def _no_sweep() -> int:
    return 0


class FakeTexRunnerProvider(RunnerProvider):
    """Настоящий раннер, у которого исполнитель TeX поддельный."""

    @provide
    async def get_build_backend(self, config: RunnerConfig) -> AsyncIterator[BuildBackend]:
        yield BuildBackend(
            executor=FakeTexExecutor(),
            environment=FakeTexEnvironment(),
            sweep=_no_sweep,
            tex_available=True,
            name="fake-tex",
        )


async def mint_registration_token() -> str:
    """Свежий токен регистрации общего раннера (тот же путь, что токен bootstrap из окружения api)."""
    secret = f"fake-tex-{secrets.token_hex(24)}"
    container = create_container(StudioMode.server)
    try:
        await (await container.get(RunnerRegistry)).ensure_bootstrap_token(secret)
    finally:
        await container.close()
    return secret


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = await mint_registration_token()
    config = RunnerConfig(token=SecretStr(token))
    container = make_async_container(FakeTexRunnerProvider(config))
    try:
        loop = await container.get(RunnerLoop)
        running = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                running.add_signal_handler(sig, loop.request_stop)
        logger.info("fake TeX runner %s polling %s", config.name, config.api_url)
        await loop.run()
    finally:
        await container.close()
    return 0


if __name__ == "__main__":
    os.umask(0o022)
    raise SystemExit(asyncio.run(main()))
