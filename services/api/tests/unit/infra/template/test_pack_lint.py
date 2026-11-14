"""
Инвариант состава пакета: анкета, которую профиль сдачи кладёт в архив, обязана
быть required_for_pack.

Про состав говорят два независимых места пака — `extra_items` профиля (что
реально уедет) и флаг самой формы (о чём приложение предупреждает). Пока они
могут разъехаться молча, студент отправляет незаполненную анкету и не узнаёт
об этом: расчёт готовности засчитывает только пересечение.
"""

from pathlib import Path

import pytest
import yaml
from hse_doc_studio.infra.template.pack_lint import lint_version_dir

# .../services/api/tests/unit/infra/template/<this> → корень репозитория.
PACKS_ROOT = Path(__file__).resolve().parents[6] / "packs"


def _real_version_dirs() -> list[Path]:
    """Все версии всех шаблонов всех паков репозитория (новый пак проверяется сам)."""
    dirs = sorted(p for p in PACKS_ROOT.glob("*/templates/*/versions/*") if p.is_dir())
    assert dirs, f"в {PACKS_ROOT} не найдено ни одной версии шаблона"
    return dirs


def _write_version(version_dir: Path, manifest: dict) -> None:
    (version_dir / "files").mkdir(parents=True, exist_ok=True)
    (version_dir / "version.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8", newline="\n"
    )


def _manifest(*, required_for_pack: bool) -> dict:
    return {
        "langs": ["ru"],
        "documents": [],
        "forms": [
            {"id": "code_link", "required_for_pack": required_for_pack},
        ],
        "pack_submission": {
            "profiles": [
                {
                    "id": "final",
                    "items": [],
                    "extra_items": [
                        {
                            "source": ".hse-studio/forms/code_link.json",
                            "output_name": "Ссылка на код.txt",
                            "format": "markdown",
                        }
                    ],
                }
            ]
        },
    }


def test__lint_version_dir__packed_form_not_required_for_pack__reports_error(tmp_path: Path) -> None:
    _write_version(tmp_path, _manifest(required_for_pack=False))

    report = lint_version_dir(tmp_path)

    assert not report.ok
    assert any("code_link" in e and "required_for_pack" in e for e in report.errors)


def test__lint_version_dir__packed_form_required_for_pack__reports_no_error(tmp_path: Path) -> None:
    _write_version(tmp_path, _manifest(required_for_pack=True))

    report = lint_version_dir(tmp_path)

    assert [e for e in report.errors if "code_link" in e] == []


def test__lint_version_dir__extra_item_points_at_unknown_form__reports_error(tmp_path: Path) -> None:
    manifest = _manifest(required_for_pack=True)
    manifest["forms"] = []

    _write_version(tmp_path, manifest)
    report = lint_version_dir(tmp_path)

    assert any("code_link" in e and "forms:" in e for e in report.errors)


def test__lint_version_dir__non_form_extra_item__is_ignored(tmp_path: Path) -> None:
    # Скан NDA и прочие файлы приезжают тем же механизмом extra_items, но формой
    # не являются — правило не должно их трогать.
    manifest = _manifest(required_for_pack=True)
    manifest["pack_submission"]["profiles"][0]["extra_items"] = [
        {"source": ".hse-studio/nda/scan.pdf", "output_name": "NDA.pdf"}
    ]

    _write_version(tmp_path, manifest)
    report = lint_version_dir(tmp_path)

    assert report.errors == []


def test__lint_version_dir__real_packs__satisfy_the_invariant() -> None:
    # Сам пак обязан быть чистым: правило появилось из реального расхождения
    # («Ссылка на код» уезжала в пакет ПДП/ГИА с required_for_pack: false).
    for version_dir in _real_version_dirs():
        report = lint_version_dir(version_dir)

        assert report.errors == [], f"{version_dir}: {report.errors}"


# ── двуязычные заметки версии (`changes:`, заменили CHANGELOG.md шаблона) ──


def _manifest_with_changes(changes: object) -> dict:
    manifest = _manifest(required_for_pack=True)
    manifest["changes"] = changes
    return manifest


def test__lint_version_dir__changes_absent__is_allowed(tmp_path: Path) -> None:
    # Блок необязателен: пак без заметок остаётся валидным паком.
    _write_version(tmp_path, _manifest(required_for_pack=True))

    assert lint_version_dir(tmp_path).errors == []


def test__lint_version_dir__changes_bilingual_and_parallel__reports_no_error(tmp_path: Path) -> None:
    _write_version(tmp_path, _manifest_with_changes({"ru": ["Раз", "Два"], "en": ["One", "Two"]}))

    assert [e for e in lint_version_dir(tmp_path).errors if "changes" in e] == []


def test__lint_version_dir__changes_missing_a_language__reports_error(tmp_path: Path) -> None:
    # Пропущенный перевод виден только в другой локали интерфейса, где его уже
    # некому заметить.
    _write_version(tmp_path, _manifest_with_changes({"ru": ["Раз"]}))

    assert any("changes.en" in e for e in lint_version_dir(tmp_path).errors)


def test__lint_version_dir__changes_of_different_length__reports_error(tmp_path: Path) -> None:
    # Разъехавшиеся списки означают, что языки описывают РАЗНЫЕ наборы фактов.
    _write_version(tmp_path, _manifest_with_changes({"ru": ["Раз", "Два"], "en": ["One"]}))

    assert any("разной длины" in e for e in lint_version_dir(tmp_path).errors)


def test__lint_version_dir__changes_with_a_blank_item__reports_error(tmp_path: Path) -> None:
    _write_version(tmp_path, _manifest_with_changes({"ru": ["Раз", "   "], "en": ["One", "Two"]}))

    assert any("пустой пункт" in e for e in lint_version_dir(tmp_path).errors)


def test__lint_version_dir__real_packs__carry_bilingual_release_notes() -> None:
    # Заметки — данные без тайпчекера; сам пак обязан быть чистым.
    for version_dir in _real_version_dirs():
        manifest = yaml.safe_load((version_dir / "version.yaml").read_text(encoding="utf-8"))

        changes = manifest.get("changes", {})

        assert changes.get("ru"), f"{version_dir}: нет русских заметок о версии"
        assert len(changes["ru"]) == len(changes["en"]), version_dir
        assert lint_version_dir(version_dir).errors == [], version_dir


# ── порядок маршрута подписания (`signatures.route`, `signing_route` профиля) ──


def _manifest_with_route(route: object, profile_route: object = None) -> dict:
    manifest = _manifest(required_for_pack=True)
    manifest["signatures"] = {
        "slots": [{"id": "author"}, {"id": "supervisor"}, {"id": "academic_supervisor"}],
        "route": route,
    }
    if profile_route is not None:
        manifest["pack_submission"]["profiles"][0]["signing_route"] = profile_route
    return manifest


def test__lint_version_dir__signing_route_of_declared_slots__reports_no_error(tmp_path: Path) -> None:
    _write_version(tmp_path, _manifest_with_route([["author"], ["supervisor", "academic_supervisor"]], ["author"]))

    assert lint_version_dir(tmp_path).errors == []


def test__lint_version_dir__signing_route_unknown_slot__reports_error(tmp_path: Path) -> None:
    _write_version(tmp_path, _manifest_with_route([["author"], ["dean"]]))

    errors = lint_version_dir(tmp_path).errors

    assert any("signatures.route" in e and "'dean'" in e for e in errors)


def test__lint_version_dir__signing_route_repeated_slot__reports_error(tmp_path: Path) -> None:
    _write_version(tmp_path, _manifest_with_route([["author"]], [["author"], ["supervisor", "author"]]))

    errors = lint_version_dir(tmp_path).errors

    assert any("final" in e and "signing_route" in e and "дважды" in e for e in errors)


@pytest.mark.parametrize("route", [{"first": "author"}, [["author--ivanov"]], [[1]]])
def test__lint_version_dir__signing_route_malformed__reports_error(tmp_path: Path, route: object) -> None:
    _write_version(tmp_path, _manifest_with_route(route))

    assert any(e.startswith("signatures.route:") for e in lint_version_dir(tmp_path).errors)


# ── подсказка срока точки (`deadline_hint`, signing-route.md, 16.4) ──


def _manifest_with_hint(hint: object) -> dict:
    manifest = _manifest(required_for_pack=True)
    manifest["pack_submission"]["profiles"][0]["deadline_hint"] = hint
    return manifest


def test__lint_version_dir__deadline_hint_without_dates__no_error(tmp_path: Path) -> None:
    hint = {
        "ru": "Обычно в середине ноября, точную дату объявляют в SmartLMS",
        "en": "Usually mid-November; the exact date is announced in SmartLMS",
    }
    _write_version(tmp_path, _manifest_with_hint(hint))

    assert lint_version_dir(tmp_path).errors == []


@pytest.mark.parametrize(
    ("hint", "fragment"),
    [
        (
            {"ru": "Жёсткий дедлайн 15 ноября 23:59", "en": "Usually mid-November"},
            "deadline_hint.ru names a concrete date",
        ),
        ({"ru": "Обычно в середине ноября", "en": "By 2026-11-15"}, "deadline_hint.en names a concrete date"),
        ({"ru": "До 15.11.2026", "en": "Usually mid-November"}, "concrete date"),
        ({"ru": "Обычно в середине ноября", "en": "Hard deadline November 15"}, "concrete date"),
        ({"ru": "Обычно в середине ноября"}, "deadline_hint.en is missing"),
        ({"ru": "я" * 201, "en": "Usually mid-November"}, "longer than 200"),
        ("Обычно в середине ноября", "must be a mapping"),
    ],
)
def test__lint_version_dir__deadline_hint_broken__reports_error(tmp_path: Path, hint: object, fragment: str) -> None:
    _write_version(tmp_path, _manifest_with_hint(hint))

    errors = lint_version_dir(tmp_path).errors

    assert any(e.startswith("профиль final:") and fragment in e for e in errors), errors


# ── метки даты по умолчанию (`default_dates`, signing-route.md, 14.10) ──


def _manifest_with_dates(default_dates: object) -> dict:
    manifest = _manifest(required_for_pack=True)
    manifest["signatures"] = {
        "slots": [{"id": "supervisor", "applies_to": ["project_proposal"], "default_dates": default_dates}]
    }
    return manifest


def test__lint_version_dir__default_dates_inside_a4__no_error(tmp_path: Path) -> None:
    marks = [
        {"page": 2, "x_mm": 120, "y_mm": 250, "width_mm": 8, "height_mm": 5, "format": "day"},
        {"page": 2, "x_mm": 132, "y_mm": 250, "width_mm": 22, "height_mm": 5, "format": "month_word", "align": "left"},
    ]
    _write_version(tmp_path, _manifest_with_dates({"project_proposal": marks}))

    assert lint_version_dir(tmp_path).errors == []


@pytest.mark.parametrize(
    ("dates", "fragment"),
    [
        ({"project_proposal": [{"page": 1, "x_mm": 205, "y_mm": 10, "width_mm": 8, "height_mm": 5, "format": "day"}]},
         "past the edge of the 210 x 297 mm page"),
        ({"project_proposal": [{"page": 0, "x_mm": 5, "y_mm": 10, "width_mm": 8, "height_mm": 5, "format": "day"}]},
         "before the first page"),
        ({"project_proposal": [{"page": 1, "x_mm": 5, "y_mm": 10, "width_mm": 8, "height_mm": 5, "format": "era"}]},
         "era"),
        ({"project_proposal": [{"page": 1, "x_mm": 5, "y_mm": 1, "width_mm": 8, "height_mm": 5, "format": "day"}] * 9},
         "more than 8"),
        ({"thesis": [{"page": 1, "x_mm": 5, "y_mm": 10, "width_mm": 8, "height_mm": 5, "format": "day"}]},
         "applies_to"),
        (["day"], "mapping"),
    ],
)  # fmt: skip
def test__lint_version_dir__default_dates_wrong__reports_error(tmp_path: Path, dates: object, fragment: str) -> None:
    _write_version(tmp_path, _manifest_with_dates(dates))

    errors = lint_version_dir(tmp_path).errors

    assert any(e.startswith("signatures.slots[supervisor]") and fragment in e for e in errors), errors


# ── пресет маршрута из пака (`placements`, `signing_slots`, signing-route.md, 15.8) ──


def _manifest_with_preset(*, placements: object = None, signing_slots: object = None, **overrides: object) -> dict:
    """КП с документами точки «Заявка на тему» и каталогом из четырёх слотов, как `hse-cs-sse`."""
    manifest = _manifest(required_for_pack=True)
    manifest["documents"] = [
        {"id": "project_proposal", "source_file": "p.tex"},
        {"id": "topic_application", "source_file": "t.tex"},
    ]
    supervisor: dict = {"id": "supervisor", "applies_to": ["project_proposal", "topic_application"]}
    if placements is not None:
        supervisor["placements"] = placements
    manifest["signatures"] = {
        "slots": [
            {"id": "author", "applies_to": ["topic_application"], "required": True},
            supervisor,
            {"id": "co_supervisor", "applies_to": ["topic_application"]},
            {"id": "academic_supervisor", "applies_to": ["topic_application"]},
        ]
    }
    profile: dict = {
        "id": "topic-approval",
        "items": [
            {"doc_id": "project_proposal", "signatures": ["supervisor"], "methods": {"supervisor": ["image"]}},
            {"doc_id": "topic_application", "signatures": ["author", "supervisor"]},
        ],
    }
    if signing_slots is not None:
        profile["signing_slots"] = signing_slots
    manifest["pack_submission"]["profiles"] = [profile]
    manifest.update(overrides)
    return manifest


def _write_preset(version_dir: Path, manifest: dict) -> None:
    _write_version(version_dir, manifest)
    for name in ("p.tex", "t.tex"):
        (version_dir / "files" / name).write_text("\\documentclass{article}\n", encoding="utf-8")


def test__lint_version_dir__preset_of_the_design__no_errors_no_warnings(tmp_path: Path) -> None:
    _write_preset(
        tmp_path,
        _manifest_with_preset(
            placements={
                "project_proposal": {"page": 1, "x_mm": 80, "y_mm": 139, "width_mm": 40},
                "topic_application": {"page": 1, "x_mm": 100, "y_mm": 168, "width_mm": 70},
            },
            signing_slots=[
                {"doc_id": "topic_application", "slot_id": "co_supervisor", "when": {"person": "co_supervisor"}},
                {"doc_id": "topic_application", "slot_id": "academic_supervisor",
                 "when": {"person": "supervisor", "role": "company"}},
                {"doc_id": "topic_application", "slot_id": "supervisor", "optional": False},
            ],
        ),
    )  # fmt: skip

    report = lint_version_dir(tmp_path)

    assert report.errors == []
    assert [w for w in report.warnings if "signatures" in w or "signing_slots" in w] == []


@pytest.mark.parametrize(
    ("placements", "fragment"),
    [
        ({"project_proposal": {"page": 1, "x_mm": 190, "y_mm": 139, "width_mm": 40}}, "left or right edge"),
        ({"project_proposal": {"page": 1, "x_mm": 80, "y_mm": 139, "width_mm": 4}}, "width_mm 4"),
        ({"report": {"page": 1, "x_mm": 80, "y_mm": 139, "width_mm": 40}}, "applies_to"),
        (["project_proposal"], "mapping"),
    ],
)
def test__lint_version_dir__placements_wrong__reports_error(tmp_path: Path, placements: object, fragment: str) -> None:
    _write_preset(tmp_path, _manifest_with_preset(placements=placements))

    errors = lint_version_dir(tmp_path).errors

    assert any(e.startswith("signatures.slots[supervisor]") and fragment in e for e in errors), errors


def test__lint_version_dir__placement_of_a_document_not_in_the_version__reports_error(tmp_path: Path) -> None:
    manifest = _manifest_with_preset(placements={"report": {"page": 1, "x_mm": 80, "y_mm": 139, "width_mm": 40}})
    manifest["signatures"]["slots"][1]["applies_to"].append("report")
    _write_preset(tmp_path, manifest)

    errors = lint_version_dir(tmp_path).errors

    assert any("placements.report" in e and "documents" in e for e in errors), errors


@pytest.mark.parametrize(
    ("entry", "fragment"),
    [
        ({"doc_id": "report", "slot_id": "supervisor"}, "документа нет в items"),
        ({"doc_id": "topic_application", "slot_id": "dean"}, "не объявлен"),
        ({"doc_id": "project_proposal", "slot_id": "author"}, "не применим"),
        ({"doc_id": "topic_application", "slot_id": "supervisor", "when": {"person": "supervisor"}}, "when только"),
        ({"doc_id": "topic_application", "slot_id": "author", "optional": True}, "required: true"),
        ({"doc_id": "topic_application", "slot_id": "co_supervisor", "when": {"person": "dean"}}, "when.person"),
        ({"doc_id": "topic_application", "slot_id": "co_supervisor", "when": {"meta": "nda"}}, "unknown condition"),
    ],
)
def test__lint_version_dir__signing_slots_wrong__reports_error(tmp_path: Path, entry: dict, fragment: str) -> None:
    _write_preset(tmp_path, _manifest_with_preset(signing_slots=[entry]))

    errors = lint_version_dir(tmp_path).errors

    assert any(e.startswith("профиль topic-approval") and fragment in e for e in errors), errors


def test__lint_version_dir__signing_slots_repeated_pair__reports_error(tmp_path: Path) -> None:
    entry = {"doc_id": "topic_application", "slot_id": "co_supervisor"}
    _write_preset(tmp_path, _manifest_with_preset(signing_slots=[entry, entry]))

    assert any("дважды" in e for e in lint_version_dir(tmp_path).errors)


def test__lint_version_dir__extra_slot_missing_from_the_route__warns(tmp_path: Path) -> None:
    manifest = _manifest_with_preset(signing_slots=[{"doc_id": "topic_application", "slot_id": "academic_supervisor"}])
    manifest["pack_submission"]["profiles"][0]["signing_route"] = [["author"], ["supervisor"]]
    _write_preset(tmp_path, manifest)

    report = lint_version_dir(tmp_path)

    assert report.errors == []
    assert any("'academic_supervisor'" in w and "последним шагом" in w for w in report.warnings), report.warnings


def test__lint_version_dir__per_author_place_on_a_shared_document_of_a_team_template__warns(tmp_path: Path) -> None:
    manifest = _manifest_with_preset(supported_staffing=["solo", "team"])
    author = manifest["signatures"]["slots"][0]
    author.update(per_author=True, placements={"topic_application": {"x_mm": 135, "y_mm": 200, "width_mm": 70}})
    _write_preset(tmp_path, manifest)

    report = lint_version_dir(tmp_path)

    assert report.errors == []
    assert any("per_author" in w and "topic_application" in w for w in report.warnings), report.warnings


def test__lint_version_dir__narrow_place_where_detached_is_allowed__warns_and_errors_past_the_left_edge(
    tmp_path: Path,
) -> None:
    placements = {
        # Пункт заявления не ограничивает способы: ЭП разрешена, рамка 40 мм расширится до 70 влево.
        "topic_application": {"page": 1, "x_mm": 163, "y_mm": 168, "width_mm": 40},
        # Описание проекта разрешает только картинку: узкое место не предупреждение.
        "project_proposal": {"page": 1, "x_mm": 0, "y_mm": 139, "width_mm": 40},
    }
    _write_preset(tmp_path, _manifest_with_preset(placements=placements))
    report = lint_version_dir(tmp_path)
    assert report.errors == []
    expected = (
        "signatures.slots[supervisor]: placements.topic_application: место уже плашки открепленной ЭП, при подписи ЭП "
        "рамка расширится до 70 мм влево"
    )
    assert [w for w in report.warnings if "плашки" in w] == [expected]

    placements["topic_application"]["x_mm"] = 10
    _write_preset(tmp_path, _manifest_with_preset(placements=placements))

    assert any("левый край" in e for e in lint_version_dir(tmp_path).errors)


# ── Безопасность пака (template-studio.md, раздел 9) ────────────


def _safety_version(tmp_path: Path, **manifest_extra: object) -> Path:
    version_dir = tmp_path / "v"
    _write_version(version_dir, {"langs": ["ru"], "documents": [], **manifest_extra})
    (version_dir / "files" / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
    return version_dir


def test_symlink_in_pack_is_an_error(tmp_path: Path) -> None:
    version_dir = _safety_version(tmp_path)
    try:
        (version_dir / "files" / "passwd.tex").symlink_to("/etc/passwd")
        (version_dir / "files" / "outside").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("символические ссылки недоступны (Windows без прав разработчика)")
    errors = lint_version_dir(version_dir).errors
    assert any("files/passwd.tex: символическая ссылка" in e for e in errors)
    assert any("files/outside: символическая ссылка" in e for e in errors)


@pytest.mark.parametrize(
    ("secret", "label"),
    [
        ("ghp_" + "a1B2" * 9, "токен GitHub"),
        ("github_pat_" + "x" * 30, "токен GitHub"),
        ("glpat-" + "y" * 20, "токен GitLab"),
        ("-----BEGIN OPENSSH PRIVATE KEY-----", "закрытый ключ"),
        ("-----BEGIN PRIVATE KEY-----", "закрытый ключ"),
    ],
)
def test_secret_in_pack_is_an_error_without_leaking_it(tmp_path: Path, secret: str, label: str) -> None:
    version_dir = _safety_version(tmp_path)
    (version_dir / "files" / "common").mkdir()
    (version_dir / "files" / "common" / "ci.yml").write_text(f"token: {secret}\n", encoding="utf-8")
    errors = lint_version_dir(version_dir).errors
    assert f"files/common/ci.yml: похоже на {label}, секретам не место в паке" in errors
    assert not any(secret in e for e in errors)


@pytest.mark.parametrize("flags", ["-shell-escape", "-interaction=nonstopmode --shell-escape", "-enable-write18"])
def test_shell_escape_flag_is_a_warning(tmp_path: Path, flags: str) -> None:
    report = lint_version_dir(_safety_version(tmp_path, engine={"type": "xelatex", "flags": flags}))
    assert any("engine.flags: -shell-escape" in w for w in report.warnings)
    assert report.ok


def test_safe_flags_are_quiet(tmp_path: Path) -> None:
    report = lint_version_dir(_safety_version(tmp_path, engine={"flags": "-interaction=nonstopmode -no-shell-escape"}))
    assert not any("shell-escape" in w for w in report.warnings)


@pytest.mark.parametrize("version_dir", _real_version_dirs(), ids=lambda p: "/".join(p.parts[-4:]))
def test_real_packs_pass_safety_rules(version_dir: Path) -> None:
    report = lint_version_dir(version_dir)
    assert not [e for e in report.errors if "символическая ссылка" in e or "секретам" in e]
    assert not [w for w in report.warnings if "shell-escape" in w]
