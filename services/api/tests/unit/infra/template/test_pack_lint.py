"""
Инвариант состава пакета: анкета, которую профиль сдачи кладёт в архив, обязана
быть required_for_pack.

Про состав говорят два независимых места пака — `extra_items` профиля (что
реально уедет) и флаг самой формы (о чём приложение предупреждает). Пока они
могут разъехаться молча, студент отправляет незаполненную анкету и не узнаёт
об этом: расчёт готовности засчитывает только пересечение.
"""

from pathlib import Path

import yaml
from hse_doc_studio.infra.template.pack_lint import lint_version_dir

# .../services/api/tests/unit/infra/template/<this> → корень репозитория.
PACKS_ROOT = Path(__file__).resolve().parents[6] / "packs" / "hse-cs-se" / "templates"


def _write_version(version_dir: Path, manifest: dict) -> None:
    (version_dir / "files").mkdir(parents=True, exist_ok=True)
    (version_dir / "version.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True),
        encoding="utf-8",
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
    for template in ("vkr", "coursework"):
        version_dir = PACKS_ROOT / template / "versions" / "2026.1"

        report = lint_version_dir(version_dir)

        assert report.errors == [], f"{template}: {report.errors}"


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
    for template in ("vkr", "coursework", "pp"):
        version_dir = PACKS_ROOT / template / "versions" / "2026.1"
        manifest = yaml.safe_load((version_dir / "version.yaml").read_text(encoding="utf-8"))

        changes = manifest.get("changes", {})

        assert changes.get("ru"), f"{template}: нет русских заметок о версии"
        assert len(changes["ru"]) == len(changes["en"]), template
        assert lint_version_dir(version_dir).errors == [], template
