"""Пак и шаблон с нуля над папкой паков рабочего пространства (порт `IPackScaffolder`, раздел 8, срез T15).

- «Минимальный»: заготовка `scaffolds/minimal` (манифест версии, документ «Отчёт» по ГОСТ 7.32 с титулом,
  `meta.tex.j2`), в манифесте версии подставляются номер и даты.
- «Копия»: каталог выбранной версии целиком, манифест версии черновиком тем же кодом, что у мастера «Новая версия»
  (`draft_manifest`: `id`, `status: beta`, `released_at` сегодня, без `release`, заметки пусты). Примеры данных
  предпросмотра шаблона-источника (`examples/`) едут следом: они синтетические и вне версии.
- Манифесты пака и шаблона пишутся заново (их комментарии описывают источник, а не новый пак); у копии в них
  комментарий с атрибуцией источника: лицензия Apache-2.0 и подобные требуют её сохранить.
- Реестр выпусков нового шаблона пуст (`releases: {}`).

Каталог собирается во временной папке рядом с целевой и переносится одним `rename`: при отказе на полпути ничего не
остаётся. Символьные ссылки в источнике копии отвергаются (раздел 9), служебный мусор ОС пропускается.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unicodedata
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import TEMPLATES_DIR, VersionRef
from hse_doc_studio.core.pack_studio.scaffold import (
    CopySource,
    NewPack,
    NewTemplate,
    ScaffoldResult,
    ScaffoldSource,
    SourceMeta,
    SourceOrigin,
    SourcePack,
    SourceTemplate,
    SourceVersion,
)
from hse_doc_studio.infra.pack_studio.layout import (
    PACK_MANIFEST,
    TEMPLATE_MANIFEST,
    VERSION_MANIFEST,
    VERSIONS_DIR,
    template_versions,
)
from hse_doc_studio.infra.pack_studio.versions import draft_manifest
from hse_doc_studio.infra.pack_studio.yaml_edits import YamlEditError, set_value
from hse_doc_studio.infra.template.releases import load_releases, write_releases

SCAFFOLDS_DIR = Path(__file__).parent / "scaffolds"
MINIMAL_DIR = SCAFFOLDS_DIR / "minimal"
EXAMPLES_DIR = "examples"
_JUNK = frozenset({"__pycache__", ".DS_Store", "Thumbs.db", "desktop.ini"})
# Поля `template.yaml` источника, которые копия берёт себе (имена и описание задаёт человек).
TEMPLATE_FIELDS = ("icon", "accent_hue", "author_group_placeholder")
_DEFAULT_ICON = "FileText"
_DEFAULT_HUE = 200


def _fold(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _q(value: str) -> str:
    """Строка YAML в двойных кавычках: JSON-строка это корректный скаляр YAML."""
    return json.dumps(value, ensure_ascii=False)


def _load(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _localized(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if isinstance(v, str | int | float)}
    return {"ru": str(raw), "en": str(raw)} if isinstance(raw, str) else {}


def _localized_yaml(key: str, value: Mapping[str, str]) -> list[str]:
    return [f"{key}:", f"  ru: {_q(value.get('ru', ''))}", f"  en: {_q(value.get('en', ''))}"]


def _maintainer_name(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("name") or "")
    return str(raw) if isinstance(raw, str) else ""


def _child(parent: Path, name: str) -> Path | None:
    """Папка `name` внутри `parent` без учёта регистра (не ссылка); None, если такой нет."""
    if not parent.is_dir() or parent.is_symlink():
        return None
    wanted = _fold(name)
    for child in parent.iterdir():
        if _fold(child.name) == wanted and child.is_dir() and not child.is_symlink():
            return child
    return None


def _names(parent: Path) -> frozenset[str]:
    if not parent.is_dir():
        return frozenset()
    return frozenset(_fold(child.name) for child in parent.iterdir())


def _attribution(meta: SourceMeta) -> list[str]:
    name = meta.pack_name.get("ru") or meta.pack_name.get("en") or meta.pack
    lines = [
        f"# Основан на паке {meta.pack} ({name}): шаблон {meta.template}, версия {meta.version}.",
    ]
    details = []
    if meta.license:
        details.append(f"лицензия {meta.license}")
    if meta.maintainer:
        details.append(f"сопровождающий {meta.maintainer}")
    if details:
        lines.append("# Исходный пак: " + ", ".join(details) + ".")
    lines.append("# Сохраните эту атрибуцию: её требует лицензия исходного пака.")
    return lines


class PackScaffolder:
    """Реализация `IPackScaffolder` (core/pack_studio/protocols.py)."""

    def __init__(self, *, max_files: int, max_bytes: int) -> None:
        self._max_files = max_files
        self._max_bytes = max_bytes

    # ── чтение ───────────────────────────────────────────────────────────────

    def pack_dirs(self, root: Path) -> frozenset[str]:
        return _names(root)

    def sources(self, root: Path) -> tuple[SourcePack, ...]:
        packs: list[SourcePack] = []
        for pack_dir in sorted(root.iterdir() if root.is_dir() else (), key=lambda p: p.name):
            if pack_dir.name.startswith(".") or pack_dir.is_symlink() or not (pack_dir / PACK_MANIFEST).is_file():
                continue
            manifest = _load(pack_dir / PACK_MANIFEST)
            templates = tuple(self._templates(pack_dir))
            if not templates:
                continue
            packs.append(
                SourcePack(
                    origin=SourceOrigin.workspace,
                    pack=pack_dir.name,
                    name=_localized(manifest.get("name")),
                    license=str(manifest.get("license") or ""),
                    templates=templates,
                )
            )
        return tuple(packs)

    def _templates(self, pack_dir: Path) -> list[SourceTemplate]:
        root = pack_dir / TEMPLATES_DIR
        if not root.is_dir() or root.is_symlink():
            return []
        found: list[SourceTemplate] = []
        for template_dir in sorted(root.iterdir(), key=lambda p: p.name):
            if template_dir.name.startswith(".") or template_dir.is_symlink() or not template_dir.is_dir():
                continue
            versions = template_versions(template_dir)
            if not versions:
                continue
            manifest = _load(template_dir / TEMPLATE_MANIFEST)
            default = str(manifest["default_version"]) if manifest.get("default_version") is not None else None
            released = load_releases(template_dir)
            found.append(
                SourceTemplate(
                    template=template_dir.name,
                    name=_localized(manifest.get("name")),
                    default_version=default,
                    versions=tuple(
                        SourceVersion(
                            version=v,
                            status=_status(template_dir / VERSIONS_DIR / v),
                            released=v in released,
                            default=v == default,
                        )
                        for v in reversed(versions)
                    ),
                )
            )
        return found

    def workspace_source(self, root: Path, source: ScaffoldSource) -> CopySource:
        pack_dir = _child(root, source.pack)
        template_dir = _child(pack_dir / TEMPLATES_DIR, source.template) if pack_dir else None
        version_dir = _child(template_dir / VERSIONS_DIR, source.version) if template_dir else None
        if pack_dir is None or template_dir is None or version_dir is None:
            raise PackStudioError(PackStudioErrorCode.version_not_found, version=source.version)
        if not (version_dir / VERSION_MANIFEST).is_file():
            raise PackStudioError(PackStudioErrorCode.version_not_found, version=source.version)
        pack = _load(pack_dir / PACK_MANIFEST)
        template = _load(template_dir / TEMPLATE_MANIFEST)
        examples = template_dir / EXAMPLES_DIR
        return CopySource(
            origin=SourceOrigin.workspace,
            version_dir=version_dir,
            examples_dir=examples if examples.is_dir() and not examples.is_symlink() else None,
            meta=SourceMeta(
                pack=pack_dir.name,
                template=template_dir.name,
                version=version_dir.name,
                pack_name=_localized(pack.get("name")),
                license=str(pack.get("license") or ""),
                maintainer=_maintainer_name(pack.get("maintainer")),
                template_fields={k: template[k] for k in TEMPLATE_FIELDS if template.get(k) is not None},
            ),
        )

    # ── создание ─────────────────────────────────────────────────────────────

    def create_pack(
        self, root: Path, pack: NewPack, *, version: str, today: date, source: CopySource | None
    ) -> ScaffoldResult:
        if _fold(pack.id) in self.pack_dirs(root):
            raise PackStudioError(PackStudioErrorCode.pack_id_taken, id=pack.id, where="workspace")
        staging = Path(tempfile.mkdtemp(prefix=".new-pack-", dir=root))
        try:
            pack_dir = staging / pack.id
            template_dir = pack_dir / TEMPLATES_DIR / pack.template.id
            template_dir.mkdir(parents=True)
            _write(pack_dir / PACK_MANIFEST, _pack_yaml(pack, today, source))
            files = self._fill_template(template_dir, pack.template, version, today, source, attribution=False)
            target = root / pack.id
            if target.exists():
                raise PackStudioError(PackStudioErrorCode.pack_id_taken, id=pack.id, where="workspace")
            pack_dir.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return self._result(root, target, pack.template.id, version, files + 1, source, pack_created=True)

    def create_template(  # noqa: PLR0913 — пак, шаблон, номер и источник
        self, root: Path, pack: str, template: NewTemplate, *, version: str, today: date, source: CopySource | None
    ) -> ScaffoldResult:
        pack_dir = _child(root, pack)
        if pack_dir is None or not (pack_dir / PACK_MANIFEST).is_file():
            raise PackStudioError(PackStudioErrorCode.pack_not_found, pack=pack)
        templates = pack_dir / TEMPLATES_DIR
        if templates.is_symlink():
            raise PackStudioError(PackStudioErrorCode.path_not_allowed)
        templates.mkdir(exist_ok=True)
        if _fold(template.id) in _names(templates):
            raise PackStudioError(PackStudioErrorCode.template_id_taken, id=template.id)
        staging = Path(tempfile.mkdtemp(prefix=".new-template-", dir=templates))
        try:
            template_dir = staging / template.id
            template_dir.mkdir()
            files = self._fill_template(template_dir, template, version, today, source, attribution=True)
            target = templates / template.id
            if target.exists():
                raise PackStudioError(PackStudioErrorCode.template_id_taken, id=template.id)
            template_dir.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return self._result(root, pack_dir, template.id, version, files, source, pack_created=False)

    def _fill_template(  # noqa: PLR0913 — каталог, шаблон, номер, день, источник и атрибуция
        self,
        template_dir: Path,
        template: NewTemplate,
        version: str,
        today: date,
        source: CopySource | None,
        *,
        attribution: bool,
    ) -> int:
        """Манифест шаблона, пустой реестр выпусков и каталог версии; число записанных файлов."""
        meta = source.meta if source is not None else None
        _write(template_dir / TEMPLATE_MANIFEST, _template_yaml(template, version, meta, attribution=attribution))
        write_releases(template_dir, {})
        version_dir = template_dir / VERSIONS_DIR / version
        if source is None:
            files = self._copy_tree(MINIMAL_DIR, version_dir)
            manifest = version_dir / VERSION_MANIFEST
            _write(manifest, _minimal_manifest(manifest.read_text(encoding="utf-8"), version, today))
        else:
            files = self._copy_tree(source.version_dir, version_dir)
            manifest = version_dir / VERSION_MANIFEST
            try:
                draft = draft_manifest(manifest.read_bytes().decode("utf-8"), version, today)
                draft = _first_notes(draft, source.meta)
            except (UnicodeDecodeError, YamlEditError, yaml.YAMLError, ValueError) as exc:
                raise PackStudioError(PackStudioErrorCode.version_unreadable, reason=str(exc)[:300]) from None
            _write(manifest, draft)
            examples = source.examples_dir
            if examples is not None and examples.is_dir() and not examples.is_symlink():
                files += self._copy_tree(examples, template_dir / EXAMPLES_DIR, budget=files)
        return files + 2

    def _copy_tree(self, source: Path, target: Path, *, budget: int = 0) -> int:
        """Копия каталога без ссылок и мусора ОС в пределах числа файлов и байт; число файлов."""
        count = budget
        size = 0
        for current, dirs, names in os.walk(source, followlinks=False):
            base = Path(current)
            rel = base.relative_to(source)
            dirs[:] = sorted(d for d in dirs if d not in _JUNK)
            for name in [*dirs, *names]:
                if (base / name).is_symlink():
                    raise PackStudioError(PackStudioErrorCode.path_not_allowed, path=(rel / name).as_posix())
            (target / rel).mkdir(parents=True, exist_ok=True)
            for name in sorted(names):
                if name in _JUNK:
                    continue
                count += 1
                size += (base / name).stat().st_size
                if count > self._max_files or size > self._max_bytes:
                    raise PackStudioError(PackStudioErrorCode.workspace_too_large)
                shutil.copyfile(base / name, target / rel / name)
        return count - budget

    @staticmethod
    def _result(  # noqa: PLR0913 — поля итога
        root: Path,
        pack_dir: Path,
        template: str,
        version: str,
        files: int,
        source: CopySource | None,
        *,
        pack_created: bool,
    ) -> ScaffoldResult:
        ref = VersionRef(pack_dir.name, template, version)
        template_rel = f"{pack_dir.name}/{TEMPLATES_DIR}/{template}"
        manifests = [f"{template_rel}/{TEMPLATE_MANIFEST}", f"{ref.dir}/{VERSION_MANIFEST}"]
        if pack_created:
            manifests.insert(0, f"{pack_dir.name}/{PACK_MANIFEST}")
        main = _main_file(root / ref.dir)
        return ScaffoldResult(
            ref=ref,
            manifests=tuple(manifests),
            main_file=f"{ref.dir}/{main}" if main else None,
            files=files,
            source=(
                ScaffoldSource(source.origin, source.meta.pack, source.meta.template, source.meta.version)
                if source is not None
                else None
            ),
            pack_created=pack_created,
        )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _status(version_dir: Path) -> str | None:
    raw = _load(version_dir / VERSION_MANIFEST).get("status")
    return str(raw) if raw is not None else None


def _minimal_manifest(text: str, version: str, today: date) -> str:
    return (
        text.replace("@@VERSION@@", version)
        .replace("@@TODAY@@", today.isoformat())
        .replace("@@NEXT_YEAR@@", str(today.year + 1))
    )


def _first_notes(text: str, meta: SourceMeta) -> str:
    """Заметки первой версии копии: линтер требует непустые `changes` ru и en, черновик их опустошил."""
    notes = {
        "ru": [f"Первая версия шаблона: копия {meta.pack}/{meta.template} {meta.version}."],
        "en": [f"The first version of the template: a copy of {meta.pack}/{meta.template} {meta.version}."],
    }
    data = yaml.safe_load(text) or {}
    if isinstance(data, dict) and isinstance(data.get("changes"), dict):
        for lang, items in notes.items():
            text = set_value(text, ("changes", lang), items, block=True)
        return text
    return set_value(text, ("changes",), notes, block=True)


def _pack_yaml(pack: NewPack, today: date, source: CopySource | None) -> str:
    lines = [f"# Манифест пака {pack.id}. Справка по ключам: docs/ru/reference/pack.md."]
    if source is not None:
        lines += _attribution(source.meta)
    lines += ["", f"id: {pack.id}", *_localized_yaml("name", pack.name)]
    if pack.description:
        lines += _localized_yaml("description", pack.description)
    maintainer = pack.maintainer
    if maintainer is not None and maintainer.name:
        lines += ["", "maintainer:", f"  name: {_q(maintainer.name)}"]
        if maintainer.email:
            lines.append(f"  email: {_q(maintainer.email)}")
        if maintainer.url:
            lines.append(f"  url: {_q(maintainer.url)}")
    lines += ["", f"license: {_q(pack.license)}"]
    if pack.source:
        lines.append(f"source: {_q(pack.source)}")
    lines.append(f"created_at: {today.isoformat()}")
    return "\n".join(lines) + "\n"


def _template_yaml(template: NewTemplate, version: str, meta: SourceMeta | None, *, attribution: bool) -> str:
    lines = [f"# Манифест шаблона {template.id}: не зависит от версии."]
    if meta is not None and attribution:
        lines += _attribution(meta)
    lines += ["", f"id: {template.id}", *_localized_yaml("name", template.name)]
    if template.short_name:
        lines += _localized_yaml("short_name", template.short_name)
    if template.description:
        lines += _localized_yaml("description", template.description)
    fields = dict(meta.template_fields) if meta is not None else {}
    icon = fields.get("icon")
    hue = fields.get("accent_hue")
    lines += [
        "",
        f"icon: {_q(str(icon) if isinstance(icon, str) and icon else _DEFAULT_ICON)}",
        f"accent_hue: {hue if isinstance(hue, int) and not isinstance(hue, bool) else _DEFAULT_HUE}",
        "",
        f"default_version: {_q(version)}",
    ]
    placeholder = fields.get("author_group_placeholder")
    if isinstance(placeholder, str) and placeholder:
        lines.append(f"author_group_placeholder: {_q(placeholder)}")
    return "\n".join(lines) + "\n"


def _main_file(version_dir: Path) -> str | None:
    """Исходник первого документа версии от каталога версии (с языковым суффиксом, если без него файла нет)."""
    manifest = _load(version_dir / VERSION_MANIFEST)
    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        return VERSION_MANIFEST
    first = documents[0]
    doc_id = first.get("id") if isinstance(first, dict) else first
    if not isinstance(doc_id, str):
        return VERSION_MANIFEST
    source_file = _load(version_dir / "files" / doc_id / "doc.yaml").get("source_file")
    if not isinstance(source_file, str) or not source_file:
        return VERSION_MANIFEST
    candidate = Path("files") / source_file
    if (version_dir / candidate).is_file():
        return candidate.as_posix()
    raw_langs = manifest.get("langs")
    langs = [str(lang) for lang in raw_langs] if isinstance(raw_langs, list) else []
    for lang in [*langs, "ru", "en"]:
        suffixed = candidate.with_name(f"{candidate.stem}.{lang}{candidate.suffix}")
        if (version_dir / suffixed).is_file():
            return suffixed.as_posix()
    return VERSION_MANIFEST
