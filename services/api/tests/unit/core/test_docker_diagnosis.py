from __future__ import annotations

import pytest
from hse_doc_studio.core.compile.docker_diagnosis import (
    DockerUnavailableReason,
    MountFailureReason,
    classify_docker_error,
    classify_mount_error,
)

_REAL_PERMISSION_STDERR = (
    "permission denied while trying to connect to the Docker daemon socket at "
    'unix:///var/run/docker.sock: Get "http://%2Fvar%2Frun%2Fdocker.sock/v1.47/version": '
    "dial unix /var/run/docker.sock: connect: permission denied"
)
_REAL_DAEMON_DOWN_STDERR = (
    "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?"
)


@pytest.mark.unit
def test__classify_docker_error__socket_permission_denied__is_a_permission_problem() -> None:
    assert classify_docker_error(_REAL_PERMISSION_STDERR) is DockerUnavailableReason.SOCKET_PERMISSION


@pytest.mark.unit
def test__classify_docker_error__daemon_not_running__is_not_a_permission_problem() -> None:
    assert classify_docker_error(_REAL_DAEMON_DOWN_STDERR) is DockerUnavailableReason.DAEMON_UNREACHABLE


@pytest.mark.unit
def test__classify_docker_error__permission_denied_without_socket_mention__still_permission() -> None:
    assert classify_docker_error("Got permission denied") is DockerUnavailableReason.SOCKET_PERMISSION


@pytest.mark.unit
def test__classify_docker_error__empty_stderr__falls_back_to_daemon_unreachable() -> None:
    assert classify_docker_error("") is DockerUnavailableReason.DAEMON_UNREACHABLE


_REAL_NOT_SHARED_STDERR = (
    "docker: Error response from daemon: Mounts denied: \n"
    "The path /Users/alex/study/vkr is not shared from the host and is not known to Docker.\n"
    "You can configure shared paths from Docker -> Preferences... -> Resources -> File Sharing."
)
_REAL_MOUNT_SOURCE_STDERR = (
    "docker: Error response from daemon: error while creating mount source path "
    "'/host_mnt/d/study/vkr': mkdir /host_mnt/d: file exists"
)
_REAL_MOUNT_PERMISSION_STDERR = (
    "docker: Error response from daemon: error while creating mount source path "
    "'/host_mnt/c/Users/alex/vkr': chown /host_mnt/c/Users/alex/vkr: permission denied"
)


@pytest.mark.unit
def test__classify_mount_error__path_outside_docker_desktop_file_sharing__is_not_shared() -> None:
    # Тот же текст содержит и «mounts denied», но чинится он не в compose-файле, а
    # в списке File Sharing у Docker Desktop — конкретная причина обязана победить
    # общую обёртку, иначе пользователю покажут бесполезное «демон отказал».
    assert classify_mount_error(_REAL_NOT_SHARED_STDERR) is MountFailureReason.NOT_SHARED


@pytest.mark.unit
def test__classify_mount_error__daemon_could_not_create_the_source_path__is_mount_rejected() -> None:
    assert classify_mount_error(_REAL_MOUNT_SOURCE_STDERR) is MountFailureReason.MOUNT_REJECTED


@pytest.mark.unit
def test__classify_mount_error__daemon_cannot_read_the_directory__is_permission() -> None:
    assert classify_mount_error(_REAL_MOUNT_PERMISSION_STDERR) is MountFailureReason.PERMISSION


@pytest.mark.unit
def test__classify_mount_error__bare_permission_denied__is_permission() -> None:
    assert classify_mount_error("permission denied") is MountFailureReason.PERMISSION


@pytest.mark.unit
@pytest.mark.parametrize(
    "stderr",
    [
        pytest.param("", id="empty_stderr"),
        pytest.param("docker: Error response from daemon: something we have never seen", id="unknown_wording"),
    ],
)
def test__classify_mount_error__unrecognised_stderr__falls_back_to_mount_rejected(stderr: str) -> None:
    # Неизвестную причину показываем сырым текстом демона: молча ронять её нельзя,
    # но и выдавать за нехватку прав — тоже.
    assert classify_mount_error(stderr) is MountFailureReason.MOUNT_REJECTED
