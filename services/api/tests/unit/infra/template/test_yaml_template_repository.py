from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.catalog import SignatureDefaultPlacement, SigningSlotPreset, SlotCondition
from hse_doc_studio.core.enums import (
    CheckSeverity,
    DateMarkAlign,
    DateMarkFormat,
    MetaFieldAuto,
    PersonRole,
    RequiredAt,
    TemplateUpdateClass,
)
from hse_doc_studio.infra.template.releases import freeze
from hse_doc_studio.infra.template.yaml_template_repository import (
    YamlTemplateRepository,
    _parse_signature_slot,
    _parse_submission_profile,
    parse_default_dates,
    parse_signing_route,
    parse_signing_slot,
    parse_slot_placement,
)

# ---------------------------------------------------------------------------
# Minimal YAML fixtures
# ---------------------------------------------------------------------------

_PACK_YAML = """\
id: test-pack
name: {ru: Test, en: Test}
description: {ru: Test pack, en: Test pack}
maintainer: {name: Test, email: test@test.com, url: ""}
license: MIT
created_at: 2026-01-01
"""

_TEMPLATE_YAML = """\
id: test-tmpl
name: {ru: Test Template, en: Test Template}
short_name: {ru: Test, en: Test}
description: {ru: Test, en: Test}
icon: ""
accent_hue: 200
default_version: "1.0"
"""

# NOTE: _parse_version reads data["id"] for the version string, not data["version"].
_VERSION_YAML = """\
id: "1.0"
released_at: 2026-01-01
status: stable
summary: {ru: Test, en: Test}
engine:
  default: xelatex
  allowed: [xelatex]
  passes: 1
  flags: ""
latex_packages: []
documents: []
meta_fields: {}
signatures:
  embed_via: latex
  slots: []
pack_submission:
  profiles: []
"""


def _build_pack_dir(base: Path) -> None:
    """Create the minimal test-pack directory tree under base."""
    pack_dir = base / "test-pack"
    (pack_dir).mkdir(parents=True)
    (pack_dir / "pack.yaml").write_text(_PACK_YAML, encoding="utf-8", newline="\n")

    tmpl_dir = pack_dir / "templates" / "test-tmpl"
    tmpl_dir.mkdir(parents=True)
    (tmpl_dir / "template.yaml").write_text(_TEMPLATE_YAML, encoding="utf-8", newline="\n")

    ver_dir = tmpl_dir / "versions" / "1.0"
    ver_dir.mkdir(parents=True)
    (ver_dir / "version.yaml").write_text(_VERSION_YAML, encoding="utf-8", newline="\n")
    (ver_dir / "checks").mkdir()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test__load__real_packs_dir__lists_packs(tmp_path: Path) -> None:
    _build_pack_dir(tmp_path)
    repo = YamlTemplateRepository(tmp_path)
    repo.load()
    packs = repo.list_packs()
    assert len(packs) == 1
    assert packs[0].id == "test-pack"


def test__get_version__existing_version__returns_template_version(tmp_path: Path) -> None:
    _build_pack_dir(tmp_path)
    repo = YamlTemplateRepository(tmp_path)
    version = repo.get_version("test-pack", "test-tmpl", "1.0")
    assert version is not None
    assert version.version == "1.0"
    assert version.pack_id == "test-pack"
    assert version.template_id == "test-tmpl"


def test__get_version__unknown_version__returns_none(tmp_path: Path) -> None:
    _build_pack_dir(tmp_path)
    repo = YamlTemplateRepository(tmp_path)
    result = repo.get_version("test-pack", "test-tmpl", "99.0")
    assert result is None


def test__list_versions__existing_template__returns_versions(tmp_path: Path) -> None:
    _build_pack_dir(tmp_path)
    repo = YamlTemplateRepository(tmp_path)
    versions = repo.list_versions("test-pack", "test-tmpl")
    assert "1.0" in versions


_CHECKS_YAML = """\
rules:
  - id: test/err-rule
    title: {ru: Err}
    description: {ru: ""}
    category: structure
    applies_to: [vkr]
    default_severity: err
    engine: regex
    params: {pattern: "x", file_glob: "*.tex"}
  - id: test/info-rule
    title: {ru: Info}
    description: {ru: ""}
    applies_to: "*"
    default_severity: info
    engine: regex
    params: {pattern: "y"}
  - id: test/no-severity
    title: {ru: Default}
    description: {ru: ""}
    applies_to: "*"
    engine: regex
    params: {pattern: "z"}
"""


_META_VERSION_YAML = """\
id: "1.0"
released_at: 2026-01-01
status: stable
summary: {ru: Test, en: Test}
engine:
  default: xelatex
  allowed: [xelatex]
  passes: 1
  flags: ""
latex_packages: []
documents: []
meta_fields:
  degree_type:
    type: string
    label: {ru: Тип диплома}
    default: Бакалавриат
    required_at: create
  year:
    type: string
    label: {ru: Год защиты}
    auto: academic_year
    required_at: create
  bpi_code:
    type: string
    label: {ru: Шифр}
    required_at: finalize
  city:
    type: string
    label: {ru: Город}
signatures:
  embed_via: latex
  slots: []
pack_submission:
  profiles: []
"""


def test__load__meta_field_yaml__parses_default_auto_and_required_at(tmp_path: Path) -> None:
    _build_pack_dir(tmp_path)
    ver_dir = tmp_path / "test-pack" / "templates" / "test-tmpl" / "versions" / "1.0"
    (ver_dir / "version.yaml").write_text(_META_VERSION_YAML, encoding="utf-8", newline="\n")

    repo = YamlTemplateRepository(tmp_path)
    version = repo.get_version("test-pack", "test-tmpl", "1.0")
    assert version is not None
    fields = version.meta_fields

    assert fields["degree_type"].default == "Бакалавриат"
    assert fields["degree_type"].auto is None
    assert fields["year"].auto is MetaFieldAuto.academic_year
    assert fields["year"].default is None
    assert fields["bpi_code"].required_at is RequiredAt.finalize
    # required_at defaults to "create" when the pack omits it.
    assert fields["city"].required_at is RequiredAt.create


_META_GROUPS_VERSION_YAML = """\
id: "1.0"
released_at: 2026-01-01
status: stable
summary: {ru: Test, en: Test}
engine:
  default: xelatex
  allowed: [xelatex]
  passes: 1
  flags: ""
latex_packages: []
documents: []
meta_groups:
  - id: study
    label: {ru: Учёба}
  - id: docset
    label: {ru: Состав документов}
    section: documents
meta_fields: {}
signatures:
  embed_via: latex
  slots: []
pack_submission:
  profiles: []
"""


def test__load__meta_group_yaml__reads_section_and_defaults_to_meta(tmp_path: Path) -> None:
    _build_pack_dir(tmp_path)
    ver_dir = tmp_path / "test-pack" / "templates" / "test-tmpl" / "versions" / "1.0"
    (ver_dir / "version.yaml").write_text(_META_GROUPS_VERSION_YAML, encoding="utf-8", newline="\n")

    repo = YamlTemplateRepository(tmp_path)
    version = repo.get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    by_id = {g.id: g for g in version.meta_groups}
    # `section` решает, на какой странице настроек проекта живёт группа.
    assert by_id["docset"].section == "documents"
    # Без ключа группа остаётся в «Метаданных».
    assert by_id["study"].section == "meta"


def test__load__check_rule_yaml__honours_default_severity_key(tmp_path: Path) -> None:
    # Regression: the loader must read `default_severity` (the key every pack
    # uses), not the legacy `severity` key — otherwise every rule silently
    # loads as `warn`. Rules without a severity default to `warn`.
    _build_pack_dir(tmp_path)
    checks_dir = tmp_path / "test-pack" / "templates" / "test-tmpl" / "versions" / "1.0" / "checks"
    (checks_dir / "rules.yaml").write_text(_CHECKS_YAML, encoding="utf-8", newline="\n")

    repo = YamlTemplateRepository(tmp_path)
    version = repo.get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    by_id = {r.id: r for r in version.rules}
    assert by_id["test/err-rule"].default_severity == CheckSeverity.err
    assert by_id["test/info-rule"].default_severity == CheckSeverity.info
    assert by_id["test/no-severity"].default_severity == CheckSeverity.warn


# ---------------------------------------------------------------------------
# checks/*.yaml header -> CheckSource (подписи групп объявляет пак, не приложение)
# ---------------------------------------------------------------------------

_CHECKS_WITH_HEADER = """label: {ru: ГОСТ 7.32-2017, en: GOST 7.32-2017}
ref: {ru: ГОСТ 7.32-2017 §6, en: GOST 7.32-2017 §6}
source:
  ru: Отчёт о научно-исследовательской работе
  url: https://docs.cntd.ru/document/1200157208

rules:
  - id: gost-7.32-2017/margins
    title: {ru: Поля}
    description: {ru: ""}
    applies_to: "*"
    engine: regex
    params: {pattern: "x"}
"""

_CHECKS_WITHOUT_LABEL = """ref: {ru: Только ссылка, en: Ref only}

rules:
  - id: refonly/rule
    title: {ru: R}
    description: {ru: ""}
    applies_to: "*"
    engine: regex
    params: {pattern: "x"}
"""

# Имя файла и префикс id правил расходятся — так живут два файла в hse-cs-se
# (hse-pi-language-2026.yaml -> hse-pi-lang/*).
_CHECKS_PREFIX_MISMATCH = """label: {ru: Язык, en: Language}
ref: {ru: LanguageTool, en: LanguageTool}

rules:
  - id: short-prefix/spelling
    title: {ru: Орфография}
    description: {ru: ""}
    applies_to: "*"
    engine: regex
    params: {pattern: "x"}
"""


def _write_checks(tmp_path: Path, filename: str, body: str) -> None:
    checks_dir = tmp_path / "test-pack" / "templates" / "test-tmpl" / "versions" / "1.0" / "checks"
    (checks_dir / filename).write_text(body, encoding="utf-8", newline="\n")


def test__load__checks_file_header__exposes_pack_declared_label_ref_and_url(tmp_path: Path) -> None:
    _build_pack_dir(tmp_path)
    _write_checks(tmp_path, "gost-7.32-2017.yaml", _CHECKS_WITH_HEADER)

    version = YamlTemplateRepository(tmp_path).get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    (source,) = version.check_sources
    assert source.id == "gost-7.32-2017"
    assert source.label == {"ru": "ГОСТ 7.32-2017", "en": "GOST 7.32-2017"}
    assert source.ref == {"ru": "ГОСТ 7.32-2017 §6", "en": "GOST 7.32-2017 §6"}
    assert source.url == "https://docs.cntd.ru/document/1200157208"
    # `url` не должен протечь в локализованный словарь издателя.
    assert "url" not in source.source


def test__load__checks_file_without_label__falls_back_to_ref(tmp_path: Path) -> None:
    # Пак вправе не объявлять короткую подпись — UI обязан остаться читаемым.
    _build_pack_dir(tmp_path)
    _write_checks(tmp_path, "refonly.yaml", _CHECKS_WITHOUT_LABEL)

    version = YamlTemplateRepository(tmp_path).get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    (source,) = version.check_sources
    assert source.label == {"ru": "Только ссылка", "en": "Ref only"}


def test__load__rule_prefix_differs_from_file_name__source_id_follows_the_prefix(tmp_path: Path) -> None:
    # Атрибуция правила к источнику идёт по префиксу его id, а не по имени файла:
    # id правил лежат в пользовательских переопределениях и переименованию не подлежат.
    _build_pack_dir(tmp_path)
    _write_checks(tmp_path, "language-2026.yaml", _CHECKS_PREFIX_MISMATCH)

    version = YamlTemplateRepository(tmp_path).get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    (source,) = version.check_sources
    assert source.id == "short-prefix"


def test__load__checks_file_with_no_rules__yields_no_source(tmp_path: Path) -> None:
    # Источник без правил не на что группировать — в UI это была бы пустая группа.
    _build_pack_dir(tmp_path)
    _write_checks(tmp_path, "empty.yaml", "label: {ru: Пусто, en: Empty}\nrules: []\n")

    version = YamlTemplateRepository(tmp_path).get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    assert version.check_sources == ()


# ---------------------------------------------------------------------------
# Versioning: manifest format, min_studio, release kind, notes, releases.yaml
# ---------------------------------------------------------------------------


def _write_version(tmp_path: Path, extra: str) -> Path:
    _build_pack_dir(tmp_path)
    ver_dir = tmp_path / "test-pack" / "templates" / "test-tmpl" / "versions" / "1.0"
    (ver_dir / "version.yaml").write_text(_VERSION_YAML + extra, encoding="utf-8", newline="\n")
    return ver_dir


def test__versioning_fields__parsed(tmp_path: Path) -> None:
    _write_version(
        tmp_path,
        'manifest_format: 1\nmin_studio: "0.2.0"\nrelease: {kind: minor, from: "0.9"}\n'
        "changes: {ru: [Новый раздел], en: [New section]}\n"
        "breaking_changes: {ru: [], en: []}\n",
    )
    version = YamlTemplateRepository(tmp_path).get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    assert version.manifest_format == 1
    assert version.min_studio == "0.2.0"
    assert version.release_kind == TemplateUpdateClass.minor
    assert version.changes == {"ru": ("Новый раздел",), "en": ("New section",)}
    assert version.breaking_changes == {"ru": (), "en": ()}
    assert version.frozen_digest is None
    assert not version.is_released


def test__newer_manifest_format__version_not_loaded(tmp_path: Path) -> None:
    _write_version(tmp_path, "manifest_format: 99\n")
    assert YamlTemplateRepository(tmp_path).get_version("test-pack", "test-tmpl", "1.0") is None


def test__unknown_item_types__skip_only_that_item(tmp_path: Path) -> None:
    # Манифест от более новой Студии: неизвестный тип поля и неизвестный движок
    # выкидывают только свой элемент, версия остаётся доступной проектам.
    ver_dir = _write_version(tmp_path, "")
    text = (ver_dir / "version.yaml").read_text(encoding="utf-8")
    text = text.replace("allowed: [xelatex]", "allowed: [xelatex, tectonic]")
    text = text.replace(
        "meta_fields: {}",
        "meta_fields:\n  ok: {type: string, label: {ru: Ок}}\n  future: {type: hologram, label: {ru: Будущее}}",
    )
    (ver_dir / "version.yaml").write_text(text, encoding="utf-8", newline="\n")

    version = YamlTemplateRepository(tmp_path).get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    assert set(version.meta_fields) == {"ok"}
    assert [e.value for e in version.engine_config.allowed] == ["xelatex"]


def test__releases_yaml__marks_version_released(tmp_path: Path) -> None:
    _write_version(tmp_path, "")
    tmpl_dir = tmp_path / "test-pack" / "templates" / "test-tmpl"
    entry = freeze(tmpl_dir, "1.0", TemplateUpdateClass.major)

    version = YamlTemplateRepository(tmp_path).get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    assert version.is_released
    assert version.frozen_digest == entry.digest
    assert version.release_kind == TemplateUpdateClass.major


def test__parse_submission_profile__methods_per_slot__allowed_methods() -> None:
    profile = _parse_submission_profile(
        {
            "id": "topic",
            "items": [
                {"doc_id": "app", "signatures": ["author", "supervisor"], "methods": {"author": ["image", "detached"]}}
            ],
        }
    )

    item = profile.items[0]
    assert item.allowed_methods("author") == ("image", "detached")
    assert item.allowed_methods("author--ivanov") == ("image", "detached")
    assert item.allowed_methods("supervisor") == ()


def test__parse_submission_profile__unknown_method__rejected() -> None:
    with pytest.raises(ValueError, match="unknown"):
        _parse_submission_profile(
            {"id": "topic", "items": [{"doc_id": "app", "signatures": ["author"], "methods": {"author": ["fax"]}}]}
        )


# ---------------------------------------------------------------------------
# Порядок маршрута подписания: signatures.route и signing_route профиля
# ---------------------------------------------------------------------------

_ROUTE_SLOTS = """\
  slots:
    - {id: author, label: {ru: Автор}, applies_to: [app]}
    - {id: supervisor, label: {ru: Научрук}, applies_to: [app]}
    - {id: academic_supervisor, label: {ru: Академрук}, applies_to: [app]}
"""


def _write_route_version(tmp_path: Path, route: str, profile_route: str = "") -> None:
    ver_dir = _write_version(tmp_path, "")
    text = (ver_dir / "version.yaml").read_text(encoding="utf-8")
    text = text.replace("  slots: []\n", _ROUTE_SLOTS + route)
    profile = "  profiles:\n    - id: topic\n      items: [{doc_id: app, signatures: [author, supervisor]}]\n"
    text = text.replace("  profiles: []\n", profile + profile_route)
    (ver_dir / "version.yaml").write_text(text, encoding="utf-8", newline="\n")


def test__signing_route__version_and_profile__parsed_as_steps(tmp_path: Path) -> None:
    _write_route_version(
        tmp_path,
        "  route: [[author], [supervisor, academic_supervisor]]\n",
        "      signing_route: [author, supervisor, [academic_supervisor]]\n",
    )

    version = YamlTemplateRepository(tmp_path).get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    assert version.signatures_config.route == (("author",), ("supervisor", "academic_supervisor"))
    assert version.pack_submission.profiles[0].signing_route == (("author",), ("supervisor",), ("academic_supervisor",))


def test__signing_route__absent__empty(tmp_path: Path) -> None:
    _write_route_version(tmp_path, "")

    version = YamlTemplateRepository(tmp_path).get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    assert version.signatures_config.route == ()
    assert version.pack_submission.profiles[0].signing_route == ()


def test__signing_route__malformed__ignored_version_and_profile_still_load(tmp_path: Path) -> None:
    _write_route_version(tmp_path, "  route: {first: author}\n", "      signing_route: [[author--ivanov]]\n")

    version = YamlTemplateRepository(tmp_path).get_version("test-pack", "test-tmpl", "1.0")

    assert version is not None
    assert [s.id for s in version.signatures_config.slots] == ["author", "supervisor", "academic_supervisor"]
    assert version.signatures_config.route == ()
    assert [p.id for p in version.pack_submission.profiles] == ["topic"]
    assert version.pack_submission.profiles[0].signing_route == ()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ()),
        ([], ()),
        ([["author"], [], [" supervisor ", ""]], (("author",), ("supervisor",))),
        (["author", ["supervisor", "co_supervisor"]], (("author",), ("supervisor", "co_supervisor"))),
    ],
)
def test__parse_signing_route__shapes(raw: object, expected: tuple[tuple[str, ...], ...]) -> None:
    assert parse_signing_route(raw) == expected


@pytest.mark.parametrize("raw", ["author", [["author", 1]], [{"slots": ["author"]}], [["author--ivanov"]]])
def test__parse_signing_route__malformed__rejected(raw: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        parse_signing_route(raw)


# --- метки даты по умолчанию (signing-route.md, 14.10) -----------------------------------------------------------


def test__parse_default_dates__marks_by_document_with_format_and_alignment() -> None:
    parsed = parse_default_dates(
        {
            "project_proposal": [
                {"page": 2, "x_mm": 120, "y_mm": 250, "width_mm": 8, "height_mm": 5, "format": "day"},
                {"page": 2, "x_mm": 132, "y_mm": 250, "width_mm": 22, "height_mm": 5, "format": "month_word",
                 "align": "right"},
            ]
        }
    )  # fmt: skip

    ((doc_id, (day, month)),) = parsed
    assert doc_id == "project_proposal"
    assert (day.page, day.x_mm, day.format, day.align) == (2, 120.0, DateMarkFormat.day, DateMarkAlign.centered)
    assert (month.width_mm, month.format, month.align) == (22.0, DateMarkFormat.month_word, DateMarkAlign.right)
    assert parse_default_dates(None) == ()


def test__parse_signature_slot__wrong_default_dates__dropped_and_the_slot_kept() -> None:
    slot = _parse_signature_slot(
        {
            "id": "supervisor",
            "applies_to": ["project_proposal"],
            "default_dates": {"project_proposal": [{"x_mm": 300, "y_mm": 1, "width_mm": 8, "height_mm": 5,
                                                    "format": "day"}]},
        }
    )  # fmt: skip

    assert slot.id == "supervisor"
    assert slot.default_dates == ()


# --- пресет маршрута из пака (signing-route.md, 15.3 и 15.8) --------------------------------------------------------


def test__parse_signature_slot__placements_by_document__broken_entry_dropped_others_kept() -> None:
    slot = _parse_signature_slot(
        {
            "id": "supervisor",
            "applies_to": ["project_proposal", "topic_application", "report"],
            "default_placement": {"page": 1, "x_mm": 110, "y_mm": 130, "width_mm": 40},
            "placements": {
                "project_proposal": {"page": 1, "x_mm": 80, "y_mm": 139, "width_mm": 40},
                "topic_application": {"page": 1, "x_mm": 190, "y_mm": 168, "width_mm": 40},
                "report": {"page": 0, "x_mm": 10, "y_mm": 10, "width_mm": 40},
            },
        }
    )

    assert slot.placements == (("project_proposal", SignatureDefaultPlacement(1, 80, 139, 40)),)
    assert slot.place_for("topic_application") == SignatureDefaultPlacement(1, 110, 130, 40)


@pytest.mark.parametrize(
    ("item", "fragment"),
    [
        ({"page": 0, "x_mm": 10, "y_mm": 10, "width_mm": 40}, "before the first page"),
        ({"x_mm": 10, "y_mm": 10, "width_mm": 5}, "width_mm 5 is outside 10..200"),
        ({"x_mm": 10, "y_mm": 10, "width_mm": 201}, "width_mm 201"),
        ({"x_mm": 180, "y_mm": 10, "width_mm": 40}, "left or right edge"),
        ({"x_mm": -1, "y_mm": 10, "width_mm": 40}, "left or right edge"),
        ({"x_mm": 10, "y_mm": 290, "width_mm": 40}, "y_mm 290 is outside 0..287"),
        ({"x_mm": 10, "y_mm": 10}, "width_mm"),
        ([10, 10, 40], "must be a mapping"),
    ],
)
def test__parse_slot_placement__wrong_place__error_names_the_entry(item: object, fragment: str) -> None:
    with pytest.raises((TypeError, ValueError, KeyError)) as exc:
        parse_slot_placement(item, "placements.report")

    assert fragment in str(exc.value)


def test__parse_signature_slot__placements_not_a_mapping__dropped() -> None:
    slot = _parse_signature_slot({"id": "author", "applies_to": ["report"], "placements": ["report"]})

    assert slot.placements == ()


def test__parse_submission_profile__signing_slots__conditions_and_optional() -> None:
    profile = _parse_submission_profile(
        {
            "id": "topic-approval",
            "items": [{"doc_id": "topic_application", "signatures": ["author", "supervisor"]}],
            "signing_slots": [
                {"doc_id": "topic_application", "slot_id": "co_supervisor", "when": {"person": "co_supervisor"}},
                {"doc_id": "topic_application", "slot_id": "academic_supervisor",
                 "when": {"person": "supervisor", "role": "company"}},
                {"doc_id": "topic_application", "slot_id": "supervisor", "optional": True},
            ],
        }
    )  # fmt: skip

    assert profile.signing_slots == (
        SigningSlotPreset("topic_application", "co_supervisor", SlotCondition("co_supervisor")),
        SigningSlotPreset("topic_application", "academic_supervisor", SlotCondition("supervisor", PersonRole.company)),
        SigningSlotPreset("topic_application", "supervisor", None, optional=True),
    )


@pytest.mark.parametrize(
    ("entry", "fragment"),
    [
        ({"doc_id": "d", "slot_id": "s", "when": {"person": "supervisor", "kind": "project"}}, "unknown condition"),
        ({"doc_id": "d", "slot_id": "s", "when": {"person": "dean"}}, "when.person"),
        ({"doc_id": "d", "slot_id": "s", "when": {"role": "company"}}, "when.person"),
        ({"doc_id": "d", "slot_id": "s", "when": {"person": "supervisor", "role": "ministry"}}, "when.role"),
        ({"doc_id": "d", "slot_id": "s", "when": "supervisor"}, "must be a mapping"),
        ({"doc_id": "d", "slot_id": "s", "optional": "yes"}, "optional must be true or false"),
        ({"doc_id": "d", "slot_id": "author--ivanov"}, "runtime slot id"),
        ({"doc_id": "", "slot_id": "s"}, "non-empty strings"),
        ("supervisor", "must be a mapping"),
    ],
)
def test__parse_signing_slot__wrong_entry__error(entry: object, fragment: str) -> None:
    with pytest.raises((TypeError, ValueError)) as exc:
        parse_signing_slot(entry, "signing_slots[0]")

    assert fragment in str(exc.value)


def test__parse_submission_profile__signing_slots_unknown_condition__entry_dropped_profile_kept() -> None:
    profile = _parse_submission_profile(
        {
            "id": "topic-approval",
            "items": [{"doc_id": "topic_application", "signatures": ["author"]}],
            "signing_slots": [
                {"doc_id": "topic_application", "slot_id": "academic_supervisor", "when": {"meta": "nda"}},
                {"doc_id": "topic_application", "slot_id": "supervisor"},
            ],
        }
    )

    assert profile.id == "topic-approval"
    assert profile.signing_slots == (SigningSlotPreset("topic_application", "supervisor"),)
    assert _parse_submission_profile({"id": "x", "signing_slots": {"a": 1}}).signing_slots == ()
