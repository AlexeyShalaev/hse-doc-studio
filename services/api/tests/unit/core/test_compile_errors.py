from __future__ import annotations

from hse_doc_studio.core.compile import errors as core_errors
from hse_doc_studio.infra.compile import errors as infra_errors


def test__errors__reexport_same_class_objects() -> None:
    assert infra_errors.CompileSetupError is core_errors.CompileSetupError
    assert infra_errors.DockerUnavailableError is core_errors.DockerUnavailableError
    assert infra_errors.ImageMissingError is core_errors.ImageMissingError
    assert infra_errors.__all__ == ["CompileSetupError", "DockerUnavailableError", "ImageMissingError"]


def test__errors__to_dict_codes_stay() -> None:
    assert core_errors.CompileSetupError("x").to_dict() == {"code": "compile_setup_error", "detail": "x"}
    assert core_errors.DockerUnavailableError("d", reason="cli_missing", socket_gid=5).to_dict() == {
        "code": "docker_unavailable",
        "detail": "d",
        "reason": "cli_missing",
        "socket_gid": 5,
    }
    assert core_errors.ImageMissingError("img:1").to_dict() == {
        "code": "image_missing",
        "detail": "Docker image not installed: img:1",
        "image": "img:1",
    }
    assert issubclass(core_errors.DockerUnavailableError, core_errors.CompileSetupError)
