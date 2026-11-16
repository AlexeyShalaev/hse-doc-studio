"""Синтетическая версия шаблона для тестов вычислителя результата: каждое правило закрытого языка встречается в ней
ровно там, где его нужно проверить (виды работы, состав, NDA, руководства, языки, варианты, анкеты, точки и пресет)."""

from __future__ import annotations

from pathlib import Path

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository

VERSION_YAML = """\
id: "1.0.0"
status: beta
langs: [ru, en]
supported_staffing: [solo, team]
nda: { source_dir: nda }
meta_fields:
  nda: { type: bool, label: { ru: "NDA", en: "NDA" } }
  manuals:
    type: select
    label: { ru: "Руководства", en: "Manuals" }
    options: ["Программиста и оператора", "Только программиста", "Только оператора"]
    supported_kinds: [project]
    scope: author
  stage: { type: select, label: { ru: "Этап", en: "Stage" }, options: [draft, final], default: draft }
  topic: { type: string, label: { ru: "Тема", en: "Topic" }, required_at: create, placeholder: "Тема работы" }
  code: { type: string, label: { ru: "Код", en: "Code" }, required_at: finalize, default: "09.04.04" }
  supervisor: { type: person, label: { ru: "Научрук", en: "Supervisor" }, required_at: create }
  year: { type: string, label: { ru: "Год", en: "Year" }, auto: academic_year }
documents:
  - { id: report, name: { ru: "Отчёт", en: "Report" }, source_file: report/report.tex, output_file: report/report.pdf,
      output_name: { ru: "Отчёт.pdf", en: "Report.pdf" }, scope: personal, group: work }
  - id: spec
    name: { ru: "Спецификация", en: "Spec" }
    scope: personal
    supported_kinds: [project]
    supported_langs: [ru, en]
    variants:
      - { id: espd, label: { ru: "ЕСПД", en: "ESPD" }, source_file: spec/spec.tex, output_file: spec/spec.pdf,
          output_name: { ru: "Спецификация.pdf", en: "Spec.pdf" } }
      - { id: ieee, label: { ru: "IEEE", en: "IEEE" }, source_file: spec/ieee.tex, output_file: spec/ieee.pdf,
          output_name: { en: "Spec IEEE.pdf" }, supported_langs: [en] }
  - { id: shared_spec, name: { ru: "Общая спецификация", en: "Shared spec" }, source_file: shared/spec.tex,
      output_file: shared/spec.pdf, scope: shared, supported_kinds: [project], supported_staffing: [team] }
  - { id: summary, name: { ru: "Аннотация", en: "Summary" }, source_file: summary/summary.tex,
      output_file: summary/summary.pdf, supported_kinds: [research], scope: personal }
  - { id: programmer_manual, name: { ru: "РП", en: "PM" }, source_file: pm/pm.tex, output_file: pm/pm.pdf,
      supported_kinds: [project], scope: personal, required: false }
  - { id: operator_manual, name: { ru: "РО", en: "OM" }, source_file: om/om.tex, output_file: om/om.pdf,
      supported_kinds: [project], scope: personal, required: false }
  - { id: nda, name: { ru: "NDA", en: "NDA" }, source_file: nda/nda.tex, output_file: nda/nda.pdf,
      supported_langs: [ru], scope: personal, required: false }
  - id: presentation
    name: { ru: "Презентация", en: "Slides" }
    scope: personal
    variants:
      - { id: pptx, label: { ru: "PowerPoint", en: "PowerPoint" }, source_file: pres/pres.pptx,
          output_file: pres/pres.pptx, output_name: { ru: "Презентация.pptx", en: "Slides.pptx" } }
      - { id: beamer, label: { ru: "Beamer", en: "Beamer" }, source_file: pres/pres.tex, output_file: pres/pres.pdf,
          output_name: { ru: "Презентация.pdf", en: "Slides.pdf" } }
forms:
  - id: ai
    title: { ru: "Декларация ИИ", en: "AI declaration" }
    per_author: true
    required_for_pack: true
    sections:
      - id: usage
        title: { ru: "ИИ", en: "AI" }
        fields:
          - { id: used_ai, type: select, required: true, default: "no", label: { ru: "ИИ", en: "AI" },
              options: [ { id: "no", label: { ru: "Нет", en: "No" } }, { id: "yes", label: { ru: "Да", en: "Yes" } } ] }
          - { id: tools, type: text, required: true, label: { ru: "Какие", en: "Which" },
              visible_if: { field: used_ai, equals: "yes" } }
          - { id: agree, type: bool, required: true, label: { ru: "Согласен", en: "Agree" } }
          - { id: note, type: textarea, label: { ru: "Заметка", en: "Note" },
              visible_if: { field: agree, equals: true } }
          - { id: clauses, type: markdown, label: { ru: "Пункты", en: "Clauses" }, content: { ru: "...", en: "..." } }
  - id: repo
    title: { ru: "Репозиторий", en: "Repository" }
    supported_kinds: [research]
    sections:
      - id: link
        title: { ru: "Ссылка", en: "Link" }
        fields:
          - { id: url, type: text, required: true, label: { ru: "Адрес", en: "URL" } }
signatures:
  slots:
    - { id: author, label: { ru: "Автор", en: "Author" }, applies_to: [report, spec],
        default_placement: { page: 1, x_mm: 10, y_mm: 10, width_mm: 30 }, per_author: true }
    - { id: supervisor, label: { ru: "Научрук", en: "Supervisor" }, applies_to: [report, spec],
        default_placement: { page: 1, x_mm: 50, y_mm: 10, width_mm: 30 } }
    - { id: co_supervisor, label: { ru: "Консультант", en: "Co-supervisor" }, applies_to: [report],
        default_placement: { page: 1, x_mm: 90, y_mm: 10, width_mm: 30 } }
    - { id: academic_supervisor, label: { ru: "Академрук", en: "Academic" }, applies_to: [report],
        default_placement: { page: 1, x_mm: 130, y_mm: 10, width_mm: 30 } }
pack_submission:
  profiles:
    - id: topic
      name: { ru: "Тема", en: "Topic" }
      description: { ru: "Заявка", en: "Application" }
      items:
        - { doc_id: report, signatures: [author, supervisor] }
        - { doc_id: spec, signatures: [supervisor], skip_if_nda: true }
        - { doc_id: summary, signatures: [], supported_kinds: [research] }
        - { doc_id: operator_manual, signatures: [] }
      extra_items:
        - { source: .hse-studio/forms/repo.json, output_name: "Ссылка.txt", format: markdown,
            supported_kinds: [research] }
      signing_route: [[author], [supervisor, co_supervisor], [academic_supervisor]]
      signing_slots:
        - { doc_id: report, slot_id: co_supervisor, when: { person: co_supervisor } }
        - { doc_id: report, slot_id: academic_supervisor, when: { person: supervisor, role: company }, optional: true }
      deadline_hint: { ru: "В ноябре", en: "In November" }
    - id: final
      name: { ru: "Защита", en: "Defence" }
      description: { ru: "Финал", en: "Final" }
      items:
        - { doc_id: report, signatures: [author] }
        - { doc_id: presentation, signatures: [] }
checks_version:
  disabled_categories: [style]
  disabled: [fmt/off]
  severity_override: {}
"""

CHECKS_YAML = """\
rules:
  - { id: fmt/margins, title: { ru: "Поля", en: "Margins" }, category: formatting, applies_to: [report],
      engine: structural, severity: warn, params: {} }
  - { id: fmt/off, title: { ru: "Выключено", en: "Off" }, category: formatting, applies_to: [report],
      engine: structural, severity: info, params: {} }
  - { id: sty/tone, title: { ru: "Тон", en: "Tone" }, category: style, applies_to: "*",
      engine: regex, severity: info, params: { pattern: "x" } }
  - { id: spec/sections, title: { ru: "Разделы ТЗ", en: "Spec sections" }, category: structure, applies_to: [spec],
      engine: regex, severity: err, params: { pattern: "x" } }
  - { id: sum/short, title: { ru: "Аннотация", en: "Summary" }, category: structure, applies_to: [summary],
      engine: regex, severity: warn, params: { pattern: "x" } }
"""


def load_synthetic(
    root: Path, *, version_yaml: str = VERSION_YAML, checks_yaml: str | None = CHECKS_YAML
) -> TemplateVersion:
    """Записать версию под `root` как пак `p`, шаблон `t` и прочитать её лоадером паков."""
    version_dir = root / "p" / "templates" / "t" / "versions" / "1.0.0"
    version_dir.mkdir(parents=True)
    (root / "p" / "pack.yaml").write_text("id: p\n", encoding="utf-8")
    (root / "p" / "templates" / "t" / "template.yaml").write_text("id: t\n", encoding="utf-8")
    (version_dir / "version.yaml").write_text(version_yaml, encoding="utf-8")
    if checks_yaml is not None:
        (version_dir / "checks").mkdir()
        (version_dir / "checks" / "all.yaml").write_text(checks_yaml, encoding="utf-8")
    loaded = YamlTemplateRepository(root).get_version("p", "t", "1.0.0")
    assert loaded is not None
    return loaded
