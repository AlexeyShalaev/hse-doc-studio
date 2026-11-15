"""CI для внешнего репозитория паков: `hse-doc-studio pack ci init` (template-studio.md, 4.4, срез T18).

Файл CI запускает `hse-doc-studio pack check` в опубликованном образе Студии той версии, что у автора: lint,
неизменность выпущенных версий (`releases check` и сверка с базовой веткой PR или MR), схемы, классы версий и разбор
лоадером.
TeX и секреты не нужны. Шаблоны лежат в `ci_templates/` и рендерятся тем же песочным окружением, что CI проектов
(`infra/git_sync/ci_renderer.py`).
"""

from __future__ import annotations

import re
import subprocess  # noqa: S404 — git с фиксированным argv, без оболочки
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from jinja2 import FileSystemLoader, StrictUndefined

from hse_doc_studio import __version__ as studio_version
from hse_doc_studio.api.config import settings
from hse_doc_studio.infra.template.jinja_sandbox import CI_YAML_SYNTAX, make_environment
from hse_doc_studio.infra.vcs.git_env import base_git_env, hardened_git_config

_TEMPLATES = Path(__file__).resolve().parent / "ci_templates"
_ENV = make_environment(CI_YAML_SYNTAX, undefined=StrictUndefined, loader=FileSystemLoader(_TEMPLATES))

DEFAULT_BRANCH = "main"
_GIT_TIMEOUT_S = 10

# Значения попадают в YAML и в строку shell без кавычек: только безопасные символы.
_IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._/:@-]*$")
_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


class PackCiProvider(StrEnum):
    github = "github"
    gitlab = "gitlab"


CI_FILES = {
    PackCiProvider.github: ".github/workflows/hse-packs.yml",
    PackCiProvider.gitlab: ".gitlab-ci.yml",
}
_TEMPLATE_NAMES = {PackCiProvider.github: "github.yml.j2", PackCiProvider.gitlab: "gitlab.yml.j2"}


class PackCiError(ValueError):
    """Неверный параметр (`usage`) или файл CI уже есть (`exists`)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PackCiFile:
    provider: PackCiProvider
    path: str  # от корня репозитория, через `/`
    content: str
    image: str
    packs_path: str
    branch: str


def default_image() -> str:
    """Образ этой версии Студии: CI проверяет паки тем же лоадером и линтером, что у автора."""
    return f"{settings.image_base}:{studio_version}"


def _git_line(root: Path, *args: str) -> str | None:
    argv = ["git", *hardened_git_config(), "-c", "safe.directory=*", "-C", str(root), *args]
    try:
        done = subprocess.run(  # noqa: S603
            argv, capture_output=True, env=base_git_env(), timeout=_GIT_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = done.stdout.decode(errors="replace").strip()
    return line if done.returncode == 0 and line else None


def detect_branch(root: Path) -> str:
    """Основная ветка репозитория: `origin/HEAD`, иначе текущая ветка, иначе `main`."""
    remote_head = _git_line(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if remote_head and "/" in remote_head:
        return remote_head.split("/", 1)[1]
    current = _git_line(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    return current or DEFAULT_BRANCH


def normalize_packs_path(raw: str) -> str:
    """Путь паков от корня репозитория: относительный, без `..`, без пробелов и кавычек."""
    value = raw.strip().replace("\\", "/").rstrip("/") or "."
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or value.startswith("-") or not _PATH_RE.match(value):
        raise PackCiError(
            "usage", f"{raw!r}: путь паков нужен относительный, от корня репозитория, без `..` и пробелов"
        )
    return pure.as_posix()


def render_pack_ci(provider: PackCiProvider, *, image: str, packs_path: str, branch: str) -> PackCiFile:
    if not _IMAGE_RE.match(image):
        raise PackCiError("usage", f"{image!r}: образ в виде registry/name:tag, строчными буквами")
    if not _BRANCH_RE.match(branch) or branch.startswith("-"):
        raise PackCiError("usage", f"{branch!r}: имя ветки без пробелов и кавычек")
    packs = normalize_packs_path(packs_path)
    content = _ENV.render_template(
        _TEMPLATE_NAMES[provider],
        {"image": image, "packs_path": packs, "branch": branch, "studio_version": studio_version},
    )
    return PackCiFile(provider, CI_FILES[provider], content, image, packs, branch)


def write_pack_ci(root: Path, ci_file: PackCiFile, *, force: bool = False) -> Path:
    """Файл CI в репозиторий; существующий заменяется только с `force`."""
    target = root / ci_file.path
    if target.exists() and not force:
        hint = ""
        if ci_file.provider is PackCiProvider.gitlab:
            hint = " (в нём могут быть ваши задачи: напечатайте файл с --stdout и перенесите задачу вручную)"
        raise PackCiError("exists", f"{target}: файл уже есть, перезапись только с --force{hint}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(ci_file.content, encoding="utf-8", newline="\n")
    return target
