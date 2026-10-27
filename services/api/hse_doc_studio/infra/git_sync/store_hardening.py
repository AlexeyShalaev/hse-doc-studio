"""Проверка и очистка хранилища `.hse-studio/git`, которое приехало вместе с чужой папкой.

config и хуки хранилища путешествуют вместе с проектом и могут запускать код при любой команде
git (fsmonitor, filter-драйверы, алиасы, credential helper, подмена адреса через insteadOf,
include). Белый список ключей закрывает всё сразу, не гоняясь за каждым опасным: что не
перечислено, то подозрительно. Перед сетевыми операциями хранилище должно пройти проверку,
иначе `store_untrusted`; `harden` приводит config к белому списку и убирает хуки.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.git_sync.entities import StoreAudit, StoreFinding, StoreFindingKind
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError, GitUrlError
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.vcs.errors import VcsInvalidRefError, VcsUnavailableError
from hse_doc_studio.core.vcs.refs import validate_ref_name
from hse_doc_studio.infra.vcs.git_env import base_git_env
from hse_doc_studio.infra.vcs.git_vcs_service import store_git_dir

# (раздел, подраздел) -> допустимые переменные. Подраздел "*" — любое имя (ветка), None — подраздела нет.
_ALLOWED: dict[tuple[str, str | None], frozenset[str]] = {
    (
        "core",
        None,
    ): frozenset(
        {
            "repositoryformatversion",
            "filemode",
            "bare",
            "logallrefupdates",
            "worktree",
            "ignorecase",
            "precomposeunicode",
            "symlinks",
        }
    ),
    ("remote", "origin"): frozenset({"url", "fetch"}),
    ("branch", "*"): frozenset({"remote", "merge"}),
    ("gc", None): frozenset({"auto", "autodetach"}),
    ("user", None): frozenset({"name", "email"}),
    ("hse", None): frozenset({"credential", "localbranch", "remotebranch"}),
}
# Ключи с несколькими значениями; у остальных остаётся последнее, как читает git.
_MULTI_VALUED = frozenset({"remote.origin.fetch"})
_FETCH_REFSPEC = re.compile(r"^\+?refs/heads/(?:\*|[^:\s*]+):refs/remotes/origin/(?:\*|[^:\s*]+)$")
# Что git обязан найти в config, если его пересоздают с нуля.
_CORE_DEFAULTS = (("core.repositoryformatversion", "0"), ("core.bare", "false"))
_SAMPLE_SUFFIX = ".sample"


class GitStoreGuard:
    """`allow_http` и `allow_local` повторяют настройки и режим: адрес, который туда не пускают, недоверен."""

    def __init__(self, *, allow_http: bool = False, allow_local: bool = False) -> None:
        self._allow_http = allow_http
        self._allow_local = allow_local

    def audit(self, project_folder: Path) -> StoreAudit:
        findings, _ = self._inspect(project_folder)
        return StoreAudit(findings=tuple(findings))

    def harden(self, project_folder: Path) -> tuple[StoreFinding, ...]:
        findings, entries = self._inspect(project_folder)
        pointer = _store_pointer(project_folder)
        if pointer is not None:
            # Указатель-файл или символьная ссылка ведут к чужому репозиторию: убираем сам указатель,
            # не заходя за него; хранилище создастся заново обычным путём.
            pointer.unlink(missing_ok=True)
            return tuple(findings)
        if any(f.kind is not StoreFindingKind.hook for f in findings):
            self._rewrite_config(project_folder, entries)
        for finding in findings:
            if finding.kind is StoreFindingKind.hook:
                _remove_hook(store_git_dir(project_folder) / "hooks", finding.subject)
        return tuple(findings)

    def ensure_trusted(self, project_folder: Path) -> None:
        if not self.audit(project_folder).trusted:
            raise GitSyncError(
                GitErrorCode.store_untrusted,
                localized_error(
                    "Хранилище версий проекта содержит чужие настройки или хуки. Сбросьте его настройки.",
                    "The project's version store contains foreign settings or hooks. Reset its settings.",
                ),
            )

    def _inspect(self, project_folder: Path) -> tuple[list[StoreFinding], list[tuple[str, str]]]:
        """Находки и записи config, которые можно оставить."""
        git_dir = store_git_dir(project_folder)
        if _store_pointer(project_folder) is not None:
            # git идёт за `gitdir: ...` и за ссылкой и читает config чужого репозитория, а там бывает uploadpack.
            return [StoreFinding(StoreFindingKind.config_unreadable, "git")], []
        if not (git_dir / "HEAD").exists():
            return [], []
        findings = _hook_findings(git_dir / "hooks")
        listed = _read_config(git_dir / "config")
        if listed is None:
            return [StoreFinding(StoreFindingKind.config_unreadable, "config"), *findings], []
        keep: list[tuple[str, str]] = []
        for key, value in listed:
            problem = _config_problem(key, value, allow_http=self._allow_http, allow_local=self._allow_local)
            if problem is None:
                keep.append((key, value))
            else:
                findings.append(StoreFinding(*problem))
        return findings, keep

    def _rewrite_config(self, project_folder: Path, entries: list[tuple[str, str]]) -> None:
        config = store_git_dir(project_folder) / "config"
        present = {key for key, _ in entries}
        defaults = [(key, value) for key, value in _CORE_DEFAULTS if key not in present]
        # Имя угадать нельзя: заготовленная в чужом хранилище ссылка с постоянным именем увела бы запись наружу.
        handle, name = tempfile.mkstemp(prefix="config.hse-new-", dir=config.parent)
        os.close(handle)
        fresh = Path(name)
        try:
            for key, value in [*defaults, *_dedupe(entries)]:
                _git_config(fresh, ["--add", key, value])
            os.replace(fresh, config)
        finally:
            fresh.unlink(missing_ok=True)


def _store_pointer(project_folder: Path) -> Path | None:
    """Путь, который подменяет хранилище ссылкой или файлом-указателем, а не настоящей папкой."""
    git_dir = store_git_dir(project_folder)
    for candidate in (git_dir.parent, git_dir):
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_dir()):
            return candidate
    return None


def _dedupe(entries: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    last: dict[str, str] = {}
    kept: list[tuple[str, str]] = []
    for key, value in entries:
        if key in _MULTI_VALUED:
            kept.append((key, value))
        else:
            last[key] = value
    return [*last.items(), *kept]


def _split_key(key: str) -> tuple[str, str | None, str]:
    section, _, rest = key.partition(".")
    subsection, dot, variable = rest.rpartition(".")
    return (section, subsection, variable) if dot else (section, None, rest)


def _safe_label(section: str, subsection: str | None, variable: str) -> str:
    return f"{section}.{'*.' if subsection is not None else ''}{variable}"


def _config_problem(
    key: str, value: str, *, allow_http: bool, allow_local: bool
) -> tuple[StoreFindingKind, str] | None:
    section, subsection, variable = _split_key(key)
    allowed = _ALLOWED.get((section, subsection)) or (_ALLOWED.get((section, "*")) if subsection is not None else None)
    if allowed is None or variable not in allowed:
        return StoreFindingKind.config_key, _safe_label(section, subsection, variable)
    if not _value_ok(key, value, allow_http=allow_http, allow_local=allow_local):
        return StoreFindingKind.config_value, key
    return None


def _value_ok(key: str, value: str, *, allow_http: bool, allow_local: bool) -> bool:
    if key == "remote.origin.url":
        return _url_ok(value, allow_http=allow_http, allow_local=allow_local)
    if key == "remote.origin.fetch":
        return bool(_FETCH_REFSPEC.match(value))
    if key == "hse.credential":
        return _uuid_ok(value)
    if key in ("hse.localbranch", "hse.remotebranch"):
        return _branch_ok(value)
    return True


def _url_ok(value: str, *, allow_http: bool, allow_local: bool) -> bool:
    try:
        parsed = parse_remote_url(value, allow_http=allow_http, allow_local=allow_local)
    except GitUrlError:
        return False
    return not parsed.token_stripped


def _uuid_ok(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _branch_ok(value: str) -> bool:
    try:
        validate_ref_name(value)
    except VcsInvalidRefError:
        return False
    return True


def _hook_findings(hooks: Path) -> list[StoreFinding]:
    if hooks.is_symlink() or (hooks.exists() and not hooks.is_dir()):
        return [StoreFinding(StoreFindingKind.hook, "hooks")]
    if not hooks.is_dir():
        return []
    return [
        StoreFinding(StoreFindingKind.hook, entry.name)
        for entry in sorted(hooks.iterdir())
        if not entry.name.endswith(_SAMPLE_SUFFIX)
    ]


def _remove_hook(hooks: Path, name: str) -> None:
    target = hooks if name == "hooks" else hooks / name
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target, ignore_errors=True)
    else:
        target.unlink(missing_ok=True)
    hooks.mkdir(exist_ok=True)


def _read_config(config: Path) -> list[tuple[str, str]] | None:
    proc = _git_config(config, ["--list", "-z"], check=False)
    if proc.returncode != 0:
        return None
    entries: list[tuple[str, str]] = []
    for record in proc.stdout.split("\0"):
        key, _, value = record.partition("\n")
        if key:
            entries.append((key, value))
    return entries


def _git_config(config: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603
            ["git", "config", "--file", str(config), *args],  # noqa: S607
            capture_output=True,
            text=True,
            check=check,
            env=base_git_env(),
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise VcsUnavailableError(str(exc)) from exc
