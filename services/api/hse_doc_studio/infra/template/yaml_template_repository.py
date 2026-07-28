from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

import structlog
import yaml

from hse_doc_studio.core.catalog import (
    CheckRule,
    CheckSource,
    ChecksVersionConfig,
    DocumentDefinition,
    DocumentVariant,
    DynamicInclude,
    EngineConfig,
    ExtraSubmissionItem,
    FormColumn,
    FormDefinition,
    FormFieldDef,
    FormOption,
    FormOutputConfig,
    FormSection,
    MetaFieldDef,
    MetaGroupDef,
    NdaConfig,
    PackInfo,
    PackSubmissionConfig,
    SignatureDefaultPlacement,
    SignaturesConfig,
    SignatureSlotDef,
    SubmissionDocItem,
    SubmissionProfile,
    TemplateInfo,
    TemplateVersion,
    VisibleIf,
)
from hse_doc_studio.core.enums import (
    CheckEngine,
    CheckSeverity,
    EngineType,
    FormFieldType,
    MetaFieldAuto,
    MetaFieldType,
    RequiredAt,
    RequirementFormatKind,
    TemplateVersionStatus,
)
from hse_doc_studio.core.value_objects import ChecksOverride, RequirementsFormat

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Pack parser
# ---------------------------------------------------------------------------


def _parse_pack(pack_dir: Path) -> PackInfo | None:
    pack_yaml = pack_dir / "pack.yaml"
    if not pack_yaml.exists():
        logger.warning("pack.yaml not found", path=str(pack_yaml))
        return None
    try:
        data = _load_yaml(pack_yaml)
        if data is None:
            return None
        templates = _parse_templates(pack_dir, pack_id=data["id"])
        return PackInfo(
            id=data["id"],
            name=_localized(data.get("name", {})),
            description=_localized(data.get("description", {})),
            maintainer=_localized_or_flat(data.get("maintainer", {})),
            license=data.get("license", ""),
            templates=tuple(templates),
        )
    except Exception as exc:
        logger.warning("pack.yaml parse error", path=str(pack_yaml), exc=str(exc))
        return None


def _parse_templates(pack_dir: Path, pack_id: str) -> list[TemplateInfo]:
    templates_dir = pack_dir / "templates"
    if not templates_dir.exists():
        return []
    result: list[TemplateInfo] = []
    for template_dir in sorted(templates_dir.iterdir()):
        if not template_dir.is_dir():
            continue
        info = _parse_template_info(template_dir, pack_id=pack_id)
        if info is not None:
            result.append(info)
    return result


def _parse_template_info(template_dir: Path, pack_id: str) -> TemplateInfo | None:
    tpl_yaml = template_dir / "template.yaml"
    if not tpl_yaml.exists():
        logger.warning("template.yaml not found", path=str(tpl_yaml))
        return None
    try:
        data = _load_yaml(tpl_yaml)
        if data is None:
            return None
        return TemplateInfo(
            pack_id=pack_id,
            id=data["id"],
            name=_localized(data.get("name", {})),
            short_name=_localized(data.get("short_name", {})),
            description=_localized(data.get("description", {})),
            icon=data.get("icon", ""),
            accent_hue=int(data.get("accent_hue", 0)),
            default_version=str(data.get("default_version", "")),
        )
    except Exception as exc:
        logger.warning("template.yaml parse error", path=str(tpl_yaml), exc=str(exc))
        return None


# ---------------------------------------------------------------------------
# Version parser
# ---------------------------------------------------------------------------


def _parse_version(version_dir: Path, pack_id: str, template_id: str) -> TemplateVersion | None:
    ver_yaml = version_dir / "version.yaml"
    if not ver_yaml.exists():
        logger.warning("version.yaml not found", path=str(ver_yaml))
        return None
    try:
        data = _load_yaml(ver_yaml)
        if data is None:
            return None

        engine_data = data.get("engine", {})
        engine_cfg = EngineConfig(
            default=EngineType(engine_data.get("default", "xelatex")),
            allowed=tuple(EngineType(e) for e in engine_data.get("allowed", ["xelatex"])),
            passes=int(engine_data.get("passes", 1)),
            flags=engine_data.get("flags", ""),
        )

        documents = _parse_documents(data, version_dir)

        # v2 (bundle-раскладка): объявленные языковые коды суффиксов имён
        # файлов; первый = дефолт/фолбэк. Отсутствие -> v1 (lang/-оверлеи).
        raw_langs = data.get("langs", [])
        langs: tuple[str, ...] = ()
        if isinstance(raw_langs, list):
            langs = tuple(dict.fromkeys(str(c).lower() for c in raw_langs if isinstance(c, str) and c.strip()))

        meta_fields: dict[str, MetaFieldDef] = {}
        for field_id, field_data in data.get("meta_fields", {}).items():
            meta_fields[field_id] = _parse_meta_field(field_data)
        meta_groups = _parse_meta_groups(data.get("meta_groups", []))

        sig_data = data.get("signatures", {})
        signatures_config = SignaturesConfig(
            slots=tuple(_parse_signature_slot(s) for s in sig_data.get("slots", [])),
        )

        forms = tuple(f for f in (_parse_form(fd) for fd in data.get("forms", [])) if f is not None)

        sub_data = data.get("pack_submission", {})
        pack_submission = PackSubmissionConfig(
            profiles=tuple(_parse_submission_profile(p) for p in sub_data.get("profiles", []))
        )

        checks_ver_data = data.get("checks_version", {})
        checks_config = ChecksVersionConfig(
            disabled_categories=tuple(checks_ver_data.get("disabled_categories", [])),
            disabled=tuple(checks_ver_data.get("disabled", [])),
            severity_override={k: CheckSeverity(v) for k, v in checks_ver_data.get("severity_override", {}).items()},
        )

        # Parse rules from checks/*.yaml, plus each file's own header describing
        # the document it encodes (label/ref/source) — the UI groups by that.
        rules, check_sources = _parse_checks_dir(version_dir / "checks")

        requirements_format = _parse_requirements_format(data.get("requirements"))

        dynamic_includes = tuple(
            DynamicInclude(template=str(inc["template"]), output=str(inc["output"]))
            for inc in data.get("dynamic_includes", [])
            if isinstance(inc, dict) and inc.get("template") and inc.get("output")
        )

        nda_data = data.get("nda")
        nda = None
        if isinstance(nda_data, dict) and nda_data.get("source_dir"):
            nda = NdaConfig(
                source_dir=str(nda_data["source_dir"]),
                submission_dir=str(nda_data.get("submission_dir", "NDA")),
            )

        released_raw = data.get("released_at", "2000-01-01")
        released_at = released_raw if isinstance(released_raw, date) else date.fromisoformat(str(released_raw))

        supported_staffing = _parse_staffing_list(data.get("supported_staffing"), default=("solo",))

        return TemplateVersion(
            pack_id=pack_id,
            template_id=template_id,
            version=str(data["id"]),
            status=TemplateVersionStatus(data.get("status", "stable")),
            released_at=released_at,
            summary=_localized(data.get("summary", {})),
            engine_config=engine_cfg,
            required_tex_packages=tuple(data.get("latex_packages", [])),
            documents=documents,
            meta_fields=meta_fields,
            meta_groups=meta_groups,
            signatures_config=signatures_config,
            pack_submission=pack_submission,
            checks_config=checks_config,
            rules=tuple(rules),
            check_sources=tuple(check_sources),
            requirements_format=requirements_format,
            forms=forms,
            dynamic_includes=dynamic_includes,
            nda=nda,
            supported_staffing=supported_staffing,
            langs=langs,
        )
    except Exception as exc:
        logger.warning("version.yaml parse error", path=str(ver_yaml), exc=str(exc))
        return None


def _parse_documents(data: dict[str, Any], version_dir: Path) -> tuple[DocumentDefinition, ...]:  # noqa: C901
    """Список документов версии: v1 — inline-словари в version.yaml; v2
    (bundle-раскладка) — roster из id-строк, мета каждого — files/<id>/doc.yaml.

    Fail-fast (вся версия не грузится, warning в лог): запись roster без
    doc.yaml, id внутри doc.yaml не совпадает с именем папки, bundle с doc.yaml
    на диске без записи в roster (иначе документ молча пропал бы из пака).
    Смешение строк и словарей допустимо на переходный период.
    """
    raw = data.get("documents", [])
    docs: list[DocumentDefinition] = []
    roster_ids: set[str] = set()
    for entry in raw:
        if isinstance(entry, str):
            doc_id = entry.strip()
            doc_path = version_dir / "files" / doc_id / "doc.yaml"
            if not doc_path.exists():
                raise ValueError(f"roster document {doc_id!r}: missing {doc_path}")
            doc_data = _load_yaml(doc_path)
            if not isinstance(doc_data, dict):
                raise TypeError(f"roster document {doc_id!r}: invalid doc.yaml")
            declared_id = str(doc_data.get("id", doc_id))
            if declared_id != doc_id:
                raise ValueError(f"doc.yaml id {declared_id!r} != bundle dir {doc_id!r}")
            docs.append(_parse_document_definition({**doc_data, "id": doc_id}))
            roster_ids.add(doc_id)
        else:
            docs.append(_parse_document_definition(entry))
    if roster_ids:
        on_disk = {p.parent.name for p in (version_dir / "files").glob("*/doc.yaml")}
        extra = sorted(on_disk - roster_ids)
        if extra:
            raise ValueError(f"bundles with doc.yaml not listed in documents roster: {extra}")
    return tuple(docs)


def _parse_requirements_format(data: dict[str, Any] | None) -> RequirementsFormat:
    if not data:
        return RequirementsFormat()
    return RequirementsFormat(
        kind=RequirementFormatKind(data.get("format", "macro")),
        id_pattern=data.get("id_pattern"),
        definition_docs=tuple(data.get("definition_docs", [])),
        def_pattern=data.get("def_pattern"),
        ref_pattern=data.get("ref_pattern"),
    )


def _parse_document_definition(data: dict[str, Any]) -> DocumentDefinition:
    checks_data = data.get("checks", {})
    checks = ChecksOverride(
        disabled_categories=tuple(checks_data.get("disabled_categories", [])),
        disabled=tuple(checks_data.get("disabled", [])),
        enabled=tuple(checks_data.get("enabled", [])),
        severity_override={k: CheckSeverity(v) for k, v in checks_data.get("severity_override", {}).items()},
    )
    variants_data = data.get("variants", [])
    variants = tuple(_parse_document_variant(v) for v in variants_data)
    raw_supported = data.get("supported_langs", [])
    supported_langs = tuple(str(lang).lower() for lang in raw_supported if isinstance(lang, str))
    doc_id = str(data["id"])
    if "--" in doc_id:
        # "--" зарезервирован как сепаратор инстансов team-режима
        # ("{def_id}--{owner}") — базовый id пака не может его содержать.
        raise ValueError(f"document id {doc_id!r} must not contain '--'")
    return DocumentDefinition(
        id=doc_id,
        name=_localized(data.get("name", {})),
        code=_localized(data.get("code", {})),
        source_file=data.get("source_file"),
        output_file=data.get("output_file"),
        output_name=_localized(data.get("output_name", {})),
        gost_ref=data.get("gost_ref"),
        required=bool(data.get("required", False)),
        checks=checks,
        supported_langs=supported_langs,
        variants=variants,
        scope=str(data.get("scope", "shared")),
        supported_staffing=_parse_staffing_list(data.get("supported_staffing")),
        supported_kinds=_parse_kinds_list(data.get("supported_kinds")),
        group=str(data["group"]) if data.get("group") else None,
    )


def _parse_staffing_list(raw: Any, default: tuple[str, ...] = ("solo", "team")) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return default
    values = tuple(str(s).lower() for s in raw if str(s).lower() in ("solo", "team"))
    return values or default


def _parse_kinds_list(raw: Any, default: tuple[str, ...] = ("research", "project")) -> tuple[str, ...]:
    """Форматы ВКР, в которых существует документ (research/project).

    Отсутствие/пустой/мусорный список → оба формата (документ общий). Так
    легаси-шаблоны без `supported_kinds` продолжают инстанцировать все доки.
    """
    if not isinstance(raw, list):
        return default
    values = tuple(str(s).lower() for s in raw if str(s).lower() in ("research", "project"))
    return values or default


def _parse_document_variant(data: dict[str, Any]) -> DocumentVariant:
    raw_engine = data.get("engine")
    engine: EngineType | None = None
    if raw_engine and str(raw_engine).lower() != "none":
        engine = EngineType(raw_engine)
    raw_langs = data.get("supported_langs", [])
    return DocumentVariant(
        id=data["id"],
        label=_localized(data.get("label", {})),
        source_file=data.get("source_file", ""),
        output_file=data.get("output_file", ""),
        output_name=_localized(data.get("output_name", {})),
        engine=engine,
        supported_langs=tuple(str(lang).lower() for lang in raw_langs if isinstance(lang, str)),
    )


def _parse_meta_field(data: dict[str, Any]) -> MetaFieldDef:
    auto = data.get("auto")
    return MetaFieldDef(
        type=MetaFieldType(data.get("type", "string")),
        label=_localized(data.get("label", {})),
        placeholder=data.get("placeholder"),
        required_at=RequiredAt(data.get("required_at", "create")),
        help=_localized(data.get("help", {})) if data.get("help") else None,
        default=data.get("default"),
        auto=MetaFieldAuto(auto) if auto else None,
        options=tuple(data.get("options", [])),
        group=data.get("group"),
        scope="author" if str(data.get("scope", "project")).lower() == "author" else "project",
        supported_kinds=_parse_kinds_list(data.get("supported_kinds")),
    )


def _parse_meta_groups(data: list[dict[str, Any]]) -> tuple[MetaGroupDef, ...]:
    return tuple(
        MetaGroupDef(
            id=str(g["id"]),
            label=_localized(g.get("label", {})),
            section=str(g.get("section", "meta")),
        )
        for g in data
        if isinstance(g, dict) and g.get("id")
    )


def _parse_form(data: dict[str, Any]) -> FormDefinition | None:
    """Parse one pack-declared form. Tolerant: a malformed form is skipped
    (logged) rather than aborting the whole version load.
    """
    try:
        sections = tuple(s for s in (_parse_form_section(sd) for sd in data.get("sections", [])) if s is not None)
        output_data = data.get("output")
        output: FormOutputConfig | None = None
        if isinstance(output_data, dict) and output_data.get("template"):
            output = FormOutputConfig(
                template=str(output_data["template"]),
                output_name=str(output_data.get("output_name", "")),
                format=str(output_data.get("format", "markdown")),
            )
        form_id = str(data["id"])
        if "--" in form_id:
            raise ValueError(f"form id {form_id!r} must not contain '--'")
        return FormDefinition(
            id=form_id,
            title=_localized(data.get("title", {})),
            sections=sections,
            schema_version=int(data.get("schema_version", 1)),
            required_for_pack=bool(data.get("required_for_pack", False)),
            output=output,
            icon=data.get("icon"),
            per_author=bool(data.get("per_author", False)),
            supported_kinds=_parse_kinds_list(data.get("supported_kinds")),
        )
    except Exception as exc:
        logger.warning("form parse error", form_id=data.get("id"), exc=str(exc))
        return None


def _parse_form_section(data: dict[str, Any]) -> FormSection | None:
    try:
        fields = tuple(f for f in (_parse_form_field(fd) for fd in data.get("fields", [])) if f is not None)
        return FormSection(
            id=str(data["id"]),
            title=_localized(data.get("title", {})),
            fields=fields,
        )
    except Exception as exc:
        logger.warning("form section parse error", section_id=data.get("id"), exc=str(exc))
        return None


def _parse_form_field(data: dict[str, Any]) -> FormFieldDef | None:
    # Skip-on-error at the FIELD granularity so one bad field never hides the
    # rest of the form (mirrors _parse_check_rule).
    try:
        options = tuple(
            FormOption(
                id=str(o["id"]),
                label=_localized(o.get("label", {})),
                default=bool(o.get("default", False)),
            )
            for o in data.get("options", [])
            if isinstance(o, dict) and "id" in o
        )
        columns = tuple(
            FormColumn(id=str(c["id"]), label=_localized(c.get("label", {})))
            for c in data.get("columns", [])
            if isinstance(c, dict) and "id" in c
        )
        vis_raw = data.get("visible_if")
        visible_if: VisibleIf | None = None
        if isinstance(vis_raw, dict) and "field" in vis_raw:
            visible_if = VisibleIf(field=str(vis_raw["field"]), equals=vis_raw.get("equals"))
        return FormFieldDef(
            id=str(data["id"]),
            type=FormFieldType(data.get("type", "text")),
            label=_localized(data.get("label", {})),
            help=_localized(data.get("help", {})) if data.get("help") else None,
            placeholder=_localized(data.get("placeholder", {})) if data.get("placeholder") else None,
            required=bool(data.get("required", False)),
            options=options,
            columns=columns,
            min=data.get("min"),
            max=data.get("max"),
            step=data.get("step"),
            min_length=data.get("min_length"),
            default=data.get("default"),
            widget=data.get("widget"),
            visible_if=visible_if,
            content=_localized(data.get("content", {})) if data.get("content") else None,
        )
    except Exception as exc:
        logger.warning("form field parse error", field_id=data.get("id"), exc=str(exc))
        return None


def _parse_signature_slot(data: dict[str, Any]) -> SignatureSlotDef:
    placement_data = data.get("default_placement", {})
    placement = SignatureDefaultPlacement(
        page=int(placement_data.get("page", 1)),
        x_mm=float(placement_data.get("x_mm", 60.0)),
        y_mm=float(placement_data.get("y_mm", 230.0)),
        width_mm=float(placement_data.get("width_mm", 50.0)),
    )
    applies_to_raw = data.get("applies_to", [])
    slot_id = str(data["id"])
    if "--" in slot_id:
        raise ValueError(f"signature slot id {slot_id!r} must not contain '--'")
    # `required_for` из старых паков читается и ОТБРАСЫВАЕТСЯ намеренно:
    # обязательность подписи теперь выводится из профилей сдачи (см. комментарий
    # у SignatureSlotDef). Молча игнорировать поле безопаснее, чем падать: пак
    # прошлого учебного года должен открываться, а лишний ключ на поведение
    # больше не влияет.
    return SignatureSlotDef(
        id=slot_id,
        label=_localized(data.get("label", {})),
        applies_to=tuple(applies_to_raw) if isinstance(applies_to_raw, list) else (applies_to_raw,),
        default_placement=placement,
        per_author=bool(data.get("per_author", False)),
    )


def _parse_submission_profile(data: dict[str, Any]) -> SubmissionProfile:
    items = tuple(
        SubmissionDocItem(
            doc_id=item["doc_id"],
            signatures=tuple(item.get("signatures", [])),
            skip_if_nda=bool(item.get("skip_if_nda", False)),
            supported_kinds=_parse_kinds_list(item.get("supported_kinds")),
        )
        for item in data.get("items", [])
    )
    extra_items = tuple(
        ExtraSubmissionItem(
            source=item.get("source", ""),
            output_name=item.get("output_name", ""),
            format=item.get("format"),
            supported_kinds=_parse_kinds_list(item.get("supported_kinds")),
        )
        for item in data.get("extra_items", [])
    )
    return SubmissionProfile(
        id=data["id"],
        name=_localized(data.get("name", {})),
        description=_localized(data.get("description", {})),
        items=items,
        extra_items=extra_items,
    )


# ---------------------------------------------------------------------------
# Checks parser
# ---------------------------------------------------------------------------


def _parse_checks_dir(checks_dir: Path) -> tuple[list[CheckRule], list[CheckSource]]:
    if not checks_dir.exists():
        return [], []
    all_rules: list[CheckRule] = []
    sources: list[CheckSource] = []
    seen_ids: set[str] = set()
    for yaml_file in sorted(checks_dir.glob("*.yaml")):
        rules, source = _parse_checks_file(yaml_file)
        # Только файлы, давшие хотя бы одно правило: источник без правил ни на что
        # не сгруппируется, а в UI выглядел бы пустой группой.
        if rules and source is not None:
            sources.append(source)
        for rule in rules:
            if rule.id in seen_ids:
                logger.warning("duplicate check rule id, skipping", rule_id=rule.id, file=str(yaml_file))
                continue
            seen_ids.add(rule.id)
            all_rules.append(rule)
    return all_rules, sources


def _parse_checks_file(yaml_file: Path) -> tuple[list[CheckRule], CheckSource | None]:
    try:
        data = _load_yaml(yaml_file)
        if not data:
            return [], None
        rules: list[CheckRule] = []
        for rule_data in data.get("rules", []):
            rule = _parse_check_rule(rule_data)
            if rule is not None:
                rules.append(rule)
        source = _parse_check_source(_source_id_for(yaml_file, rules), data)
    except Exception as exc:
        logger.warning("checks yaml parse error", path=str(yaml_file), exc=str(exc))
        return [], None
    else:
        return rules, source


def _source_id_for(yaml_file: Path, rules: list[CheckRule]) -> str:
    """Attribution key for a checks file = the prefix its rules actually carry.

    The convention is `<file-basename>/<short-name>`, but a pack may ship a shorter
    prefix than the file name (hse-cs-se: `hse-pi-language-2026.yaml` -> `hse-pi-lang/*`).
    Rule ids are persisted in per-project overrides inside `.hse-studio`, so they must
    NOT be renamed to fit the file name — key off the prefix and tell the pack author.
    """
    prefixes = {rule.id.split("/", 1)[0] for rule in rules if "/" in rule.id}
    if len(prefixes) == 1:
        prefix = next(iter(prefixes))
        if prefix != yaml_file.stem:
            logger.warning(
                "checks file name differs from its rule-id prefix; grouping by the prefix",
                file=yaml_file.name,
                prefix=prefix,
            )
        return prefix
    if len(prefixes) > 1:
        logger.warning(
            "checks file mixes rule-id prefixes; grouping by file name",
            file=yaml_file.name,
            prefixes=sorted(prefixes),
        )
    return yaml_file.stem


def _parse_check_source(source_id: str, data: dict[str, Any]) -> CheckSource:
    """Header of a checks/*.yaml: what document its rules come from.

    `label` is the short UI heading; a pack that omits it degrades to `ref`, and
    then to the bare id — the UI stays readable either way and never has to know
    the names of standards or study programmes itself.
    """
    ref = _localized(data.get("ref", {}))
    label = _localized(data.get("label", {})) or ref
    source_data = data.get("source") or {}
    if not isinstance(source_data, dict):
        source_data = {}
    url = source_data.get("url")
    return CheckSource(
        id=source_id,
        label=label,
        ref=ref,
        source=_localized({k: v for k, v in source_data.items() if k != "url"}),
        url=str(url) if url else None,
    )


def _parse_check_rule(data: dict[str, Any]) -> CheckRule | None:
    try:
        applies_to_raw = data.get("applies_to", "*")
        if applies_to_raw == "*":
            applies_to: list[str] | Literal["*"] = "*"
        elif isinstance(applies_to_raw, list):
            applies_to = list(applies_to_raw)
        else:
            applies_to = [str(applies_to_raw)]

        return CheckRule(
            id=data["id"],
            title=_localized(data.get("title", {})),
            description=_localized(data.get("description", {})),
            category=data.get("category"),
            applies_to=applies_to,
            # Pack YAML uses the `default_severity` key (see every checks/*.yaml);
            # `severity` is kept as a forward-compat fallback. Historically only
            # `severity` was read, so all rules silently loaded as `warn` — this
            # now honours the authored severity (err/info/warn).
            default_severity=CheckSeverity(data.get("default_severity") or data.get("severity") or "warn"),
            engine=CheckEngine(data.get("engine", "structural")),
            params=dict(data.get("params", {})),
        )
    except Exception as exc:
        logger.warning("check rule parse error", rule_id=data.get("id"), exc=str(exc))
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        content = path.read_text(encoding="utf-8")
        return yaml.safe_load(content)
    except Exception as exc:
        logger.warning("yaml load error", path=str(path), exc=str(exc))
        return None


def _localized(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {k: str(v) for k, v in value.items()}
    if isinstance(value, str):
        return {"ru": value}
    return {}


def _localized_or_flat(value: Any) -> dict[str, str]:
    """For maintainer field which may be a flat dict or localized."""
    if isinstance(value, dict):
        # Check if it looks like a localized dict (keys are language codes)
        if any(k in value for k in ("ru", "en")):
            return {k: str(v) for k, v in value.items()}
        # Otherwise treat as flat dict, stringify all values
        return {k: str(v) for k, v in value.items()}
    if isinstance(value, str):
        return {"name": value}
    return {}


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class YamlTemplateRepository:
    """Loads and caches template definitions from a directory of YAML packs."""

    def __init__(self, packs_dir: Path) -> None:
        self._packs_dir = packs_dir
        self._packs: list[PackInfo] = []
        # Map (pack_id, template_id, version) -> TemplateVersion
        self._versions: dict[tuple[str, str, str], TemplateVersion] = {}
        self._loaded = False

    def load(self) -> None:
        """Recursively read packs_dir, parse all YAML files, cache results."""
        self._packs = []
        self._versions = {}

        if not self._packs_dir.exists():
            logger.warning("packs_dir does not exist", path=str(self._packs_dir))
            self._loaded = True
            return

        for pack_dir in sorted(self._packs_dir.iterdir()):
            if not pack_dir.is_dir():
                continue
            pack_info = _parse_pack(pack_dir)
            if pack_info is None:
                continue
            self._packs.append(pack_info)
            self._load_pack_versions(pack_info, pack_dir)

        self._loaded = True
        logger.info(
            "template repository loaded",
            packs=len(self._packs),
            versions=len(self._versions),
        )

    def _load_pack_versions(self, pack_info: PackInfo, pack_dir: Path) -> None:
        """Iterate templates_dir, read template.yaml, delegate to _load_template_versions."""
        templates_dir = pack_dir / "templates"
        if not templates_dir.exists():
            return
        for template_dir in sorted(templates_dir.iterdir()):
            if not template_dir.is_dir():
                continue
            tpl_yaml = template_dir / "template.yaml"
            if not tpl_yaml.exists():
                continue
            tpl_data = _load_yaml(tpl_yaml)
            if tpl_data is None:
                continue
            template_id = tpl_data.get("id", template_dir.name)
            self._load_template_versions(pack_info, template_dir, template_id)

    def _load_template_versions(self, pack_info: PackInfo, template_dir: Path, template_id: str) -> None:
        """Iterate versions_dir, parse each version, store in self._versions."""
        versions_dir = template_dir / "versions"
        if not versions_dir.exists():
            return
        for version_dir in sorted(versions_dir.iterdir()):
            if not version_dir.is_dir():
                continue
            version_obj = _parse_version(
                version_dir,
                pack_id=pack_info.id,
                template_id=template_id,
            )
            if version_obj is not None:
                key = (pack_info.id, template_id, version_obj.version)
                self._versions[key] = version_obj

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def list_packs(self) -> list[PackInfo]:
        self._ensure_loaded()
        return list(self._packs)

    def get_version(self, pack_id: str, template_id: str, version: str) -> TemplateVersion | None:
        self._ensure_loaded()
        return self._versions.get((pack_id, template_id, version))

    def list_versions(self, pack_id: str, template_id: str) -> list[str]:
        self._ensure_loaded()
        return [ver for (pid, tid, ver) in self._versions if pid == pack_id and tid == template_id]

    def version_dir(self, pack_id: str, template_id: str, version: str) -> Path | None:
        """Filesystem directory of a version's authored sources.

        Paths declared in the pack (a form's `output.template`) are relative to
        this directory.
        """
        self._ensure_loaded()
        candidate = self._packs_dir / pack_id / "templates" / template_id / "versions" / version
        return candidate if candidate.exists() else None
