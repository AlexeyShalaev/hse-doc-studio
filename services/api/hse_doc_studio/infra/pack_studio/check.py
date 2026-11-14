"""Проверки пака одной командой: `hse-doc-studio pack lint` и `pack check` (template-studio.md, 4.4 и 11).

* `lint`: `pack_lint` каждой версии под каталогом (вместе с правилом класса невыпущенной версии, 7.2);
* `check`: lint, неизменность выпущенных версий (`releases check`), схемы манифестов (`contracts/pack`), отчёт
  классификатора для версий, которые сверяются с предыдущей выпущенной, и при `--base` сверка реестра выпусков с
  базовой веткой (4.5).

Ошибка схемы в выпущенной версии это предупреждение: её каталог неизменен, исправляется новой версией. Выпущенной
считается версия из `releases.yaml` базовой ветки (с `--base`) или рабочего дерева (без него).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from hse_doc_studio.core.template_diff import ChangeReport, classify_change
from hse_doc_studio.infra.pack_studio import pack_schemas
from hse_doc_studio.infra.pack_studio.base_ref import BaseReleases
from hse_doc_studio.infra.pack_studio.layout import (
    PACK_MANIFEST,
    TEMPLATE_MANIFEST,
    VERSION_MANIFEST,
    PackTree,
    template_of,
)
from hse_doc_studio.infra.template.pack_lint import class_base, lint_version_dir
from hse_doc_studio.infra.template.releases import RELEASES_FILE, ReleaseEntry, check_template, load_releases

Severity = Literal["error", "warning"]
CheckName = Literal["lint", "releases", "schema", "base"]


@dataclass(frozen=True)
class Finding:
    """Одна находка: серьёзность, какая проверка, где (путь как его видит команда) и что."""

    severity: Severity
    check: CheckName
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "check": self.check, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class VersionClass:
    """Отчёт классификатора для версии, которая сверяется с предыдущей выпущенной (7.2)."""

    version_dir: Path
    base: str
    report: ChangeReport

    def to_dict(self) -> dict[str, Any]:
        template = template_of(self.version_dir)
        return {
            "path": str(self.version_dir),
            "template": template.name if template else None,
            "version": self.version_dir.name,
            "base": self.base,
            **self.report.to_dict(),
        }


@dataclass
class CheckResult:
    tree: PackTree
    findings: list[Finding] = field(default_factory=list)
    classes: list[VersionClass] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    def ok(self, *, strict: bool = False) -> bool:
        return not self.errors and not (strict and self.warnings)

    def add(self, severity: Severity, check: CheckName, path: Path, messages: list[str]) -> None:
        self.findings.extend(Finding(severity, check, str(path), message) for message in messages)

    def to_dict(self, *, strict: bool = False) -> dict[str, Any]:
        return {
            "ok": self.ok(strict=strict),
            "summary": {
                "packs": len(self.tree.packs),
                "templates": len(self.tree.templates),
                "versions": len(self.tree.versions),
                "errors": self.errors,
                "warnings": self.warnings,
            },
            "findings": [f.to_dict() for f in self.findings],
            "classes": [c.to_dict() for c in self.classes],
        }


def _lint(result: CheckResult, version_dir: Path) -> None:
    try:
        report = lint_version_dir(version_dir)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, TypeError, ValueError) as exc:
        result.add("error", "lint", version_dir, [f"{VERSION_MANIFEST} не разобран: {exc}"])
        return
    result.add("error", "lint", version_dir, report.errors)
    result.add("warning", "lint", version_dir, report.warnings)


def lint_tree(tree: PackTree) -> CheckResult:
    """`pack_lint` каждой найденной версии."""
    result = CheckResult(tree)
    for version_dir in tree.versions:
        _lint(result, version_dir)
    return result


def _schema(result: CheckResult, path: Path, severity: Severity, prefix: str = "") -> None:
    name = pack_schemas.schema_for(path)
    if name is None or not path.is_file():
        return
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        result.add("error", "schema", path, [f"YAML не разобран: {exc}"])
        return
    result.add(severity, "schema", path, [prefix + error for error in pack_schemas.validate(name, data)])


class _Released:
    """Выпущенные версии шаблона: из базы git, если она задана, иначе из рабочего дерева."""

    def __init__(self, base: BaseReleases | None) -> None:
        self._base = base
        self._cache: dict[Path, dict[str, ReleaseEntry]] = {}

    def of(self, template_dir: Path) -> dict[str, ReleaseEntry]:
        if template_dir not in self._cache:
            self._cache[template_dir] = self._base.releases(template_dir) if self._base else load_releases(template_dir)
        return self._cache[template_dir]


def _lint_and_schema(result: CheckResult, version_dir: Path, *, frozen: bool) -> None:
    _lint(result, version_dir)
    severity: Severity = "warning" if frozen else "error"
    prefix = "выпущенная версия неизменна, исправьте в новой: " if frozen else ""
    _schema(result, version_dir / VERSION_MANIFEST, severity, prefix)
    files = version_dir / "files"
    for doc_manifest in sorted(files.rglob("doc.yaml")) if files.is_dir() else ():
        _schema(result, doc_manifest, severity, prefix)


def check_version(version_dir: Path) -> CheckResult:
    """Линтер и схемы одной невыпущенной версии: то, что `pack freeze` требует перед записью в реестр."""
    result = CheckResult(PackTree((), (), (version_dir,)))
    _lint_and_schema(result, version_dir, frozen=False)
    return result


def _check_version(result: CheckResult, version_dir: Path, released: _Released) -> None:
    template = template_of(version_dir)
    _lint_and_schema(result, version_dir, frozen=template is not None and version_dir.name in released.of(template))
    base = class_base(version_dir)
    if base is None:
        return
    try:
        report = classify_change(version_dir.parent / base, version_dir)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, TypeError, ValueError):
        return  # линтер уже назвал это ошибкой («класс версии не посчитан»)
    result.classes.append(VersionClass(version_dir, base, report))


def _base_errors(template_dir: Path, base: dict[str, ReleaseEntry]) -> list[str]:
    """Запись выпущенной в базе версии ветка не убирает и не меняет (4.5)."""
    current = load_releases(template_dir)
    errors: list[str] = []
    for version, entry in sorted(base.items()):
        mine = current.get(version)
        if mine is None:
            errors.append(f"{template_dir.name}@{version}: выпущенная версия пропала из {RELEASES_FILE}")
        elif (mine.digest, mine.kind) != (entry.digest, entry.kind):
            errors.append(
                f"{template_dir.name}@{version}: запись выпущенной версии в {RELEASES_FILE} изменена "
                f"относительно базы; выпущенные версии не переиздают, выпустите новую"
            )
    return errors


def check_tree(tree: PackTree, base: BaseReleases | None = None) -> CheckResult:
    """Все проверки пака без TeX: lint, `releases check`, схемы, классы невыпущенных, сверка с базой."""
    result = CheckResult(tree)
    released = _Released(base)
    for pack_dir in tree.packs:
        _schema(result, pack_dir / PACK_MANIFEST, "error")
    for template_dir in tree.templates:
        _schema(result, template_dir / TEMPLATE_MANIFEST, "error")
        _schema(result, template_dir / RELEASES_FILE, "error")
        result.add("error", "releases", template_dir, check_template(template_dir))
        if base is not None:
            result.add("error", "base", template_dir, _base_errors(template_dir, released.of(template_dir)))
    for version_dir in tree.versions:
        _check_version(result, version_dir, released)
    return result
