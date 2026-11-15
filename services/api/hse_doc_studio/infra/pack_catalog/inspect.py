"""Разбор паков ревизии источника для «Проверить» (порт IRevisionInspector, template-studio.md, 10.3 и раздел 9).

Разбор идёт в отдельном процессе (`call_isolated`: spawn, предел времени и памяти), как предпросмотр чужого пака:
YAML чужого источника разбирается лоадером этой Студии (`YamlTemplateRepository`), выпущенные версии проходят
`pack_lint` (Jinja только разбирается песочницей T3, не исполняется), дайджест каждого каталога считается по файлам
для сверки с `releases.yaml` (`releases check`). В процесс api возвращаются только данные (`InspectedTree`).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml

from hse_doc_studio.core.pack_catalog.entities import (
    InspectedPack,
    InspectedTemplate,
    InspectedTree,
    InspectedVersion,
)
from hse_doc_studio.core.pack_catalog.errors import CatalogError, CatalogErrorCode
from hse_doc_studio.infra.template.jinja_sandbox import IsolatedRenderError, IsolationLimits, call_isolated
from hse_doc_studio.infra.template.pack_lint import lint_version_dir
from hse_doc_studio.infra.template.releases import load_releases, version_digest
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository

PACK_MANIFEST = "pack.yaml"
TEMPLATE_MANIFEST = "template.yaml"
VERSION_MANIFEST = "version.yaml"
_MAX_MESSAGES = 50


def _yaml(path: Path) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def _localized(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    return {"ru": value} if isinstance(value, str) else {}


def inspect_tree(root: str) -> InspectedTree:
    """Разбор корня паков ревизии. Вызывается в дочернем процессе; ничего не пишет."""
    base = Path(root)
    repo = YamlTemplateRepository(base)
    repo.load()
    loaded = {pack.id for pack in repo.list_packs()}
    packs: list[InspectedPack] = []
    for pack_dir in sorted(base.iterdir()) if base.is_dir() else ():
        if not pack_dir.is_dir() or pack_dir.name.startswith(".") or not (pack_dir / PACK_MANIFEST).is_file():
            continue
        packs.append(_inspect_pack(pack_dir, repo, loaded))
    problems = () if packs else ("в папке паков нет ни одного пака (pack.yaml)",)
    return InspectedTree(packs=tuple(packs), problems=problems)


def _inspect_pack(pack_dir: Path, repo: YamlTemplateRepository, loaded: set[str]) -> InspectedPack:
    data = _yaml(pack_dir / PACK_MANIFEST)
    pack_id = str(data.get("id") or "") if data is not None else ""
    problems: list[str] = []
    if data is None or not pack_id:
        problems.append(f"{PACK_MANIFEST} не разобран или в нём нет id")
    elif pack_id != pack_dir.name:
        problems.append(f"id пака {pack_id!r} не совпадает с именем папки {pack_dir.name!r}")
    readable = not problems and pack_id in loaded
    if not problems and not readable:
        problems.append(f"лоадер этой Студии не разобрал {PACK_MANIFEST}")
    templates_dir = pack_dir / "templates"
    templates = tuple(
        _inspect_template(pack_id or pack_dir.name, template_dir, repo)
        for template_dir in (sorted(templates_dir.iterdir()) if templates_dir.is_dir() else ())
        if template_dir.is_dir() and not template_dir.name.startswith(".")
    )
    return InspectedPack(
        id=pack_id or pack_dir.name,
        path=pack_dir.name,
        name=_localized(data.get("name")) if data is not None else {},
        templates=templates,
        problems=tuple(problems),
        readable=readable,
    )


def _inspect_template(pack_id: str, template_dir: Path, repo: YamlTemplateRepository) -> InspectedTemplate:
    data = _yaml(template_dir / TEMPLATE_MANIFEST)
    template_id = str(data.get("id") or "") if data is not None else ""
    problems: list[str] = []
    if data is None or not template_id:
        problems.append(f"{template_dir.name}: {TEMPLATE_MANIFEST} не разобран или в нём нет id")
    elif template_id != template_dir.name:
        problems.append(f"{template_dir.name}: id шаблона {template_id!r} не совпадает с именем папки")
    releases = load_releases(template_dir)
    versions_dir = template_dir / "versions"
    names = {d.name for d in versions_dir.iterdir() if d.is_dir()} if versions_dir.is_dir() else set()
    names |= set(releases)
    versions = tuple(
        _inspect_version(
            pack_id,
            template_dir.name,
            name,
            versions_dir / name,
            releases.get(name),
            repo,
            template_problem=problems[0] if problems else None,
        )
        for name in sorted(names)
    )
    return InspectedTemplate(
        id=template_dir.name,
        path=f"{template_dir.parent.parent.name}/templates/{template_dir.name}",
        versions=versions,
        problems=tuple(problems),
    )


def _inspect_version(  # noqa: PLR0913 — версия и всё, что о ней известно из шаблона
    pack_id: str,
    template_id: str,
    name: str,
    version_dir: Path,
    release: Any,
    repo: YamlTemplateRepository,
    *,
    template_problem: str | None,
) -> InspectedVersion:
    released = release is not None
    if not version_dir.is_dir():
        return InspectedVersion(
            template=template_id,
            version=name,
            released=released,
            registry_digest=release.digest if released else None,
            digest=None,
            kind=release.kind.value if released and release.kind else None,
        )
    manifest = _yaml(version_dir / VERSION_MANIFEST) or {}
    errors: list[str] = [template_problem] if template_problem else []
    warnings: list[str] = []
    if released:
        # Линтер только для выпущенных: в каталог попадают только они, черновики источника не интересны.
        errors_l, warnings_l = _lint(version_dir)
        errors += errors_l
        warnings += warnings_l
        if str(manifest.get("id", name)) != name:
            errors.append(f"id версии {manifest.get('id')!r} не совпадает с именем папки {name!r}")
    try:
        manifest_format: int | None = int(manifest.get("manifest_format", 1))
    except (TypeError, ValueError):
        manifest_format = None
    return InspectedVersion(
        template=template_id,
        version=name,
        released=released,
        registry_digest=release.digest if released else None,
        digest=version_digest(version_dir),
        kind=release.kind.value if released and release.kind else None,
        manifest_format=manifest_format,
        min_studio=str(manifest["min_studio"]) if manifest.get("min_studio") else None,
        readable=repo.get_version(pack_id, template_id, name) is not None,
        errors=tuple(errors[:_MAX_MESSAGES]),
        warnings=tuple(warnings[:_MAX_MESSAGES]),
    )


def _lint(version_dir: Path) -> tuple[list[str], list[str]]:
    try:
        report = lint_version_dir(version_dir)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, TypeError, ValueError) as exc:
        return [f"{VERSION_MANIFEST} не разобран: {exc}"], []
    return list(report.errors), list(report.warnings)


class IsolatedRevisionInspector:
    def __init__(self, *, timeout_s: float, memory_bytes: int) -> None:
        self._limits = IsolationLimits(timeout_seconds=timeout_s, memory_bytes=memory_bytes)

    async def inspect(self, root: Path) -> InspectedTree:
        try:
            return await asyncio.to_thread(call_isolated, inspect_tree, (str(root),), limits=self._limits)
        except IsolatedRenderError as exc:
            raise CatalogError(CatalogErrorCode.inspection_failed, reason=str(exc)) from exc
