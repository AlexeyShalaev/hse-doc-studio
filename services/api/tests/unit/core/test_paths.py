from __future__ import annotations

import pytest
from hse_doc_studio.core.paths import Mount, PathMapping

_PROJECTS = Mount(container="/projects", host="D:/study/hse")
_DATA = Mount(container="/data", host="C:/hse-studio-data")


@pytest.fixture
def mapping() -> PathMapping:
    return PathMapping([_PROJECTS, _DATA])


@pytest.mark.unit
def test__to_host__path_inside_a_mount__shows_the_users_own_path(mapping: PathMapping) -> None:
    assert mapping.to_host("/projects/vkr-ru") == "D:/study/hse/vkr-ru"


@pytest.mark.unit
def test__to_container__users_path__maps_back_inside(mapping: PathMapping) -> None:
    assert mapping.to_container("D:/study/hse/vkr-ru") == "/projects/vkr-ru"


@pytest.mark.unit
def test__to_container__windows_backslashes__are_accepted(mapping: PathMapping) -> None:
    assert mapping.to_container("D:\\study\\hse\\vkr-ru") == "/projects/vkr-ru"


@pytest.mark.unit
def test__to_host__path_outside_every_mount__is_untranslatable(mapping: PathMapping) -> None:
    assert mapping.to_host("/usr/share") is None


@pytest.mark.unit
def test__display__untranslatable_path__falls_back_to_the_path_itself(mapping: PathMapping) -> None:
    # Проект мог быть подключён до появления маунта — подписать его контейнерным
    # именем лучше, чем уронить список проектов.
    assert mapping.display("/usr/share") == "/usr/share"


@pytest.mark.unit
def test__accept__container_path__is_taken_as_is(mapping: PathMapping) -> None:
    # Клиент присылает хостовые пути, но контейнерный (из агента, из URL) — тоже валиден.
    assert mapping.accept("/projects/vkr-ru") == "/projects/vkr-ru"


@pytest.mark.unit
def test__accept__host_path__is_translated_inside(mapping: PathMapping) -> None:
    assert mapping.accept("D:/study/hse/vkr-ru") == "/projects/vkr-ru"


@pytest.mark.unit
def test__mapping_order__more_specific_mount_wins() -> None:
    # /projects специфичнее /data и объявлен первым.
    mapping = PathMapping([_PROJECTS, _DATA])

    assert mapping.to_host("/data/projects/vkr") == "C:/hse-studio-data/projects/vkr"


@pytest.mark.unit
def test__empty_mapping__shows_the_path_verbatim() -> None:
    # Нативный запуск: путь и так пользовательский, подменять разделители незачем.
    mapping = PathMapping()

    assert mapping.display("C:\\Users\\me\\hse") == "C:\\Users\\me\\hse"
    assert mapping.accept("C:\\Users\\me\\hse") == "C:\\Users\\me\\hse"
    assert not mapping


@pytest.mark.unit
def test__empty_mapping__to_host__still_normalises_for_docker() -> None:
    # А вот в `docker -v` уходят только прямые слэши — на любой ОС.
    assert PathMapping().to_host("C:\\Users\\me\\hse") == "C:/Users/me/hse"


# ── Корни: у `/` и `C:/` хвостовой слэш — часть имени ───────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("C:\\", "C:/", id="windows_drive_root_backslash"),
        pytest.param("C:/", "C:/", id="windows_drive_root_slash"),
        pytest.param("d:", "d:/", id="bare_drive_letter_lowercase"),
        pytest.param("/", "/", id="posix_root"),
        pytest.param("D:/study/hse/", "D:/study/hse", id="trailing_slash_still_stripped"),
    ],
)
def test__to_host__root_paths__keep_the_separator_that_makes_them_roots(raw: str, expected: str) -> None:
    # Регрессия: rstrip("/") превращал `C:\` в `C:` — а это не корень диска, а
    # «текущий каталог диска C», и `docker run -v C::/work` монтировал не то.
    assert PathMapping().to_host(raw) == expected


@pytest.mark.unit
def test__to_host__mount_rooted_at_a_drive_root__does_not_double_the_separator() -> None:
    mapping = PathMapping([Mount(container="/projects", host="C:\\")])

    assert mapping.to_host("/projects/vkr-ru") == "C:/vkr-ru"


@pytest.mark.unit
def test__to_container__mount_rooted_at_the_filesystem_root__does_not_double_the_separator() -> None:
    mapping = PathMapping([Mount(container="/", host="D:/study")])

    assert mapping.to_container("D:/study/vkr-ru") == "/vkr-ru"
