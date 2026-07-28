from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from hse_doc_studio.core.catalog import (
    ChecksVersionConfig,
    DocumentDefinition,
    EngineConfig,
    FormDefinition,
    PackSubmissionConfig,
    SignatureDefaultPlacement,
    SignaturesConfig,
    SignatureSlotDef,
    SubmissionDocItem,
    SubmissionProfile,
    TemplateVersion,
)
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import (
    DocumentStatus,
    EngineType,
    Lang,
    ProjectKind,
    ProjectStaffing,
    TemplateVersionStatus,
)
from hse_doc_studio.core.services import (
    ProjectTemplateService,
    SignatureSlotService,
    SubmissionProfileService,
    resolve_form_instance,
)
from hse_doc_studio.core.team import (
    doc_instance_id,
    normalize_team_authors,
    project_bases,
    split_instance_id,
    translit_slug,
)
from hse_doc_studio.core.value_objects import (
    Author,
    ChecksOverride,
    ProjectLock,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
)
from hse_doc_studio.infra.project_init.template_renderer import (
    TemplateRenderer,
    instantiate_missing_base_parts,
)
from hse_doc_studio.use_cases.projects.create_project import _build_documents

# ── фикстуры ──────────────────────────────────────────────────────────────


def _doc_def(doc_id: str, scope: str = "personal", staffing: tuple[str, ...] = ("solo", "team")) -> DocumentDefinition:
    return DocumentDefinition(
        id=doc_id,
        name={"ru": doc_id},
        code={"ru": doc_id},
        source_file=f"{doc_id}/{doc_id}.tex",
        output_file=f"{doc_id}/{doc_id}.pdf",
        output_name={"ru": f"{doc_id}.pdf"},
        gost_ref=None,
        required=True,
        checks=ChecksOverride(),
        scope=scope,
        supported_staffing=staffing,
    )


def _version(
    docs: tuple[DocumentDefinition, ...],
    slots: tuple[SignatureSlotDef, ...] = (),
    profiles: tuple[SubmissionProfile, ...] = (),
) -> TemplateVersion:
    return TemplateVersion(
        pack_id="p",
        template_id="t",
        version="1",
        status=TemplateVersionStatus.stable,
        released_at=date(2026, 1, 1),
        summary={"ru": ""},
        engine_config=EngineConfig(default=EngineType.xelatex, allowed=(EngineType.xelatex,), passes=1, flags=""),
        required_tex_packages=(),
        documents=docs,
        meta_fields={},
        signatures_config=SignaturesConfig(slots=slots),
        pack_submission=PackSubmissionConfig(profiles=profiles),
        checks_config=ChecksVersionConfig(disabled_categories=(), disabled=(), severity_override={}),
        rules=(),
        forms=(
            FormDefinition(id="ai_declaration", title={"ru": "Декларация"}, sections=(), per_author=True),
            FormDefinition(id="feedback", title={"ru": "Отзыв"}, sections=()),
        ),
        supported_staffing=("solo", "team"),
    )


def _team_project(documents: list[Document] | None = None, *, shared_enabled: bool = True) -> Project:
    now = datetime.now(tz=timezone.utc)
    return Project(
        id=uuid.uuid4(),
        name="Система X",
        folder=Path("/tmp/x"),
        lock=ProjectLock(pack_id="p", template_id="t", version="1", engine=EngineType.xelatex),
        kind=ProjectKind.project,
        staffing=ProjectStaffing.team,
        lang=Lang.ru,
        authors=[
            Author(name="Шалаев Алексей", group="БПИ211", slug="shalaev", topic="Серверная часть", managed=True),
            Author(name="Иванов Иван", group="БПИ212", slug="ivanov", topic="Клиентская часть", managed=True),
        ],
        meta={},
        supervisor=None,
        co_supervisor=None,
        documents=documents or [],
        created_at=now,
        updated_at=now,
        shared_enabled=shared_enabled,
    )


# ── team.py primitives ────────────────────────────────────────────────────


def test__translit_slug__surname() -> None:
    assert translit_slug("Шалаев Алексей Дмитриевич") == "shalaev"
    assert translit_slug("Щукин И.") == "schukin"
    assert translit_slug("Юрьев") == "yurev"
    assert translit_slug("") == ""


def test__normalize_team_authors__derives_and_dedupes() -> None:
    authors = normalize_team_authors(
        [
            Author(name="Шалаев Алексей"),
            Author(name="Шалаев Пётр"),
            Author(name="Иванов Иван", slug="ivanov"),
        ]
    )
    assert [a.slug for a in authors] == ["shalaev", "shalaev2", "ivanov"]


def test__normalize_team_authors__reserved_slug_shifted() -> None:
    authors = normalize_team_authors([Author(name="Иванов", slug="shared")])
    assert authors[0].slug == "shared2"


def test__normalize_team_authors__blank_draft_kept_unmanaged() -> None:
    # Пустая строка автора из настроек — черновик: не падаем, слаг не выводим,
    # managed принудительно снимается (комплект без слага вести нельзя).
    authors = normalize_team_authors([Author(name="Шалаев Алексей"), Author(name="", managed=True)])
    assert authors[0].slug == "shalaev"
    assert authors[1].slug is None
    assert authors[1].managed is False


# ── instantiate_missing_base_parts (новые доки пака в существующей базе) ──


def _missing_parts_env(tmp_path: Path) -> tuple[Project, MagicMock]:
    """Пак с двумя shared-доками; shared-база материализована ДО появления
    второго (pmi_shared) и содержит правки студента."""
    files_dir = tmp_path / "packs" / "p" / "templates" / "t" / "versions" / "1" / "files"
    (files_dir / "tz_shared").mkdir(parents=True)
    (files_dir / "tz_shared" / "tz_shared.tex").write_text("pack tz", encoding="utf-8")
    (files_dir / "pmi_shared").mkdir()
    (files_dir / "pmi_shared" / "pmi_shared.tex").write_text("pack pmi {{ project.name }}", encoding="utf-8")
    (files_dir / "common").mkdir()
    (files_dir / "common" / "preamble.tex").write_text("pack preamble", encoding="utf-8")
    (files_dir / ".latexmkrc").write_text("pack rc", encoding="utf-8")

    project = _team_project()
    project.folder = tmp_path / "project"
    shared = project.folder / "shared"
    (shared / "tz_shared").mkdir(parents=True)
    (shared / "tz_shared" / "tz_shared.tex").write_text("edited by student", encoding="utf-8")
    (shared / "common").mkdir()
    (shared / "common" / "preamble.tex").write_text("edited preamble", encoding="utf-8")
    (shared / ".latexmkrc").write_text("edited rc", encoding="utf-8")

    template_repo = MagicMock()
    template_repo._packs_dir = str(tmp_path / "packs")
    template_repo.list_packs.return_value = [SimpleNamespace(id="p", templates=[SimpleNamespace(id="t")])]
    return project, template_repo


def test__instantiate_missing_base_parts__adds_only_new_doc_dir(tmp_path: Path) -> None:
    project, template_repo = _missing_parts_env(tmp_path)
    version = _version(
        (
            _doc_def("tz_shared", scope="shared", staffing=("team",)),
            _doc_def("pmi_shared", scope="shared", staffing=("team",)),
            _doc_def("vkr"),  # personal — в shared-базу не попадает
        )
    )

    added = instantiate_missing_base_parts(
        project=project,
        version=version,
        template_repo=template_repo,
        renderer=TemplateRenderer(),
        base_dir="shared",
        author=None,
    )

    shared = project.folder / "shared"
    assert added == ["pmi_shared"]
    assert (shared / "pmi_shared" / "pmi_shared.tex").read_text(encoding="utf-8") == "pack pmi Система X"
    # Существующие файлы базы (правки студента) не перезаписаны.
    assert (shared / "tz_shared" / "tz_shared.tex").read_text(encoding="utf-8") == "edited by student"
    assert (shared / "common" / "preamble.tex").read_text(encoding="utf-8") == "edited preamble"
    assert (shared / ".latexmkrc").read_text(encoding="utf-8") == "edited rc"
    assert not (shared / "vkr").exists()


def test__instantiate_missing_base_parts__noop_when_base_complete(tmp_path: Path) -> None:
    project, template_repo = _missing_parts_env(tmp_path)
    version = _version((_doc_def("tz_shared", scope="shared", staffing=("team",)),))

    added = instantiate_missing_base_parts(
        project=project,
        version=version,
        template_repo=template_repo,
        renderer=TemplateRenderer(),
        base_dir="shared",
        author=None,
    )

    assert added == []
    assert (project.folder / "shared" / "tz_shared" / "tz_shared.tex").read_text(encoding="utf-8") == (
        "edited by student"
    )


def test__instance_id_roundtrip() -> None:
    assert doc_instance_id("vkr", "ivanov") == "vkr--ivanov"
    assert doc_instance_id("tz_shared", None) == "tz_shared"
    assert split_instance_id("vkr--ivanov") == ("vkr", "ivanov")
    assert split_instance_id("tz_shared") == ("tz_shared", None)


def test__project_bases__team() -> None:
    project = _team_project()
    assert project_bases(project) == [
        ("shared", None),
        ("shalaev", project.authors[0]),
        ("ivanov", project.authors[1]),
    ]


# ── инстансы документов ───────────────────────────────────────────────────

_DOCS = (
    _doc_def("tz", scope="personal"),
    _doc_def("tz_shared", scope="shared", staffing=("team",)),
    _doc_def("vkr", scope="personal"),
)


def test__build_documents__team_instances() -> None:
    version = _version(_DOCS)
    project = _team_project()

    docs = _build_documents(
        version, None, ProjectStaffing.team, project.authors, shared_enabled=True, kind=ProjectKind.project
    )

    ids = sorted(d.id for d in docs)
    assert ids == ["tz--ivanov", "tz--shalaev", "tz_shared", "vkr--ivanov", "vkr--shalaev"]
    shared = next(d for d in docs if d.id == "tz_shared")
    assert shared.owner is None
    assert shared.def_id == "tz_shared"
    personal = next(d for d in docs if d.id == "vkr--ivanov")
    assert personal.owner == "ivanov"
    assert personal.def_id == "vkr"


def test__build_documents__solo_skips_team_only_docs() -> None:
    version = _version(_DOCS)

    docs = _build_documents(
        version, None, ProjectStaffing.solo, [Author(name="Оди Ночка")], shared_enabled=True, kind=ProjectKind.project
    )

    assert sorted(d.id for d in docs) == ["tz", "vkr"]
    assert all(d.def_id == d.id and d.owner is None for d in docs)


@pytest.fixture
def team_project_vkr_and_shared_tz() -> Project:
    return _team_project(
        documents=[
            Document("vkr--shalaev", DocumentStatus.draft, None, None, ChecksOverride(), "vkr", "shalaev"),
            Document("tz_shared", DocumentStatus.draft, None, None, ChecksOverride(), "tz_shared", None),
        ]
    )


def test__resolve_instance_source__prefixes_owner_base(team_project_vkr_and_shared_tz: Project) -> None:
    version = _version(_DOCS)
    project = team_project_vkr_and_shared_tz
    svc = ProjectTemplateService()

    assert svc.resolve_instance_source(project, project.documents[0], version) == (
        "shalaev/vkr/vkr.tex",
        "shalaev/vkr/vkr.pdf",
    )
    assert svc.resolve_instance_source(project, project.documents[1], version) == (
        "shared/tz_shared/tz_shared.tex",
        "shared/tz_shared/tz_shared.pdf",
    )


def test__instance_dir_map__maps_owner_prefixed_dirs_to_doc_ids(team_project_vkr_and_shared_tz: Project) -> None:
    version = _version(_DOCS)
    project = team_project_vkr_and_shared_tz
    svc = ProjectTemplateService()

    dir_map = svc.instance_dir_map(project, version)

    assert dir_map["shalaev/vkr"] == "vkr--shalaev"
    assert dir_map["shared/tz_shared"] == "tz_shared"


# ── подписи ───────────────────────────────────────────────────────────────

_SLOTS = (
    SignatureSlotDef(
        id="author",
        label={"ru": "Автор работы"},
        applies_to=("tz", "tz_shared", "vkr"),
        default_placement=SignatureDefaultPlacement(page=1, x_mm=1, y_mm=2, width_mm=3),
        per_author=True,
    ),
    SignatureSlotDef(
        id="supervisor",
        label={"ru": "Научный руководитель"},
        applies_to=("tz", "tz_shared", "vkr"),
        default_placement=SignatureDefaultPlacement(page=1, x_mm=1, y_mm=2, width_mm=3),
    ),
)


def test__runtime_slots__per_author_expansion(team_project_vkr_and_shared_tz: Project) -> None:
    version = _version(_DOCS, slots=_SLOTS)
    project = team_project_vkr_and_shared_tz
    svc = SignatureSlotService()

    slots = svc.runtime_slots(project, version)

    assert [s.id for s in slots] == ["author--shalaev", "author--ivanov", "supervisor"]
    shalaev_slot = slots[0]
    ivanov_slot = slots[1]
    supervisor = slots[2]
    assert "Шалаев" in shalaev_slot.label["ru"]
    # Личный док подписывает владелец; общее ТЗ — все авторы; научрук — везде.
    personal, shared = project.documents
    assert svc.slot_applies_to_doc(shalaev_slot, personal) is True
    assert svc.slot_applies_to_doc(ivanov_slot, personal) is False
    assert svc.slot_applies_to_doc(shalaev_slot, shared) is True
    assert svc.slot_applies_to_doc(ivanov_slot, shared) is True
    assert svc.slot_applies_to_doc(supervisor, personal) is True


# ── обязательность подписи выводится из профилей сдачи ────────────────────
#
# Отдельного поля `required_for` у слота больше нет: обязательность — свойство
# пары «документ + контрольная точка». Пока поле существовало, оно разошлось с
# профилями (11 пар в ВКР, 5 в курсовой): панель размещения молчала о подписи,
# которую финальный комплект затем требовал, и упаковка отказывала.

_CP_EARLY = SubmissionProfile(
    id="checkpoint-2",
    name={"ru": "КТ2", "en": "CP2"},
    description={"ru": ""},
    items=(SubmissionDocItem(doc_id="tz", signatures=("author",)),),
    extra_items=(),
)
_CP_FINAL = SubmissionProfile(
    id="final",
    name={"ru": "Итоговая сдача", "en": "Final"},
    description={"ru": ""},
    items=(
        SubmissionDocItem(doc_id="tz", signatures=("author", "supervisor")),
        SubmissionDocItem(doc_id="vkr", signatures=("supervisor",)),
    ),
    extra_items=(),
)


@pytest.fixture
def solo_project_tz_and_vkr() -> Project:
    project = _team_project(
        documents=[
            Document("tz", DocumentStatus.draft, None, None, ChecksOverride(), "tz", None),
            Document("vkr", DocumentStatus.draft, None, None, ChecksOverride(), "vkr", None),
        ]
    )
    return replace(project, staffing=ProjectStaffing.solo, authors=[project.authors[0]])


def test__required_by_profiles__reports_every_checkpoint_that_demands_the_signature(
    solo_project_tz_and_vkr: Project,
) -> None:
    version = _version(_DOCS, slots=_SLOTS, profiles=(_CP_EARLY, _CP_FINAL))

    required = SignatureSlotService().required_by_profiles(solo_project_tz_and_vkr, version)

    # ТЗ подписывает автор на обеих точках — обе и должны быть названы.
    assert required["author"]["tz"] == ("checkpoint-2", "final")


def test__required_by_profiles__signature_needed_only_at_the_final_checkpoint(
    solo_project_tz_and_vkr: Project,
) -> None:
    version = _version(_DOCS, slots=_SLOTS, profiles=(_CP_EARLY, _CP_FINAL))

    required = SignatureSlotService().required_by_profiles(solo_project_tz_and_vkr, version)

    # Ровно тот случай, ради которого поле и убрано: на КТ2 подписи научрука на
    # ТЗ нет, на итоговой — есть. Статическим полем это не выражалось.
    assert required["supervisor"]["tz"] == ("final",)


def test__required_by_profiles__applicable_but_never_demanded_slot_is_absent(
    solo_project_tz_and_vkr: Project,
) -> None:
    version = _version(_DOCS, slots=_SLOTS, profiles=(_CP_EARLY,))

    required = SignatureSlotService().required_by_profiles(solo_project_tz_and_vkr, version)

    # Научрук применим к ТЗ (applies_to), но ни один профиль его не требует.
    assert "supervisor" not in required


def test__required_by_profiles__without_profiles__is_empty(solo_project_tz_and_vkr: Project) -> None:
    version = _version(_DOCS, slots=_SLOTS)

    assert SignatureSlotService().required_by_profiles(solo_project_tz_and_vkr, version) == {}


def test__required_by_profiles__team_expands_per_author_slots(
    team_project_vkr_and_shared_tz: Project,
) -> None:
    shared_final = SubmissionProfile(
        id="final",
        name={"ru": "Итоговая сдача"},
        description={"ru": ""},
        items=(SubmissionDocItem(doc_id="tz_shared", signatures=("author",)),),
        extra_items=(),
    )
    version = _version(_DOCS, slots=_SLOTS, profiles=(shared_final,))

    required = SignatureSlotService().required_by_profiles(team_project_vkr_and_shared_tz, version)

    # Общий документ команды подписывают ОБА автора — по одному рантайм-слоту
    # на каждого, а не один общий.
    assert required["author--shalaev"]["tz_shared"] == ("final",)
    assert required["author--ivanov"]["tz_shared"] == ("final",)


def test__required_by_profiles__item_of_another_project_kind_is_skipped(
    solo_project_tz_and_vkr: Project,
) -> None:
    research_only = SubmissionProfile(
        id="final",
        name={"ru": "Итоговая сдача"},
        description={"ru": ""},
        items=(SubmissionDocItem(doc_id="tz", signatures=("author",), supported_kinds=("research",)),),
        extra_items=(),
    )
    version = _version(_DOCS, slots=_SLOTS, profiles=(research_only,))

    # Проект прикладной: пункт в комплект не входит, значит и подпись не нужна.
    assert SignatureSlotService().required_by_profiles(solo_project_tz_and_vkr, version) == {}


# ── сдача ─────────────────────────────────────────────────────────────────


def test__build_item_list__team_expands_instances_and_slots() -> None:
    version = _version(_DOCS, slots=_SLOTS)
    project = _team_project(
        documents=[
            Document("vkr--shalaev", DocumentStatus.draft, None, None, ChecksOverride(), "vkr", "shalaev"),
            Document("vkr--ivanov", DocumentStatus.draft, None, None, ChecksOverride(), "vkr", "ivanov"),
            Document("tz_shared", DocumentStatus.draft, None, None, ChecksOverride(), "tz_shared", None),
        ]
    )
    profile = SubmissionProfile(
        id="final",
        name={"ru": "Финал"},
        description={"ru": ""},
        items=(
            SubmissionDocItem(doc_id="vkr", signatures=("author",)),
            SubmissionDocItem(doc_id="tz_shared", signatures=("author",)),
        ),
        extra_items=(),
    )
    slot = SignatureSlot(png_path="s.png", natural_width_px=None, natural_height_px=None)
    placement = SignaturePlacement(enabled=True, page=1, x_mm=1, y_mm=2, width_mm=3)
    sig_state = SignaturesState(
        slots={"author--shalaev": slot, "author--ivanov": slot},
        placements={
            "vkr--shalaev": {"author--shalaev": placement},
            "tz_shared": {"author--shalaev": placement, "author--ivanov": placement},
        },
    )

    result = SubmissionProfileService().build_item_list(profile, project, version, sig_state, author_slug="shalaev")

    by_id = {item.doc_id: item for item in result}
    # Пакет Шалаева: его ВКР (ивановская не попала) + общее ТЗ с подписями всех.
    assert set(by_id) == {"vkr--shalaev", "tz_shared"}
    assert by_id["vkr--shalaev"].signatures == ("author--shalaev",)
    assert set(by_id["tz_shared"].signatures) == {"author--shalaev", "author--ivanov"}


def test__build_item_list__team_requires_author() -> None:
    version = _version(_DOCS, slots=_SLOTS)
    profile = SubmissionProfile(id="p", name={"ru": ""}, description={"ru": ""}, items=(), extra_items=())

    with pytest.raises(ValueError, match="автора"):
        SubmissionProfileService().build_item_list(profile, _team_project(), version, SignaturesState.empty())


def test__build_item_list__known_but_missing_def_is_skipped() -> None:
    version = _version(_DOCS, slots=_SLOTS)
    project = _team_project(
        documents=[Document("vkr--shalaev", DocumentStatus.draft, None, None, ChecksOverride(), "vkr", "shalaev")],
        shared_enabled=False,
    )
    profile = SubmissionProfile(
        id="p",
        name={"ru": ""},
        description={"ru": ""},
        items=(SubmissionDocItem(doc_id="tz_shared", signatures=()),),
        extra_items=(),
    )

    result = SubmissionProfileService().build_item_list(
        profile, project, version, SignaturesState.empty(), author_slug="shalaev"
    )

    assert result == []


# ── формы ─────────────────────────────────────────────────────────────────


def test__resolve_form_instance__team_per_author_id__resolves_form_and_author() -> None:
    version = _version(_DOCS)
    team = _team_project()

    form, author = resolve_form_instance(team, version, "ai_declaration--ivanov")

    assert form.id == "ai_declaration"
    assert author is not None
    assert author.slug == "ivanov"


def test__resolve_form_instance__per_author_form_addressed_by_base_id_in_team__raises_value_error() -> None:
    version = _version(_DOCS)
    team = _team_project()

    # per-author форма в team не адресуется базовым id
    with pytest.raises(ValueError, match="персональная"):
        resolve_form_instance(team, version, "ai_declaration")


def test__resolve_form_instance__non_per_author_form_with_instance_suffix__raises_value_error() -> None:
    version = _version(_DOCS)
    team = _team_project()

    # обычная форма — без инстансов
    with pytest.raises(ValueError, match="нет персональных инстансов"):
        resolve_form_instance(team, version, "feedback--ivanov")


def test__resolve_form_instance__solo_base_id__resolves_form_without_author() -> None:
    version = _version(_DOCS)
    solo = _team_project()
    solo.staffing = ProjectStaffing.solo

    # solo — базовый id работает как раньше
    form, author = resolve_form_instance(solo, version, "ai_declaration")

    assert form.id == "ai_declaration"
    assert author is None
