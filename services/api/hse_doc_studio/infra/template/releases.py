r"""Реестр выпущенных версий шаблона и их неизменность.

Выпущенная версия — снимок требований: проекты читают её манифест (проверки,
профили сдачи, слоты подписей, шаблоны dynamic include) вживую по `lock.version`,
поэтому правка выпущенного каталога на месте молча меняет существующие проекты.
Чтобы этого не случалось, у каждого шаблона есть `releases.yaml`:

    releases:
      "2026.1":
        digest: sha256:…
        kind: major

`digest` — хеш всего каталога версии (version.yaml, checks/, files/). Тест
`tests/unit/infra/template/test_releases.py` пересчитывает его для всех паков репозитория и падает
при любой правке выпущенного каталога. Исправление — новая версия (patch).

Хеш не зависит от платформы: в текстовых файлах (без NUL-байтов) CRLF приводится
к LF, иначе checkout на Windows с autocrlf давал бы другой дайджест.

CLI:
  `python -m hse_doc_studio.infra.template.releases check <каталог шаблона>…`
  `python -m hse_doc_studio.infra.template.releases freeze <каталог шаблона> <версия> [--kind patch]`
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
import yaml

from hse_doc_studio.core.enums import TemplateUpdateClass

logger = structlog.get_logger()

RELEASES_FILE = "releases.yaml"
DIGEST_PREFIX = "sha256:"

# Мусор файловых менеджеров и интерпретатора — не содержимое версии.
_JUNK_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
_JUNK_DIRS = frozenset({"__pycache__"})

_HEADER = """\
# Выпущенные версии шаблона. Каталог выпущенной версии НЕИЗМЕНЕН: проекты читают
# её манифест вживую, правка на месте молча поменяла бы их требования. Тест
# test_releases.py пересчитывает дайджесты и падает при любой правке.
# Исправление — новая версия (patch), см. core/template_versions.py.
# Внести версию: python -m hse_doc_studio.infra.template.releases freeze <каталог шаблона> <версия>
"""


@dataclass(frozen=True)
class ReleaseEntry:
    version: str
    digest: str
    kind: TemplateUpdateClass | None = None


def _content_for_digest(data: bytes) -> bytes:
    if b"\x00" in data:
        return data
    return data.replace(b"\r\n", b"\n")


def _iter_version_files(version_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in version_dir.rglob("*"):
        if not path.is_file() or path.name in _JUNK_NAMES:
            continue
        if any(part in _JUNK_DIRS for part in path.relative_to(version_dir).parts):
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(version_dir).as_posix())


def version_digest(version_dir: Path) -> str:
    """Дайджест содержимого каталога версии (пути + содержимое файлов)."""
    outer = hashlib.sha256()
    for path in _iter_version_files(version_dir):
        rel = path.relative_to(version_dir).as_posix()
        inner = hashlib.sha256(_content_for_digest(path.read_bytes())).hexdigest()
        outer.update(f"{rel}\0{inner}\n".encode())
    return DIGEST_PREFIX + outer.hexdigest()


def _parse_kind(raw: Any) -> TemplateUpdateClass | None:
    try:
        return TemplateUpdateClass(str(raw)) if raw else None
    except ValueError:
        return None


def load_releases(template_dir: Path) -> dict[str, ReleaseEntry]:
    """Реестр выпусков шаблона; пустой, если файла нет или он битый."""
    path = template_dir / RELEASES_FILE
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("releases.yaml read error", path=str(path), exc=str(exc))
        return {}
    raw = data.get("releases") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}
    entries: dict[str, ReleaseEntry] = {}
    for version, item in raw.items():
        if not isinstance(item, dict) or not item.get("digest"):
            continue
        entries[str(version)] = ReleaseEntry(
            version=str(version), digest=str(item["digest"]), kind=_parse_kind(item.get("kind"))
        )
    return entries


def _write_releases(template_dir: Path, entries: dict[str, ReleaseEntry]) -> None:
    body: dict[str, Any] = {
        "releases": {
            e.version: {"digest": e.digest, **({"kind": e.kind.value} if e.kind else {})}
            for e in sorted(entries.values(), key=lambda e: e.version)
        }
    }
    text = _HEADER + yaml.safe_dump(body, allow_unicode=True, sort_keys=False, default_flow_style=False)
    (template_dir / RELEASES_FILE).write_text(text, encoding="utf-8")


def _version_dir(template_dir: Path, version: str) -> Path:
    return template_dir / "versions" / version


def check_template(template_dir: Path) -> list[str]:
    """Ошибки неизменности: выпущенный каталог пропал или изменился."""
    errors: list[str] = []
    for entry in load_releases(template_dir).values():
        version_dir = _version_dir(template_dir, entry.version)
        if not version_dir.is_dir():
            errors.append(f"{template_dir.name}@{entry.version}: каталог выпущенной версии отсутствует")
            continue
        actual = version_digest(version_dir)
        if actual != entry.digest:
            errors.append(
                f"{template_dir.name}@{entry.version}: каталог выпущенной версии изменён "
                f"(ожидался {entry.digest}, сейчас {actual}). Выпущенные версии не правят на месте — "
                f"выпустите новую (patch)."
            )
    return errors


def freeze(template_dir: Path, version: str, kind: TemplateUpdateClass | None = None) -> ReleaseEntry:
    """Внести версию в реестр выпусков (статус в version.yaml должен быть stable)."""
    version_dir = _version_dir(template_dir, version)
    manifest = yaml.safe_load((version_dir / "version.yaml").read_text(encoding="utf-8")) or {}
    status = str(manifest.get("status", "stable"))
    if status not in ("stable", "deprecated"):
        raise ValueError(f"{template_dir.name}@{version}: выпускать можно только stable-версию (сейчас {status})")
    entries = load_releases(template_dir)
    if version in entries:
        raise ValueError(f"{template_dir.name}@{version}: версия уже выпущена — её каталог неизменен")
    entry = ReleaseEntry(version=version, digest=version_digest(version_dir), kind=kind)
    entries[version] = entry
    _write_releases(template_dir, entries)
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="releases", description="Реестр выпущенных версий шаблона")
    sub = parser.add_subparsers(dest="command", required=True)
    check_cmd = sub.add_parser("check", help="проверить неизменность выпущенных версий")
    check_cmd.add_argument("templates", nargs="+", type=Path)
    freeze_cmd = sub.add_parser("freeze", help="внести версию в реестр выпусков")
    freeze_cmd.add_argument("template", type=Path)
    freeze_cmd.add_argument("version")
    freeze_cmd.add_argument("--kind", choices=[c.value for c in TemplateUpdateClass])
    args = parser.parse_args(argv)

    if args.command == "freeze":
        entry = freeze(args.template, args.version, TemplateUpdateClass(args.kind) if args.kind else None)
        sys.stdout.write(f"{args.template.name}@{entry.version}: {entry.digest}\n")
        return 0
    errors = [error for template in args.templates for error in check_template(template)]
    for error in errors:
        sys.stderr.write(f"ERROR {error}\n")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
