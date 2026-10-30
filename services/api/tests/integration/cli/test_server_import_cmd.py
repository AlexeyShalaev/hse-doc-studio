"""`hse-doc-studio server import|import-project`: разбор аргументов, отчёты и коды выхода без базы."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio import cli, cli_import
from hse_doc_studio.core.projects.importer import ImportReport, ImportWarning, ImportWarningCode
from hse_doc_studio.use_cases.server_import.import_user_data import ImportNote, ImportNoteCode, ImportUserDataReport


def test__parser__import_with_dry_run_and_instance_flag() -> None:
    args = cli._parser().parse_args(
        ["server", "import", "--data-dir", "/d", "--user", "a@b.test", "--dry-run", "--include-instance"]
    )

    assert (args.server_command, args.data_dir, args.user, args.dry_run, args.include_instance) == (
        "import",
        Path("/d"),
        "a@b.test",
        True,
        True,
    )


def test__parser__import_project_needs_user() -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(["server", "import-project", "/p"])


def test__main__missing_data_dir__usage_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    async def fail(*_: object, **__: object) -> object:
        raise cli_import.ImportCliError("каталог данных не найден")

    monkeypatch.setattr(cli_import, "import_user_data", fail)

    code = cli.main(["server", "import", "--data-dir", str(tmp_path / "x"), "--user", "a@b.test"])

    assert code == cli._EXIT_USAGE
    assert "каталог данных не найден" in capsys.readouterr().err


def test__data_report__dry_run_wording_and_notes() -> None:
    report = ImportUserDataReport(
        dry_run=True,
        settings_created=2,
        providers_created=1,
        notes=[ImportNote(ImportNoteCode.not_transferred, "git_credentials")],
    )
    lines: list[str] = []

    cli_import.format_data_report(report, lines.append)

    assert lines[0].startswith("перенос данных: пробный запуск")
    assert "будет создано 2" in lines[1]
    assert "git_credentials" in lines[-1]
    assert "заново" in lines[-1]


def test__project_report__shows_regenerated_id_and_warnings() -> None:
    report = ImportReport(
        project_id=uuid4(),
        name="Курсовая",
        id_regenerated=True,
        files=4,
        bytes=10,
        chats=2,
        warnings=[ImportWarning(ImportWarningCode.remote_needs_access)],
    )
    lines: list[str] = []

    cli_import.format_project_report(report, lines.append)

    text = "\n".join(lines)
    assert "Курсовая" in text
    assert "выдан новый" in text
    assert "remote_needs_access" in text
