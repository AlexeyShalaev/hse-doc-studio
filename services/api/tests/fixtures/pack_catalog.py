"""Паки на диске для тестов каталогов паков (срез T17): пак с выпущенными версиями и хранилище на его основе."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from hse_doc_studio.core.catalog import PackOrigin, PackOriginKind
from hse_doc_studio.core.pack_catalog.store import CatalogState, StoredPack, StoredTemplate, StoredVersion
from hse_doc_studio.infra.pack_catalog.store import PacksStore
from hse_doc_studio.infra.template.releases import freeze, version_digest

_VERSION_YAML = """\
id: "{version}"
status: {status}
summary: {{ ru: "Версия {version}", en: "Version {version}" }}
langs: [ru]
{extra}"""


def write_version(template_dir: Path, version: str, *, body: str = "", status: str = "stable", extra: str = "") -> Path:
    version_dir = template_dir / "versions" / version
    (version_dir / "files" / "report").mkdir(parents=True, exist_ok=True)
    (version_dir / "version.yaml").write_text(
        _VERSION_YAML.format(version=version, status=status, extra=extra), encoding="utf-8"
    )
    (version_dir / "files" / "report" / "main.tex").write_text(
        f"\\documentclass{{article}}\n% {version} {body}\n", encoding="utf-8"
    )
    return version_dir


def write_pack(  # noqa: PLR0913 — пак собирается из явных частей
    root: Path,
    pack_id: str = "acme",
    template: str = "report",
    *,
    released: Iterable[str] = ("2026.1.0",),
    drafts: Iterable[str] = (),
    name: str = "Паки Acme",
    body: str = "",
) -> Path:
    """Пак `root/<pack_id>` с шаблоном и версиями; `released` внесены в реестр настоящим `freeze`."""
    pack_dir = root / pack_id
    template_dir = pack_dir / "templates" / template
    template_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "pack.yaml").write_text(f'id: {pack_id}\nname: {{ ru: "{name}", en: "Acme" }}\n', encoding="utf-8")
    released = tuple(released)
    default = released[-1] if released else ""
    (template_dir / "template.yaml").write_text(
        f'id: {template}\nname: {{ ru: "Отчёт", en: "Report" }}\ndefault_version: "{default}"\n', encoding="utf-8"
    )
    for version in released:
        write_version(template_dir, version, body=body)
        freeze(template_dir, version, replace=True)
    for version in drafts:
        write_version(template_dir, version, status="beta", body=body)
    return pack_dir


def subscribe(
    store: PacksStore,
    pack_dir: Path,
    *,
    source_id: str = "src-1",
    listed: bool = True,
    replaces_builtin: bool = False,
    revision: int | None = None,
) -> CatalogState:
    """Все версии каталога пака кладутся в хранилище, пак в `catalog.json` (без конвейера проверки)."""
    pack_id = pack_dir.name
    meta = store.put_meta(pack_id, None, "pack.yaml", (pack_dir / "pack.yaml").read_bytes())
    templates: list[StoredTemplate] = []
    for template_dir in sorted((pack_dir / "templates").iterdir()):
        tpl_meta = store.put_meta(
            pack_id, template_dir.name, "template.yaml", (template_dir / "template.yaml").read_bytes()
        )
        versions = []
        for version_dir in sorted((template_dir / "versions").iterdir()):
            digest = version_digest(version_dir)
            rel = store.put_version(version_dir, pack_id, template_dir.name, version_dir.name, digest)
            versions.append(StoredVersion(version=version_dir.name, digest=digest, dir=rel))
        templates.append(StoredTemplate(id=template_dir.name, meta=tpl_meta, versions=tuple(versions)))
    state = store.read()
    origin = PackOrigin(
        kind=PackOriginKind.subscribed,
        source_id=source_id,
        source_kind="git",
        label="acme-packs",
        replaces_builtin=replaces_builtin,
    )
    pack = StoredPack(
        id=pack_id, meta=meta, source_id=source_id, origin=origin, templates=tuple(templates), listed=listed
    )
    new = CatalogState(
        revision=revision if revision is not None else state.revision + 1,
        packs=(*(p for p in state.packs if p.id != pack_id), pack),
    )
    store.write(new)
    return new
