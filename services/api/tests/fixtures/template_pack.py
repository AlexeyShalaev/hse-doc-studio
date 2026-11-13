"""Синтетический пак с двумя версиями шаблона — для тестов обновления шаблона.

`2026.1` (выпущена) → `2026.1.1` (patch): меняется цвет в преамбуле, в конец
отчёта добавляется раздел, появляется приложение, исчезает устаревший файл,
меняется логотип (бинарник).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.infra.template.releases import freeze

PACK_ID = "upd-pack"
TEMPLATE_ID = "kp"
V1 = "2026.1"
V2 = "2026.1.1"

_PACK_YAML = """\
id: upd-pack
name: {ru: Пак обновлений, en: Update pack}
description: {ru: Тест, en: Test}
maintainer: {name: Test, email: test@test.local, url: ""}
license: MIT
created_at: 2026-01-01
"""

_TEMPLATE_YAML = """\
id: kp
name: {ru: КП, en: CP}
short_name: {ru: КП, en: CP}
description: {ru: Тест, en: Test}
icon: ""
accent_hue: 200
default_version: "2026.1"
"""

_VERSION_YAML = """\
id: "{version}"
released_at: 2026-09-01
status: stable
summary: {{ru: Версия {version}, en: Version {version}}}
changes:
  ru: [{change_ru}]
  en: [{change_en}]
engine: {{default: xelatex, allowed: [xelatex], passes: 1, flags: ""}}
latex_packages: []
supported_kinds: [research, project]
supported_staffing: [solo]
langs: [ru]
documents: [report]
meta_fields: {{}}
dynamic_includes:
  - template: common/meta.tex.j2
    output: common/meta.tex
signatures: {signatures}
pack_submission: {{profiles: []}}
"""

_DOC_YAML = """\
name: {ru: Отчёт, en: Report}
code: {ru: ОТЧ, en: REP}
source_file: report/report.tex
output_file: report/report.pdf
output_name: {ru: Отчёт.pdf, en: Report.pdf}
required: true
"""

REPORT_V1 = """\
\\documentclass{article}
\\input{preamble}
\\input{../common/meta}
\\title{ {{ project.name | texesc }} }
\\begin{document}
\\section{Введение}
Текст введения из шаблона.

\\section{Основная часть}
Текст основной части.
\\end{document}
"""

REPORT_V2 = REPORT_V1.replace(
    "\\end{document}\n",
    "\\section{Заключение}\nВыводы.\n\\end{document}\n",
)

PREAMBLE_V1 = "\\usepackage{xcolor}\n\\definecolor{accent}{RGB}{0,0,255}\n"
PREAMBLE_V2 = "\\usepackage{xcolor}\n\\definecolor{accent}{RGB}{0,0,0}\n"
OLD_TEX = "% устаревший файл\n"
APPENDIX_TEX = "\\section{Приложение}\n"
LOGO_V1 = b"\x89PNG\r\n\x1a\n\x00logo-v1"
LOGO_V2 = b"\x89PNG\r\n\x1a\n\x00logo-v2"
META_J2 = "\\newcommand{\\projectName}{ {{ project.name | texesc }} }\n"


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="\n")


def _version(
    template_dir: Path,
    version: str,
    files: dict[str, Any],
    change: tuple[str, str],
    signatures: str = "{slots: []}",
) -> None:
    version_dir = template_dir / "versions" / version
    _write(
        version_dir / "version.yaml",
        _VERSION_YAML.format(version=version, change_ru=change[0], change_en=change[1], signatures=signatures),
    )
    (version_dir / "checks").mkdir(parents=True, exist_ok=True)
    _write(version_dir / "files" / "report" / "doc.yaml", _DOC_YAML)
    _write(version_dir / "files" / "common" / "meta.tex.j2", META_J2)
    for rel, content in files.items():
        _write(version_dir / "files" / rel, content)


def build_update_pack(packs_dir: Path) -> Path:
    """Пак в `packs_dir`; возвращает каталог шаблона."""
    pack_dir = packs_dir / PACK_ID
    _write(pack_dir / "pack.yaml", _PACK_YAML)
    template_dir = pack_dir / "templates" / TEMPLATE_ID
    _write(template_dir / "template.yaml", _TEMPLATE_YAML)
    _version(
        template_dir,
        V1,
        {
            "report/report.tex": REPORT_V1,
            "report/preamble.tex": PREAMBLE_V1,
            "report/old.tex": OLD_TEX,
            "report/logo.png": LOGO_V1,
        },
        ("Первая версия", "First version"),
    )
    _version(
        template_dir,
        V2,
        {
            "report/report.tex": REPORT_V2,
            "report/preamble.tex": PREAMBLE_V2,
            "report/appendix.tex": APPENDIX_TEX,
            "report/logo.png": LOGO_V2,
        },
        ("Чёрный акцент и раздел «Заключение»", "Black accent and a Conclusion section"),
    )
    freeze(template_dir, V1, TemplateUpdateClass.major)
    freeze(template_dir, V2, TemplateUpdateClass.patch)
    return template_dir


# Пресеты подписания (docs/design/signing-route.md, 15.10): 2026.1 знает только общее место слота, patch 2026.1.1 с
# теми же файлами задаёт место научрука на отчёте и метки даты. Обновление меняет только места подписей.
SUPERVISOR_V1 = {"page": 1, "x_mm": 110.0, "y_mm": 130.0, "width_mm": 40.0}
SUPERVISOR_V2 = {"page": 1, "x_mm": 80.0, "y_mm": 139.0, "width_mm": 40.0}
AUTHOR_PLACE = {"page": 1, "x_mm": 160.0, "y_mm": 208.0, "width_mm": 30.0}

_SIGNATURES_V1 = """
  slots:
    - id: author
      label: {ru: Автор, en: Author}
      applies_to: [report]
      default_placement: {page: 1, x_mm: 160, y_mm: 208, width_mm: 30}
    - id: supervisor
      label: {ru: Научный руководитель, en: Supervisor}
      applies_to: [report]
      default_placement: {page: 1, x_mm: 110, y_mm: 130, width_mm: 40}"""

_SIGNATURES_V2 = (
    _SIGNATURES_V1
    + """
      placements:
        report: {page: 1, x_mm: 80, y_mm: 139, width_mm: 40}
      default_dates:
        report:
          - {page: 1, x_mm: 81, y_mm: 156, width_mm: 7, height_mm: 5, format: day}
          - {page: 1, x_mm: 90, y_mm: 156, width_mm: 24, height_mm: 5, format: month_word}"""
)


def build_presets_pack(packs_dir: Path) -> Path:
    """Пак `upd-pack`: 2026.1 и patch 2026.1.1 с теми же файлами и местами подписей из шаблона."""
    pack_dir = packs_dir / PACK_ID
    _write(pack_dir / "pack.yaml", _PACK_YAML)
    template_dir = pack_dir / "templates" / TEMPLATE_ID
    _write(template_dir / "template.yaml", _TEMPLATE_YAML)
    files = {"report/report.tex": REPORT_V1, "report/preamble.tex": PREAMBLE_V1}
    _version(template_dir, V1, files, ("Первая версия", "First version"), _SIGNATURES_V1)
    _version(
        template_dir, V2, files, ("Места подписей из шаблона", "Signature places from the template"), _SIGNATURES_V2
    )
    freeze(template_dir, V1, TemplateUpdateClass.major)
    freeze(template_dir, V2, TemplateUpdateClass.patch)
    return template_dir


def project_payload(folder: Path, version: str = V1, name: str = "Курсовой проект") -> dict[str, Any]:
    return {
        "name": name,
        "folder": str(folder),
        "pack_id": PACK_ID,
        "template_id": TEMPLATE_ID,
        "version": version,
        "engine": "xelatex",
        "kind": "research",
        "staffing": "solo",
        "lang": "ru",
        "authors": [{"name": "Иван Иванов", "group": "МСПИН261", "email": None}],
        "supervisor": None,
        "co_supervisor": None,
        "meta": {},
    }
