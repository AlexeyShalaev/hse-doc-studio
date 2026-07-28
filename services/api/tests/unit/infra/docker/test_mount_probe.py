"""Обзор файловой системы хоста: выбор корня для монтирования и разбор ответа.

Главная проверяемая здесь вещь — что проверка пути НЕ ПОРТИТ диск. `docker run -v`
несуществующий каталог не отвергает, а создаёт; смонтировав сам проверяемый путь,
мы бы возвращали «папка найдена, но пуста» на любую опечатку и оставляли за собой
мусор. Поэтому монтируется заведомо существующий корень, а внутри него путь
проверяется обычным `-d`.
"""

from __future__ import annotations

import pytest
from hse_doc_studio.core.setup import MountProbeStatus
from hse_doc_studio.infra.docker.mount_probe import _parse_probe_output, split_anchor


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        pytest.param("C:/Users/Иван/HSE", ("C:/", "Users/Иван/HSE"), id="windows_deep"),
        pytest.param("C:\\Users\\Иван\\HSE", ("C:/", "Users/Иван/HSE"), id="windows_backslashes"),
        pytest.param("C:/", ("C:/", ""), id="windows_drive_root"),
        pytest.param("D:", ("D:/", ""), id="windows_bare_drive"),
        pytest.param("/Users/ivan/HSE", ("/Users", "ivan/HSE"), id="macos"),
        pytest.param("/home/ivan/HSE", ("/home", "ivan/HSE"), id="linux"),
        pytest.param("/home", ("/home", ""), id="first_segment_only"),
        pytest.param("/", ("/", ""), id="posix_root"),
    ],
)
def test__split_anchor__any_platform_path__anchors_at_a_root_that_surely_exists(
    path: str, expected: tuple[str, str]
) -> None:
    assert split_anchor(path) == expected


@pytest.mark.unit
def test__split_anchor__macos_path__never_anchors_at_the_filesystem_root() -> None:
    # Целиком `/` брать нельзя: Docker Desktop на macOS по умолчанию делится
    # только `/Users`, `/Volumes`, `/private` и `/tmp`, и монтирование корня там
    # просто откажет.
    anchor, _relative = split_anchor("/Users/ivan/HSE")

    assert anchor == "/Users"


@pytest.mark.unit
def test__parse_probe_output__path_is_absent__reports_missing_not_empty() -> None:
    # Ровно та разница, ради которой всё и затевалось: «нет такой папки» — не то
    # же самое, что «папка есть и пуста».
    result = _parse_probe_output("__HSE_MISSING__\n")

    assert result.status is MountProbeStatus.ok
    assert result.exists is False
    assert result.entries == ()


@pytest.mark.unit
def test__parse_probe_output__listing__separates_folders_from_files() -> None:
    out = "d\tvkr\nd\tкурсовая\nf\tnotes.md\n__HSE_ENTRIES_END__\n__HSE_WRITABLE__\n"

    result = _parse_probe_output(out)

    assert result.exists is True
    assert [(e.name, e.is_dir) for e in result.entries] == [
        ("vkr", True),
        ("курсовая", True),
        ("notes.md", False),
    ]
    assert [e.name for e in result.directories] == ["vkr", "курсовая"]
    assert result.writable is True


@pytest.mark.unit
def test__parse_probe_output__name_with_spaces__survives_the_tab_split() -> None:
    result = _parse_probe_output("d\tHSE Studio 2026\n__HSE_ENTRIES_END__\n")

    assert [e.name for e in result.entries] == ["HSE Studio 2026"]


@pytest.mark.unit
def test__parse_probe_output__existing_but_empty__is_marked_empty_and_existing() -> None:
    result = _parse_probe_output("__HSE_ENTRIES_END__\n__HSE_WRITABLE__\n")

    assert result.exists is True
    assert result.is_empty is True


@pytest.mark.unit
def test__parse_probe_output__not_writable__says_so() -> None:
    result = _parse_probe_output("d\tvkr\n__HSE_ENTRIES_END__\n")

    assert result.writable is False


@pytest.mark.unit
def test__parse_probe_output__script_died_before_the_marker__reports_no_partial_listing() -> None:
    # Неполный список, выданный за полный, хуже пустого: человек решит, что
    # ошибся папкой, хотя ошиблись мы.
    result = _parse_probe_output("d\tvkr\n")

    assert result.exists is True
    assert result.entries == ()
    assert result.is_empty is True


@pytest.mark.unit
def test__parse_probe_output__folder_with_the_registry_file__is_recognised_as_a_previous_install() -> None:
    # Сценарий переустановки: человек указывает старую папку и не знает, сотрёт
    # мастер его работы или подхватит. Узнавание своих же файлов обязано быть
    # явным — молчание здесь читается как угроза.
    out = "f\tprojects.json\nd\tfonts\n__HSE_ENTRIES_END__\n__HSE_WRITABLE__\n"

    assert _parse_probe_output(out).looks_like_install is True


@pytest.mark.unit
def test__parse_probe_output__folder_with_a_same_named_subdirectory__is_not_an_install() -> None:
    # Маркеры — ФАЙЛЫ реестра и настроек; одноимённая папка ими не является.
    out = "d\tprojects.json\n__HSE_ENTRIES_END__\n"

    assert _parse_probe_output(out).looks_like_install is False


@pytest.mark.unit
def test__parse_probe_output__ordinary_user_folder__is_not_an_install() -> None:
    out = "d\tvkr\nf\tnotes.md\n__HSE_ENTRIES_END__\n__HSE_WRITABLE__\n"

    assert _parse_probe_output(out).looks_like_install is False
