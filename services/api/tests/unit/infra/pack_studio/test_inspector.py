"""Раскладка находок `pack_lint` и схем по файлам и строкам для редактора Студии шаблонов (срез T8)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from hse_doc_studio.core.pack_studio.errors import PackStudioError
from hse_doc_studio.infra.pack_studio.inspector import PackInspector, line_of

_PACKS = Path(__file__).resolve().parents[6] / "packs"
_SSE_VERSIONS = "hse-cs-sse/templates/coursework/versions"

_TEXT = """\
id: "2026.1.0"
meta_fields:
  year:
    type: string
signatures:
  slots:
    - id: author
      placements:
        report: { page: 1 }
"""


@pytest.mark.parametrize(
    ("where", "line"),
    [
        ((), 1),
        (("meta_fields", "year", "type"), 4),
        (("signatures", "slots", 0), 7),
        (("signatures", "slots", 0, "placements", "report"), 9),
        (("meta_fields", "nope", "type"), 2),
        (("signatures", "slots", 5), 6),
    ],
)
def test__line_of__finds_the_deepest_existing_node(where: tuple[str | int, ...], line: int) -> None:
    assert line_of(yaml.compose(_TEXT), where) == line


def test__lint_version__repository_pack__manifest_findings_get_a_line_in_version_yaml() -> None:
    versions = sorted((_PACKS / _SSE_VERSIONS).iterdir())
    version_dir = f"{_SSE_VERSIONS}/{versions[-1].name}"

    findings = PackInspector().lint_version(_PACKS, version_dir, released=True)

    manifest = (_PACKS / version_dir / "version.yaml").read_text(encoding="utf-8").splitlines()
    for finding in findings:
        if finding.message.startswith("signatures.slots["):
            assert finding.path == f"{version_dir}/version.yaml"
            assert finding.line is not None
            slot_key = finding.message.split(": ")[1].split(".")[1]
            assert manifest[finding.line - 1].lstrip().startswith(f"{slot_key}:")


def test__hints__repository_pack__fields_and_macros_from_meta_include() -> None:
    versions = sorted((_PACKS / _SSE_VERSIONS).iterdir())
    version_dir = f"{_SSE_VERSIONS}/{versions[-1].name}"

    hints = PackInspector().hints(_PACKS, version_dir)

    assert hints.version == version_dir
    assert "year" in {f.key for f in hints.meta_fields}
    macros = {m.name: m for m in hints.macros}
    assert macros["hseTitleEn"].keys == ("name_en",)
    assert all(not name.startswith("if") and "@" not in name for name in macros)


def test__inside__symlink_out_of_the_packs_folder__is_refused(tmp_path: Path) -> None:
    root = tmp_path / "packs"
    (root / "p/templates/t/versions").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "version.yaml").write_text("id: x\n", encoding="utf-8")
    (root / "p/templates/t/versions/1.0.0").symlink_to(outside)

    with pytest.raises(PackStudioError) as caught:
        PackInspector().lint_version(root, "p/templates/t/versions/1.0.0", released=False)

    assert caught.value.code.value == "path_not_allowed"


def test__lint_version__file_and_line_prefix_of_the_version_root_is_kept(tmp_path: Path) -> None:
    vdir = tmp_path / "p/templates/t/versions/1.0.0"
    (vdir / "files").mkdir(parents=True)
    (vdir / "version.yaml").write_text('id: "1.0.0"\nlangs: [ru]\n', encoding="utf-8")
    locator_input = "version.yaml:2: ru «текст» со скобкой без пары"

    from hse_doc_studio.infra.pack_studio.inspector import _LintLocator  # noqa: PLC0415

    path, line = _LintLocator(vdir, "p/templates/t/versions/1.0.0").locate(locator_input)

    assert (path, line) == ("p/templates/t/versions/1.0.0/version.yaml", 2)
