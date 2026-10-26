from __future__ import annotations


class CompileSetupError(Exception):
    """Base for environmental prerequisites that aren't a compile failure.

    These are raised before the compile task is even scheduled (image
    missing, docker daemon unreachable, ...). They map to a structured
    HTTP 409 by the router so the frontend can branch on `code` and
    offer install / fix actions, instead of treating them as a generic
    build failure.
    """

    code: str = "compile_setup_error"

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "detail": str(self)}


class DockerUnavailableError(CompileSetupError):
    code = "docker_unavailable"

    def __init__(
        self,
        detail: str = "Docker daemon is not reachable",
        *,
        reason: str | None = None,
        socket_gid: int | None = None,
    ) -> None:
        super().__init__(detail)
        # Те же поля, что и у GET /compile/docker-status: причина сборки, упавшей
        # из-за окружения, и причина в настройках — это ОДНА причина, и подсказку
        # с командой починки фронтенд рисует по одному коду в обоих местах.
        self.reason = reason
        self.socket_gid = socket_gid

    def to_dict(self) -> dict[str, object]:
        return {**super().to_dict(), "reason": self.reason, "socket_gid": self.socket_gid}


class ImageMissingError(CompileSetupError):
    code = "image_missing"

    def __init__(self, image: str) -> None:
        super().__init__(f"Docker image not installed: {image}")
        self.image = image

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "detail": str(self), "image": self.image}
