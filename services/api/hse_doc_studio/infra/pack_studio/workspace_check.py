"""Проверки рабочего пространства перед «Предложить изменения» (template-studio.md, 4.4 и 4.5; срез T6).

Тот же код, что у `hse-doc-studio pack check --base` (T2), в процессе api: lint, `releases check`, схемы,
классификатор невыпущенных версий и сверка реестра выпусков с базовой веткой. Проверяются только тронутые шаблоны и
паки: чужая ошибка в нетронутом паке не мешает предложить свою правку. Реестры базы приходят текстом (их читает git
рабочего пространства), сюда git не запускается.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

from hse_doc_studio.core.pack_studio.protocols import (
    CheckFinding,
    PackCheckReport,
    VersionClassInfo,
    VersionNotes,
)
from hse_doc_studio.infra.pack_studio.base_ref import BaseRefError, BaseReleases
from hse_doc_studio.infra.pack_studio.check import check_tree
from hse_doc_studio.infra.pack_studio.layout import VERSION_MANIFEST, PackPathError, discover
from hse_doc_studio.infra.template.releases import ReleaseEntry, parse_releases

_LANGS = ("ru", "en")


class _StoredBase(BaseReleases):
    """Реестры выпусков базовой ветки, уже прочитанные из хранилища пространства (ключ: каталог шаблона)."""

    def __init__(self, root: Path, texts: Mapping[str, str]) -> None:
        super().__init__("base")
        self._root = root.resolve()
        self._texts = texts

    def releases(self, template_dir: Path) -> dict[str, ReleaseEntry]:
        try:
            rel = template_dir.resolve().relative_to(self._root).as_posix()
        except ValueError:
            return {}
        text = self._texts.get(rel)
        if text is None:
            return {}
        try:
            return parse_releases(text)
        except yaml.YAMLError as exc:
            raise BaseRefError(f"{rel}: реестр базы не разобран ({exc})") from exc


def _rel(root: Path, raw: str) -> str:
    path = Path(raw)
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return raw


class WorkspacePackChecker:
    def check(self, root: Path, scopes: Sequence[str], base_registries: Mapping[str, str]) -> PackCheckReport:
        paths = [root / scope for scope in scopes if (root / scope).is_dir()]
        if not paths:
            return PackCheckReport()
        try:
            tree = discover(paths)
        except PackPathError:
            return PackCheckReport()
        try:
            result = check_tree(tree, _StoredBase(root, base_registries))
        except BaseRefError as exc:
            return PackCheckReport(findings=(CheckFinding("error", "base", ".", str(exc)),))
        findings = tuple(CheckFinding(f.severity, f.check, _rel(root, f.path), f.message) for f in result.findings)
        classes = tuple(
            VersionClassInfo(
                path=_rel(root, str(item.version_dir)),
                base=item.base,
                minimum=item.report.minimum.value,
                suggested=item.report.suggested.value,
                by_number=item.report.by_number.value if item.report.by_number else None,
                headline={lang: item.report.headline(lang) for lang in _LANGS},
                reasons=tuple({lang: reason.message(lang) for lang in _LANGS} for reason in item.report.reasons),
            )
            for item in result.classes
        )
        return PackCheckReport(findings=findings, classes=classes)

    def notes(self, root: Path, version_dir: str) -> VersionNotes:
        manifest = root / version_dir / VERSION_MANIFEST
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            return VersionNotes()
        raw = data.get("changes") if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return VersionNotes()
        changes = {
            lang: tuple(str(item) for item in items) for lang in _LANGS if isinstance(items := raw.get(lang), list)
        }
        return VersionNotes(changes=changes)
