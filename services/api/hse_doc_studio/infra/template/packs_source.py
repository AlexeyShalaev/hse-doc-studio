"""Опись вшитых паков и проверка, не подменён ли каталог шаблонов.

Сборка образа пишет опись (`write_manifest`) рядом с паками, но вне каталога
`/app/packs`: смонтированная поверх него папка закрывает и сами паки, и всё,
что лежало бы внутри. Опись остаётся видна, и по ней Студия знает, какие
версии шаблонов вшиты именно в неё.

Подмену видно двумя способами: каталог (или папка над ним) значится точкой
монтирования в `/proc/self/mountinfo`, или `HSE_STUDIO__PACKS_DIR` указывает
не туда, куда сборка положила паки.

Запуск как скрипт пишет опись (так её вызывает Dockerfile):

    python -m hse_doc_studio.infra.template.packs_source <packs_dir> <manifest.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import structlog

from hse_doc_studio import __version__ as studio_version
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.template_packs import PacksSource, TemplateKey, classify_packs
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository

logger = structlog.get_logger()

MOUNTINFO = Path("/proc/self/mountinfo")
_MANIFEST_FORMAT = 1


def template_keys(repo: ITemplateRepository) -> frozenset[TemplateKey]:
    keys: set[TemplateKey] = set()
    for pack in repo.list_packs():
        for template in pack.templates:
            keys.update(TemplateKey(pack.id, template.id, v) for v in repo.list_versions(pack.id, template.id))
    return frozenset(keys)


def write_manifest(packs_dir: Path, out: Path) -> dict[str, Any]:
    repo = YamlTemplateRepository(packs_dir)
    repo.load()
    data = {
        "format": _MANIFEST_FORMAT,
        "studio_version": studio_version,
        "packs_dir": str(PurePosixPath(packs_dir)),
        "templates": [
            {"pack_id": k.pack_id, "template_id": k.template_id, "version": k.version}
            for k in sorted(template_keys(repo))
        ],
    }
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def read_manifest(path: Path | None) -> tuple[str, str | None, frozenset[TemplateKey]] | None:
    """(каталог паков при сборке, версия Студии, версии шаблонов); None — описи нет или она нечитаема."""
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = frozenset(
            TemplateKey(str(t["pack_id"]), str(t["template_id"]), str(t["version"])) for t in data["templates"]
        )
        return str(data["packs_dir"]), (str(data.get("studio_version") or "") or None), keys
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("packs manifest unreadable", path=str(path), error=str(exc))
        return None


def _unescape_mount_path(raw: str) -> str:
    # mountinfo экранирует пробел, табуляцию, перевод строки и обратную косую восьмеричными кодами.
    return raw.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def mount_points(mountinfo: str) -> list[str]:
    """Точки монтирования из текста `/proc/self/mountinfo` (пятое поле строки)."""
    points: list[str] = []
    for line in mountinfo.splitlines():
        fields = line.split(" ")
        if len(fields) > 4:  # noqa: PLR2004 — формат mountinfo: точка монтирования в пятом поле
            points.append(_unescape_mount_path(fields[4]))
    return points


def is_mounted_over(path: str, points: list[str]) -> bool:
    """Каталог или папка над ним (кроме корня) смонтированы поверх файловой системы образа."""
    target = PurePosixPath(path)
    for point in points:
        mount = PurePosixPath(point)
        if str(mount) == "/":
            continue
        if target == mount or mount in target.parents:
            return True
    return False


def _read_mount_points(mountinfo: Path) -> list[str]:
    try:
        return mount_points(mountinfo.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []


class FilesystemPacksSource:
    """`ITemplatePacksSource` по манифесту образа и таблице монтирования процесса."""

    def __init__(
        self,
        packs_dir: Path,
        templates: ITemplateRepository,
        manifest: Path | None,
        mountinfo: Path = MOUNTINFO,
    ) -> None:
        self._packs_dir = packs_dir
        self._templates = templates
        self._manifest = manifest
        self._mountinfo = mountinfo
        self._cached: PacksSource | None = None

    def describe(self) -> PacksSource:
        if self._cached is None:
            self._cached = self._build()
        return self._cached

    def _build(self) -> PacksSource:
        path = str(PurePosixPath(self._packs_dir)) if self._packs_dir.is_absolute() else str(self._packs_dir)
        manifest = read_manifest(self._manifest)
        mounted = is_mounted_over(path, _read_mount_points(self._mountinfo))
        builtin_dir, builtin_studio, builtin = manifest if manifest is not None else (None, None, None)
        source = PacksSource(
            path=path,
            kind=classify_packs(packs_dir=path, builtin_dir=builtin_dir, mounted=mounted),
            mounted=mounted,
            builtin=builtin,
            builtin_studio=builtin_studio,
            available=template_keys(self._templates),
        )
        if source.missing_builtin:
            logger.warning(
                "external packs dir lags behind this studio",
                path=path,
                studio=studio_version,
                missing=[f"{k.pack_id}/{k.template_id}@{k.version}" for k in source.missing_builtin],
            )
        return source


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:  # noqa: PLR2004 — два позиционных аргумента
        sys.stderr.write("usage: python -m hse_doc_studio.infra.template.packs_source <packs_dir> <manifest.json>\n")
        return 2
    data = write_manifest(Path(args[0]), Path(args[1]))
    sys.stdout.write(f"packs manifest: {len(data['templates'])} template versions\n")
    return 0 if data["templates"] else 1


if __name__ == "__main__":
    sys.exit(main())
