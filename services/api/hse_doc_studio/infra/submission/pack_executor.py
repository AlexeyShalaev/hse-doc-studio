"""Исполнитель пакета сдачи: применяет записи готового плана и упаковывает папку в архив.

Проекта исполнитель не знает: все решения принял планировщик на стороне API,
сюда приходит нагрузка `pack.submission` и рабочая папка, относительно которой
разворачиваются пути входов. Синхронный: вызывающий сам решает, в каком потоке
его запускать.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import structlog

from hse_doc_studio.core.jobs.files import StampSpec
from hse_doc_studio.core.jobs.pack import PackEntry, PackEntryKind, PackSkip, PackSubmissionPayload
from hse_doc_studio.core.signatures.stamps import Stamp
from hse_doc_studio.infra.signatures.pdf_stamper import PdfStamper

logger = structlog.get_logger()

# Папка и архив пакета лежат в этой подпапке рабочей папки.
SUBMISSIONS_DIR = "submissions"

# Причины в PackSkip, которые ставит исполнитель.
REASON_ARCNAME_ESCAPES = "arcname_escapes"
REASON_WRITE_FAILED = "write_failed"
REASON_SOURCE_ESCAPES = "source_escapes"

_EXTERNAL_TIMEOUT_SEC = 120.0


@dataclass(frozen=True)
class ArchiveFormatSpec:
    id: str
    label: str
    ext: str
    # Внешние утилиты, умеющие этот формат (берется первая найденная). Пустой кортеж:
    # формат делает сам shutil, он доступен всегда.
    tools: tuple[str, ...]


# zip/tar.gz нативные (shutil); 7z/rar вызывают внешнюю утилиту, которой может не
# быть: наличие проверяется через shutil.which, как у внешних редакторов.
ARCHIVE_FORMATS: tuple[ArchiveFormatSpec, ...] = (
    ArchiveFormatSpec(id="zip", label="ZIP", ext=".zip", tools=()),
    ArchiveFormatSpec(id="targz", label="TAR.GZ", ext=".tar.gz", tools=()),
    ArchiveFormatSpec(id="7z", label="7z", ext=".7z", tools=("7z", "7za")),
    ArchiveFormatSpec(id="rar", label="RAR", ext=".rar", tools=("rar",)),
)
_FORMAT_BY_ID: dict[str, ArchiveFormatSpec] = {spec.id: spec for spec in ARCHIVE_FORMATS}


def _resolve_tool(spec: ArchiveFormatSpec) -> str | None:
    for tool in spec.tools:
        path = shutil.which(tool)
        if path is not None:
            return path
    return None


def is_archive_format_available(fmt: str) -> bool:
    spec = _FORMAT_BY_ID.get(fmt)
    if spec is None:
        return False
    if not spec.tools:
        return True  # нативный (shutil)
    return _resolve_tool(spec) is not None


def archive_ext(fmt: str) -> str:
    spec = _FORMAT_BY_ID.get(fmt)
    if spec is None:
        raise ValueError(f"Unknown archive format: {fmt!r}")
    return spec.ext


def available_archive_formats() -> list[dict[str, object]]:
    """Каталог для API: id, label, ext, available. Питает селектор формата в UI."""
    return [
        {"id": spec.id, "label": spec.label, "ext": spec.ext, "available": is_archive_format_available(spec.id)}
        for spec in ARCHIVE_FORMATS
    ]


def _contained(base: Path, rel: str) -> Path | None:
    """Путь ``rel`` под ``base``; None, если он выходит за ``base``.

    resolve() сворачивает ``..`` и идет по символьным ссылкам существующего
    префикса, так что побег через ссылку тоже ловится.
    """
    candidate = base / rel
    try:
        resolved = candidate.resolve()
        base_resolved = base.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(base_resolved):
        return None
    return candidate


class SourceEscapesError(OSError):
    """Исходник записи лежит вне рабочей папки (например, символьная ссылка наружу)."""


def resolve_source(workspace: Path, rel: str) -> Path:
    """Путь исходника под ``workspace``; символьная ссылка наружу не пускается."""
    path = _contained(workspace, rel)
    if path is None:
        raise SourceEscapesError(f"source escapes the workspace: {rel!r}")
    return path


def stamp_from_spec(spec: StampSpec, workspace: Path) -> Stamp:
    return Stamp(
        page=spec.page,
        x_mm=spec.x_mm,
        y_mm=spec.y_mm,
        width_mm=spec.width_mm,
        png_path=resolve_source(workspace, spec.png.path) if spec.png is not None else None,
        aspect_ratio=spec.aspect_ratio,
        text=spec.text,
        details=spec.details,
        subtitle=spec.subtitle,
        date_label=spec.date_label,
        date_text=spec.date_text,
    )


@dataclass(frozen=True)
class ExecutedPack:
    folder: Path
    written: tuple[str, ...]
    skipped: tuple[PackSkip, ...]


class PackExecutor:
    """Кладет записи плана в папку пакета и упаковывает ее в архив.

    Исходные файлы проекта не меняются: штампы рисуются в копию в папке пакета.
    """

    def __init__(self, pdf_stamper: PdfStamper | None = None) -> None:
        self._pdf_stamper = pdf_stamper or PdfStamper()

    def execute(self, workspace: Path, payload: PackSubmissionPayload) -> ExecutedPack:
        """Создает папку пакета и применяет записи по порядку.

        Запись, выходящая за папку, и запись с ошибкой записи пропускаются: в лог и в
        `skipped`, остальные продолжают, кроме критичных записей (`critical`): их сбой
        записи идет наверх. Ошибки штампера, не связанные с диском, тоже идут наверх.
        """
        folder = workspace / SUBMISSIONS_DIR / payload.base_name
        folder.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        skipped: list[PackSkip] = []
        for entry in payload.entries:
            target = _contained(folder, entry.arcname)
            if target is None:
                logger.warning("assembler: doc output_name escapes folder", arcname=entry.arcname)
                skipped.append(PackSkip(arcname=entry.arcname, reason=REASON_ARCNAME_ESCAPES))
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                self._apply(entry, target, workspace)
            except OSError as exc:
                logger.warning(
                    "assembler: error adding doc", source=self._source_for_log(entry, workspace), exc=str(exc)
                )
                if entry.critical:
                    # Замороженный PDF и подписи нельзя терять молча: запрос падает, как и раньше.
                    raise
                reason = REASON_SOURCE_ESCAPES if isinstance(exc, SourceEscapesError) else REASON_WRITE_FAILED
                skipped.append(PackSkip(arcname=entry.arcname, reason=reason, detail=str(exc)))
                continue
            written.append(entry.arcname)
            logger.debug(
                "assembler: added doc",
                source=self._source_for_log(entry, workspace),
                arcname=entry.arcname,
                stamps=len(entry.stamps),
            )
        return ExecutedPack(folder=folder, written=tuple(written), skipped=tuple(skipped))

    @staticmethod
    def _source_for_log(entry: PackEntry, workspace: Path) -> str:
        return str(workspace / entry.source.path) if entry.source is not None else entry.arcname

    def _apply(self, entry: PackEntry, target: Path, workspace: Path) -> None:
        match entry.kind:
            case PackEntryKind.copy:
                assert entry.source is not None  # noqa: S101 — инвариант PackEntry
                shutil.copyfile(resolve_source(workspace, entry.source.path), target)
            case PackEntryKind.stamp_pdf:
                assert entry.source is not None  # noqa: S101 — инвариант PackEntry
                stamps = [stamp_from_spec(spec, workspace) for spec in entry.stamps]
                self._pdf_stamper.stamp(resolve_source(workspace, entry.source.path), target, stamps)
            case PackEntryKind.text:
                assert entry.text is not None  # noqa: S101 — инвариант PackEntry
                target.write_text(entry.text, encoding="utf-8")
            case PackEntryKind.blob:
                assert entry.blob is not None  # noqa: S101 — инвариант PackEntry
                target.write_bytes(entry.blob.to_bytes())

    def create_archive(self, src_dir: Path, dest_base: Path, fmt: str) -> Path:
        """Упаковывает ``src_dir`` в ``dest_base`` + расширение; возвращает путь архива.

        ValueError для неизвестного формата и для 7z/rar без установленной утилиты.
        """
        spec = _FORMAT_BY_ID.get(fmt)
        if spec is None:
            raise ValueError(f"Unknown archive format: {fmt!r}")

        dest_base.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "zip":
            return Path(shutil.make_archive(str(dest_base), "zip", root_dir=str(src_dir)))
        if fmt == "targz":
            return Path(shutil.make_archive(str(dest_base), "gztar", root_dir=str(src_dir)))

        tool = _resolve_tool(spec)
        if tool is None:
            raise ValueError(
                f"Archive format {fmt!r} requires an external tool ({'/'.join(spec.tools)}) which is not installed"
            )
        dest = dest_base.with_name(dest_base.name + spec.ext)
        names = [p.name for p in sorted(src_dir.iterdir())]
        cmd = [tool, "a", str(dest), *names]
        result = subprocess.run(  # noqa: S603 — tool path comes from shutil.which, args are local filenames
            cmd,
            cwd=str(src_dir),
            capture_output=True,
            text=True,
            timeout=_EXTERNAL_TIMEOUT_SEC,
            check=False,
        )
        if result.returncode != 0 or not dest.exists():
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise ValueError(f"{fmt} archiving failed: {detail}")
        return dest
