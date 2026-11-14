"""Выпущенные версии по базовой ветке git (template-studio.md, 4.5).

Выпущенной версия становится после слияния: список берётся из `releases.yaml` базовой ветки, а не рабочего
дерева. `pack check --base origin/master` сверяет с ним реестр ветки (запись выпущенной версии нельзя ни убрать, ни
пересчитать), `pack freeze --replace --base ...` не заменяет запись, которая уже есть в базе.

git запускается только на чтение (`rev-parse`, `cat-file`, `show`) с окружением и конфигурацией, закалёнными как у
стора проекта: чужой репозиторий паков не исполнит хуков и fsmonitor.
"""

from __future__ import annotations

import subprocess  # noqa: S404 — git с фиксированным argv, без оболочки
from functools import cache
from pathlib import Path

import yaml

from hse_doc_studio.infra.template.releases import RELEASES_FILE, ReleaseEntry, parse_releases
from hse_doc_studio.infra.vcs.git_env import base_git_env, hardened_git_config

_TIMEOUT_S = 30


class BaseRefError(ValueError):
    """Ссылка не разобрана, каталог не в репозитории git или git недоступен."""


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    argv = ["git", *hardened_git_config(), "-c", "safe.directory=*", "-C", str(cwd), *args]
    try:
        return subprocess.run(argv, capture_output=True, env=base_git_env(), timeout=_TIMEOUT_S, check=False)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BaseRefError(f"git недоступен: {exc}") from exc


class BaseReleases:
    """Реестры выпусков шаблонов на коммите `ref`; результат кэшируется по каталогу шаблона."""

    def __init__(self, ref: str) -> None:
        self.ref = ref
        self._commits: dict[Path, str] = {}

    def _commit(self, top: Path) -> str:
        if top not in self._commits:
            done = _git(top, "rev-parse", "--verify", "--quiet", f"{self.ref}^{{commit}}")
            if done.returncode != 0:
                raise BaseRefError(f"{self.ref}: не коммит в {top} (сделайте git fetch)")
            self._commits[top] = done.stdout.decode().strip()
        return self._commits[top]

    def releases(self, template_dir: Path) -> dict[str, ReleaseEntry]:
        """Реестр выпусков шаблона в базе; пустой, если шаблона или `releases.yaml` там нет."""
        top = _toplevel(template_dir.resolve())
        commit = self._commit(top)
        rel = (template_dir.resolve() / RELEASES_FILE).relative_to(top).as_posix()
        if _git(top, "cat-file", "-e", f"{commit}:{rel}").returncode != 0:
            return {}
        done = _git(top, "show", f"{commit}:{rel}")
        if done.returncode != 0:
            raise BaseRefError(f"{self.ref}:{rel}: {done.stderr.decode(errors='replace').strip()}")
        try:
            return parse_releases(done.stdout.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise BaseRefError(f"{self.ref}:{rel}: не разобран ({exc})") from exc


@cache
def _toplevel(path: Path) -> Path:
    done = _git(path, "rev-parse", "--show-toplevel")
    if done.returncode != 0:
        raise BaseRefError(f"{path}: не в репозитории git, --base не применить")
    return Path(done.stdout.decode().strip()).resolve()
