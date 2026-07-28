from __future__ import annotations

import pytest
from hse_doc_studio.core.compile.docker_diagnosis import DockerUnavailableReason
from hse_doc_studio.core.paths import Mount
from hse_doc_studio.core.setup import (
    SetupCheck,
    SetupCheckId,
    SetupSeverity,
    assess_docker,
    assess_project_storage,
    build_report,
)


def _check(severity: SetupSeverity, code: str, check_id: SetupCheckId = SetupCheckId.project_storage) -> SetupCheck:
    return SetupCheck(id=check_id, severity=severity, code=code)


# ── assess_project_storage ──────────────────────────────────────────────────


@pytest.mark.unit
def test__assess_project_storage__native_run__ok_without_host_path() -> None:
    check = assess_project_storage(in_container=False, mounts=(), host_data_dir=None)

    assert check.id is SetupCheckId.project_storage
    assert check.severity is SetupSeverity.ok
    assert check.code == "native"


@pytest.mark.unit
def test__assess_project_storage__native_run__ignores_a_relative_data_dir() -> None:
    # Вне контейнера относительный путь резолвит сам процесс: файловая система
    # одна, и ругаться тут не на что.
    check = assess_project_storage(in_container=False, mounts=(), host_data_dir="./data")

    assert check.severity is SetupSeverity.ok
    assert check.code == "native"


@pytest.mark.unit
def test__assess_project_storage__container_with_mount__ok_and_shows_the_host_path() -> None:
    mounts = (Mount(container="/data", host="D:/study/hse"),)

    check = assess_project_storage(in_container=True, mounts=mounts, host_data_dir="D:/study/hse")

    assert check.severity is SetupSeverity.ok
    assert check.code == "ok"
    assert check.context == {"host_path": "D:/study/hse"}


@pytest.mark.unit
def test__assess_project_storage__container_with_several_mounts__reports_the_first_one() -> None:
    mounts = (
        Mount(container="/data", host="D:/study/hse"),
        Mount(container="/projects", host="E:/archive"),
    )

    check = assess_project_storage(in_container=True, mounts=mounts, host_data_dir=None)

    assert check.context == {"host_path": "D:/study/hse"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "host_data_dir",
    [
        pytest.param("./data", id="the_broken_default_from_the_shipped_env_example"),
        pytest.param("data", id="bare_name_docker_reads_as_a_volume_name"),
        pytest.param("../hse-data", id="path_relative_to_the_compose_file"),
    ],
)
def test__assess_project_storage__container_with_relative_host_dir__blocks_with_relative_host_path(
    host_data_dir: str,
) -> None:
    # Главный случай продукта: бинд ЗАДАН, но относительным путём. Демон принял
    # его за имя тома, соответствия «контейнер ↔ хост» нет — маунтов ноль, хотя
    # пользователь уверен, что всё настроил. Отдельный код нужен, чтобы мастер
    # показал ему ровно ту строку, которую он написал.
    check = assess_project_storage(in_container=True, mounts=(), host_data_dir=host_data_dir)

    assert check.severity is SetupSeverity.blocker
    assert check.code == "relative_host_path"
    assert check.context == {"host_path": host_data_dir}


@pytest.mark.unit
def test__assess_project_storage__container_without_any_host_dir__blocks_with_no_host_path() -> None:
    check = assess_project_storage(in_container=True, mounts=(), host_data_dir=None)

    assert check.severity is SetupSeverity.blocker
    assert check.code == "no_host_path"
    assert check.context == {}


@pytest.mark.unit
def test__assess_project_storage__container_with_empty_host_dir__blocks_with_no_host_path() -> None:
    # Пустая переменная окружения неотличима от незаданной: показывать
    # пользователю его «настройку» нечего, ведёт мастер по ветке «бинда нет».
    check = assess_project_storage(in_container=True, mounts=(), host_data_dir="")

    assert check.code == "no_host_path"
    assert check.context == {}


# ── assess_docker ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test__assess_docker__daemon_alive__ok() -> None:
    check = assess_docker(alive=True)

    assert check.id is SetupCheckId.docker
    assert check.severity is SetupSeverity.ok
    assert check.code == "ok"
    assert check.is_blocker is False


@pytest.mark.unit
def test__assess_docker__daemon_alive_with_stale_reason__stays_ok() -> None:
    check = assess_docker(alive=True, reason_code=str(DockerUnavailableReason.SOCKET_PERMISSION))

    assert check.severity is SetupSeverity.ok
    assert check.code == "ok"


@pytest.mark.unit
@pytest.mark.parametrize(
    "reason",
    [
        pytest.param(DockerUnavailableReason.SOCKET_PERMISSION, id="socket_permission"),
        pytest.param(DockerUnavailableReason.CLI_MISSING, id="cli_missing"),
        pytest.param(DockerUnavailableReason.TIMEOUT, id="timeout"),
    ],
)
def test__assess_docker__daemon_down__warns_and_passes_the_reason_through(
    reason: DockerUnavailableReason,
) -> None:
    # Код причины доходит до интерфейса неизменным: по нему подбирается и текст,
    # и команда-подсказка, поэтому подменять его на общий здесь нельзя.
    check = assess_docker(alive=False, reason_code=str(reason))

    assert check.severity is SetupSeverity.warning
    assert check.code == reason.value


@pytest.mark.unit
def test__assess_docker__daemon_down__is_not_a_blocker() -> None:
    # Мёртвый демон — состояние машины, а не установки: его запускают за минуту,
    # ничего не пересоздавая, а тексты и готовые PDF доступны и без него. Поэтому
    # blocker тут был бы запиранием всего интерфейса за мастером настройки.
    check = assess_docker(alive=False, reason_code=str(DockerUnavailableReason.SOCKET_PERMISSION))

    assert check.is_blocker is False


@pytest.mark.unit
def test__assess_docker__daemon_down_without_reason__falls_back_to_daemon_unreachable() -> None:
    check = assess_docker(alive=False)

    assert check.severity is SetupSeverity.warning
    assert check.code == DockerUnavailableReason.DAEMON_UNREACHABLE.value


# ── SetupReport ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test__setup_report__no_checks_at_all__is_ready() -> None:
    report = build_report([])

    assert report.checks == ()
    assert report.blockers == ()
    assert report.is_ready is True


@pytest.mark.unit
def test__setup_report__only_ok_checks__is_ready() -> None:
    report = build_report(
        [
            assess_docker(alive=True),
            assess_project_storage(in_container=False, mounts=(), host_data_dir=None),
        ]
    )

    assert report.blockers == ()
    assert report.is_ready is True


@pytest.mark.unit
def test__setup_report__warning_only__is_still_ready() -> None:
    # Предупреждение — про отключённую возможность, а не про сломанный продукт:
    # мастер первоначальной настройки из-за него открываться не должен.
    report = build_report([_check(SetupSeverity.warning, "something_optional_is_off")])

    assert report.blockers == ()
    assert report.is_ready is True


@pytest.mark.unit
def test__setup_report__has_a_blocker__is_not_ready() -> None:
    report = build_report(
        [
            assess_docker(alive=True),
            assess_project_storage(in_container=True, mounts=(), host_data_dir="./data"),
        ]
    )

    assert report.is_ready is False
    assert [c.code for c in report.blockers] == ["relative_host_path"]


@pytest.mark.unit
def test__setup_report__docker_is_down_but_storage_is_fine__is_still_ready() -> None:
    # Настройка при этом ЗАКОНЧЕНА: мастер открывать не за чем, про докер
    # рассказывает отдельный баннер.
    report = build_report(
        [
            assess_docker(alive=False, reason_code=str(DockerUnavailableReason.SOCKET_PERMISSION)),
            assess_project_storage(
                in_container=True, mounts=(Mount(container="/data", host="D:/hse"),), host_data_dir="D:/hse"
            ),
        ]
    )

    assert report.blockers == ()
    assert report.is_ready is True


@pytest.mark.unit
def test__setup_report__mixed_checks__blockers_keep_the_declared_order() -> None:
    report = build_report(
        [
            _check(SetupSeverity.ok, "ok", SetupCheckId.docker),
            _check(SetupSeverity.blocker, "relative_host_path"),
            _check(SetupSeverity.warning, "something_optional_is_off"),
            _check(SetupSeverity.blocker, "no_host_path"),
        ]
    )

    assert [c.code for c in report.blockers] == ["relative_host_path", "no_host_path"]
