"""Временный дифференциальный тест: планировщик плюс исполнитель дают то же, что старый ассемблер.

Удаляется вместе с `SubmissionAssembler.populate_dir` в слайсе P5.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from hse_doc_studio.core.catalog import ExtraSubmissionItem, SubmissionDocItem, TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.infra.submission.assembler import SubmissionAssembler
from hse_doc_studio.infra.submission.pack_executor import PackExecutor
from hse_doc_studio.use_cases.submission.pack_planner import PackPlanner
from pypdf import PdfReader, PdfWriter
from pypdf._page import PageObject

from tests.factories import make_custom_file_override, make_document, make_project
from tests.unit.use_cases.submission.test_pack_planner import (
    FakeExporter,
    _def,
    _detached_setup,
    _empty,
    _stamped_state,
    _team_project,
    _version,
)

_BASE = "final-20260101T000000-abcd1234"


def _pdf(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _png() -> bytes:
    from PIL import Image  # noqa: PLC0415 — нужен только этому тесту

    buf = io.BytesIO()
    Image.new("RGBA", (200, 100), (0, 0, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


@dataclass
class _Scenario:
    project: Project
    version: TemplateVersion
    files: dict[str, bytes]
    docs: list[SubmissionDocItem]
    extras: list[ExtraSubmissionItem] = field(default_factory=list)
    state: SignaturesState = field(default_factory=_empty)
    rendered: dict[str, str] = field(default_factory=dict)
    decisions: dict[str, bool] | None = None
    exporter: FakeExporter | None = None
    lang: Lang = Lang.ru


def _items(*doc_ids: str, signatures: tuple[str, ...] = ()) -> list[SubmissionDocItem]:
    return [SubmissionDocItem(doc_id=d, signatures=signatures) for d in doc_ids]


def _solo_stamped() -> _Scenario:
    state, slot_def = _stamped_state()
    return _Scenario(
        project=make_project(documents=[make_document("tz"), make_document("vkr")]),
        version=_version((_def("tz", "ТЗ.pdf"), _def("vkr", "ВКР.pdf")), slots=(slot_def,)),
        files={"tz/tz.pdf": _pdf(3), "vkr/vkr.pdf": _pdf(1), ".hse-studio/signatures/author.png": _png()},
        docs=[SubmissionDocItem("tz", ("author",)), SubmissionDocItem("vkr", ())],
        state=state,
    )


def _solo_extras() -> _Scenario:
    custom = make_custom_file_override("my.pdf", "tz/_custom/my.pdf", ".pdf")
    docx = make_custom_file_override("През.docx", "pres/_custom/През.docx", ".docx")
    return _Scenario(
        project=make_project(
            documents=[
                make_document("tz", custom_file=custom),
                make_document("pres", custom_file=docx),
                make_document("vkr"),
            ]
        ),
        version=_version((_def("tz", "ТЗ.pdf"), _def("pres", "Презентация.pdf"), _def("vkr", "ВКР.pdf"))),
        files={
            "tz/_custom/my.pdf": _pdf(2),
            "pres/_custom/През.docx": b"PK docx",
            "pres/_custom/През.pdf": _pdf(4),
            # vkr без собранного PDF: пункт молча пропускается.
            "notes/raw.txt": "сырой".encode(),
            ".hse-studio/forms/ai.json": json.dumps({"Автор": "Иван", "Ответ": 42}, ensure_ascii=False).encode(),
            ".hse-studio/forms/broken.json": b"{not json",
        },
        docs=_items("tz", "pres", "vkr", "ghost"),
        extras=[
            ExtraSubmissionItem(source="notes/raw.txt", output_name="Заметки/Сырой.txt", format=None),
            ExtraSubmissionItem(source=".hse-studio/forms/ai.json", output_name="Декларация ИИ", format="markdown"),
            ExtraSubmissionItem(source=".hse-studio/forms/form.json", output_name="Форма.md", format="markdown"),
            ExtraSubmissionItem(source=".hse-studio/forms/broken.json", output_name="Сломан.md", format="markdown"),
            ExtraSubmissionItem(source="missing.txt", output_name="Нет.txt", format=None),
            ExtraSubmissionItem(source="notes/raw.txt", output_name="../evil.txt", format=None),
            ExtraSubmissionItem(source="../secret.txt", output_name="leak.txt", format=None),
        ],
        rendered={".hse-studio/forms/form.json": "# Готовая форма\n"},
        decisions={"pres": True},
    )


def _team() -> _Scenario:
    from dataclasses import replace  # noqa: PLC0415

    project = _team_project(
        [
            replace(make_document("tz--shalaev"), def_id="tz", owner="shalaev"),
            replace(make_document("tz--ivanov"), def_id="tz", owner="ivanov"),
            make_document("vkr"),
        ]
    )
    return _Scenario(
        project=project,
        version=_version((_def("tz", "ТЗ.pdf"), _def("vkr", "ВКР.pdf", scope="shared"))),
        files={"shalaev/tz/tz.pdf": _pdf(2), "ivanov/tz/tz.pdf": _pdf(1), "shared/vkr/vkr.pdf": _pdf(5)},
        docs=_items("tz--shalaev", "tz--ivanov", "vkr"),
        lang=Lang.en,
    )


def _detached() -> _Scenario:
    project, version, state, probe = _detached_setup()
    return _Scenario(
        project=project,
        version=version,
        files=dict(probe.files),
        docs=_items("tz", signatures=("advisor",)),
        state=state,
        exporter=FakeExporter({"A" * 40: b"-----BEGIN PGP PUBLIC KEY BLOCK-----"}),
    )


class _DiskProbe:
    def __init__(self, root: Path) -> None:
        self._root = root

    def is_file(self, path: str) -> bool:
        return (self._root / path).is_file()

    def size(self, path: str) -> int:
        return (self._root / path).stat().st_size

    def sha256(self, path: str) -> str:
        return hashlib.sha256((self._root / path).read_bytes()).hexdigest()

    def read_text(self, path: str) -> str:
        return (self._root / path).read_text(encoding="utf-8")

    def read_bytes(self, path: str) -> bytes:
        return (self._root / path).read_bytes()

    def list_files(self, prefix: str = "") -> tuple[str, ...]:
        return tuple(sorted(p.relative_to(self._root).as_posix() for p in self._root.rglob("*") if p.is_file()))


def _materialize(root: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _members(archive: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(archive) as zf:
        return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}


def _content(page: PageObject) -> bytes:
    contents = page.get_contents()
    return contents.get_data() if contents is not None else b""


def _changed_pages(source: bytes, produced: bytes) -> tuple[int, list[int]]:
    """(число страниц, номера страниц, чье содержимое отличается от исходника)."""
    before = PdfReader(io.BytesIO(source)).pages
    after = PdfReader(io.BytesIO(produced)).pages
    changed = [i + 1 for i, (a, b) in enumerate(zip(before, after, strict=True)) if _content(a) != _content(b)]
    return len(after), changed


_SCENARIOS: dict[str, Callable[[], _Scenario]] = {
    "solo_stamped": _solo_stamped,
    "solo_extras_and_custom": _solo_extras,
    "team_owner_suffix_en": _team,
    "detached_frozen_with_key": _detached,
}


@pytest.mark.unit
@pytest.mark.parametrize("name", list(_SCENARIOS))
async def test__plan_execute_matches_legacy__member_names_and_stamped_pages(name: str, tmp_path: Path) -> None:
    scenario = _SCENARIOS[name]()
    legacy_root = tmp_path / "legacy"
    new_root = tmp_path / "new"
    for root in (legacy_root, new_root):
        _materialize(root, scenario.files)

    legacy_dir = legacy_root / "submissions" / _BASE
    assembler = SubmissionAssembler(keyring=scenario.exporter)  # type: ignore[arg-type]
    legacy_written = await assembler.populate_dir(
        output_dir=legacy_dir,
        project_folder=legacy_root,
        doc_items=scenario.docs,
        extra_items=scenario.extras,
        template_version=scenario.version,
        signatures_state=scenario.state,
        lang=str(scenario.lang),
        rendered_extras=scenario.rendered,
        project=scenario.project,
        custom_doc_decisions=scenario.decisions,
    )
    legacy_archive = assembler.create_archive(legacy_dir, legacy_root / "submissions" / _BASE, "zip")

    plan = PackPlanner().build(
        scenario.project,
        scenario.version,
        scenario.state,
        scenario.docs,
        scenario.extras,
        scenario.lang,
        scenario.rendered,
        scenario.decisions,
        _DiskProbe(new_root),
        scenario.exporter,
        _BASE,
        "final",
        "zip",
    )
    executor = PackExecutor()
    executed = executor.execute(new_root, plan.payload)
    new_archive = executor.create_archive(executed.folder, new_root / "submissions" / _BASE, "zip")

    legacy_members = _members(legacy_archive)
    new_members = _members(new_archive)
    assert sorted(new_members) == sorted(legacy_members)
    assert sorted(executed.written) == sorted(legacy_written)
    assert executed.skipped == ()
    sources = {e.arcname: e.source.path for e in plan.payload.entries if e.source is not None}
    for member, legacy_data in legacy_members.items():
        if member in sources and _is_real_pdf(legacy_data):
            source = scenario.files[sources[member]]
            assert _changed_pages(source, new_members[member]) == _changed_pages(source, legacy_data)
        else:
            assert new_members[member] == legacy_data
    if name == "solo_stamped":
        # Сценарий не вырожден: штамп действительно лег на вторую страницу.
        assert _changed_pages(scenario.files["tz/tz.pdf"], new_members["ТЗ.pdf"]) == (3, [2])


def _is_real_pdf(data: bytes) -> bool:
    try:
        return len(PdfReader(io.BytesIO(data)).pages) > 0
    except Exception:  # noqa: BLE001 — любые байты, не разбираемые как PDF
        return False
