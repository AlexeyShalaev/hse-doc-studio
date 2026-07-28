from __future__ import annotations

from pathlib import Path

from hse_doc_studio.core.enums import CheckSeverity, MetaFieldAuto, RequiredAt
from hse_doc_studio.infra.template.yaml_template_repository import (
    YamlTemplateRepository,
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
    (pack_dir / "pack.yaml").write_text(_PACK_YAML, encoding="utf-8")

    tmpl_dir = pack_dir / "templates" / "test-tmpl"
    tmpl_dir.mkdir(parents=True)
    (tmpl_dir / "template.yaml").write_text(_TEMPLATE_YAML, encoding="utf-8")

    ver_dir = tmpl_dir / "versions" / "1.0"
    ver_dir.mkdir(parents=True)
    (ver_dir / "version.yaml").write_text(_VERSION_YAML, encoding="utf-8")
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
    (ver_dir / "version.yaml").write_text(_META_VERSION_YAML, encoding="utf-8")

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
    (ver_dir / "version.yaml").write_text(_META_GROUPS_VERSION_YAML, encoding="utf-8")

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
    (checks_dir / "rules.yaml").write_text(_CHECKS_YAML, encoding="utf-8")

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
    (checks_dir / filename).write_text(body, encoding="utf-8")


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
