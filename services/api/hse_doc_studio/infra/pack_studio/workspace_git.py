"""Git рабочего пространства Студии шаблонов: частичный закалённый клон репозитория паков (порт IPackWorkspaceGit).

Своего сетевого git здесь нет: каждая команда идёт через `IGitRemoteRunner` синхронизации проектов (окружение по
белому списку, защитные `-c`, токен только в окружении процесса через `http.<адрес>.extraheader`, egress, доверие
к хостам, очистка вывода от секретов). Отсюда только раскладка и аргументы:

- хранилище `git/` лежит вне рабочего дерева `tree/`, поэтому файлы `.git` в дереве не появляются, а пути API до
  хранилища не дотягиваются;
- выборка без блобов (`--filter=blob:none`, D6) и разреженное дерево только с папкой паков: блобы приходят лениво,
  ровно для неё. История коммитов и деревьев целая: ветке и слиянию с базой (T6) нужна общая история;
- `core.symlinks=false`, `core.protectNTFS`, `core.protectHFS`, без подмодулей и без фоновой сборки мусора; хуки,
  fsmonitor и помощники учётных данных выключает сам запускатель на каждой команде;
- адрес в конфиге без секретов: он нужен ленивой подгрузке блобов (promisor remote `origin`).

Блоб, которого нет в хранилище, git подгружает сам, но только в командах с сетью (`runner.run`: доступ пространства,
те же ограничения сети и времени, что у выборки). Локальные команды (`run_local`) идут с `GIT_ALLOW_PROTOCOL=none`
и подгрузить ничего не могут. Поэтому:

- после каждой команды с сетью (клон, выборка базы, ветка, слияние, сброс, восстановление) блобы, которые могут
  понадобиться локальному git, догружаются явно (`_hydrate`): всё под папкой паков в HEAD и в базе плюс
  `.gitignore`, `.gitattributes` и `.gitmodules` на пути к ней. Эти файлы корня лежат вне разреженного дерева
  (skip-worktree), и `status`, `add -A`, `ls-files --others`, `clean` читают правила игнорирования из их блоба в
  индексе: без блоба свежий клон падал на первом же `status`;
- локальная команда, которая всё же упёрлась в недостающий объект («could not fetch <oid> from promisor remote»),
  догружает его тем же путём и повторяется. Так чинятся и пространства, созданные до этой правки;
- состояние ветки (`status`) сравнивает с базой только идентификаторы объектов (`diff-index --raw`) и хэши файлов
  рабочего дерева, а не текст.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import structlog
import yaml

from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import GitResult, RemoteTarget
from hse_doc_studio.core.git_sync.error_classifier import DETAIL_TAIL_CHARS, GitOp, scrub
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.protocols import IGitRemoteRunner
from hse_doc_studio.core.git_sync.url import RemoteKind
from hse_doc_studio.core.pack_studio.entities import ReleasedVersions
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.git_flow import (
    ChangeStatus,
    FileChange,
    MergeOutcome,
    PushOutcome,
    WorkGitStatus,
)
from hse_doc_studio.core.pack_studio.paths import is_registry_path, template_key
from hse_doc_studio.core.pack_studio.protocols import GitRevisionName, WorkspaceDirs, WorkspaceLimits
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.core.vcs.errors import VcsInvalidRefError
from hse_doc_studio.core.vcs.refs import validate_ref_name
from hse_doc_studio.infra.template.releases import parse_releases

logger = structlog.get_logger()

_LOCAL_TIMEOUT_S = 60.0
_REMOTE = "origin"
# Реестр выпусков крупнее этого не читается: это не реестр, а попытка занять память api.
_REGISTRY_MAX_BYTES = 1_048_576
_KIB = 1024
# Файлов в одном вызове `hash-object`: длина командной строки ограничена.
_HASH_BATCH = 200
# Глобальные опции git со значением: подкоманда в журнале ищется после них.
_OPTIONS_WITH_VALUE = frozenset({"-c", "-C", "--work-tree", "--git-dir"})
# Файлы, которые git читает сам (игнорирование, атрибуты, подмодули), в каждом каталоге на пути к папке паков.
_CONTROL_FILES = (".gitignore", ".gitattributes", ".gitmodules")
# Объектов в одной выборке по идентификаторам: длина командной строки ограничена.
_FETCH_BATCH = 200
# Сколько раз локальная команда может догрузить недостающий объект и повториться.
_LAZY_ROUNDS = 3
# Обычные файлы в дереве git: без права исполнения и с ним (ссылки 120000 и подмодули 160000 не читаются).
_REGULAR_MODES = frozenset({b"100644", b"100755"})
_PATHSPEC_GLOB = re.compile(r"[*?\[\]]")
_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
# Блобов, которые читаются из хранилища одновременно.
_READ_PARALLEL = 8
_PROMISOR_MISS = re.compile(r"could not fetch ([0-9a-f]{40}(?:[0-9a-f]{24})?) from promisor remote")
# Подсказка к workspace_git_failed: без адресов и путей сервера, не длиннее этого.
_HINT_LINES = 2
_HINT_MAX = 300
_HINT_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
_HINT_SCP = re.compile(r"\b[\w.-]+@[\w.-]+:\S+")
_HINT_PATH = re.compile(r"(?<![\w.~<>/-])(?:/|[A-Za-z]:[\\/])[^\s'\"`]*")


def remote_ref(branch: str) -> str:
    return f"refs/remotes/{_REMOTE}/{branch}"


def _author_config(author: VcsAuthor) -> list[str]:
    """Подпись коммита из профиля человека (автор и коммиттер); подпись GPG и хуки выключены."""
    return ["-c", f"user.name={author.name}", "-c", f"user.email={author.email}", "-c", "commit.gpgsign=false"]


def _scope(packs_path: str) -> list[str]:
    return ["--", "." if packs_path == "." else packs_path]


def _rel(name: str, packs_path: str) -> str | None:
    if packs_path == ".":
        return name
    prefix = f"{packs_path}/"
    return name[len(prefix) :] if name.startswith(prefix) else None


def _status_of(code: str) -> ChangeStatus:
    if "D" in code:
        return ChangeStatus.deleted
    if "A" in code or code == "??":
        return ChangeStatus.added
    return ChangeStatus.modified


def _parse_porcelain(raw: bytes, packs_path: str) -> list[FileChange]:
    """`status --porcelain=v1 -z --no-renames`: `XY path\0`."""
    changes: list[FileChange] = []
    for entry in raw.decode("utf-8", errors="replace").split("\0"):
        if len(entry) < 4:  # noqa: PLR2004
            continue
        rel = _rel(entry[3:], packs_path)
        if rel:
            changes.append(FileChange(rel, _status_of(entry[:2])))
    return changes


@dataclass(frozen=True)
class _RawChange:
    """Строка `diff-index --raw`: идентификатор объекта в базе и в рабочем дереве (нули, если файл правлен)."""

    path: str
    status: str
    base_oid: str
    work_oid: str

    @property
    def work_unknown(self) -> bool:
        """Файл на диске отличается от индекса: git не хэширует его в diff-index, а пишет нули."""
        return self.status in {"M", "T"} and not self.work_oid.strip("0")


def _parse_raw(raw: bytes) -> list[_RawChange]:
    """`diff-index --raw -z --no-renames`: `:old_mode new_mode old_oid new_oid S\0path\0`."""
    parts = iter(raw.decode("utf-8", errors="replace").split("\0"))
    changes: list[_RawChange] = []
    for meta in parts:
        if not meta.startswith(":"):
            continue
        path = next(parts, "")
        fields = meta[1:].split()
        if len(fields) < 5 or not path:  # noqa: PLR2004 — пять полей формата raw
            continue
        changes.append(_RawChange(path=path, status=fields[4][:1], base_oid=fields[2], work_oid=fields[3]))
    return changes


def _subcommand(args: Sequence[str]) -> str:
    """Имя подкоманды для журнала: сами аргументы (пути, почта автора) в журнал не идут."""
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in _OPTIONS_WITH_VALUE:
            skip = True
        elif not arg.startswith("-"):
            return arg
    return ""


def git_hint(command: str, stderr: str) -> str:
    """Безопасная подсказка к сбою локального git для ответа: подкоманда и первые строки ошибки.

    Вывод сначала проходит общую очистку от секретов, потом из него уходят адреса (в том числе вида
    `git@host:repo`) и абсолютные пути сервера. Пути внутри репозитория и идентификаторы объектов остаются: по ним
    видно, какой файл git не смог прочитать.
    """
    lines = [line.strip() for line in scrub(stderr).splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith(("fatal:", "error:"))] or lines
    text = " | ".join(errors[:_HINT_LINES])
    text = _HINT_URL.sub("<url>", text)
    text = _HINT_SCP.sub("<url>", text)
    text = _HINT_PATH.sub("<path>", text)
    text = "".join(ch for ch in text if ch.isprintable())
    if len(text) > _HINT_MAX:
        text = text[: _HINT_MAX - 1] + "…"
    head = f"git {command}" if command else "git"
    return f"{head}: {text}" if text else head


def _promised_object(stderr: str) -> str | None:
    """Идентификатор объекта, за которым локальный git пытался сходить в promisor remote."""
    found = _PROMISOR_MISS.search(stderr)
    return found.group(1) if found else None


def _control_paths(packs_path: str) -> list[str]:
    """`.gitignore` и соседи в корне и в каждом каталоге над папкой паков (внутри неё они и так в выборке)."""
    folders = [""]
    if packs_path != ".":
        parts = packs_path.split("/")
        folders += ["/".join(parts[:i]) for i in range(1, len(parts))]
    return [f"{folder}/{name}" if folder else name for folder in folders for name in _CONTROL_FILES]


def _blob_oids(raw: bytes) -> set[str]:
    """`ls-tree -r -z`: `mode type oid\tpath\0`; только блобы (ссылки подмодулей это коммиты)."""
    oids: set[str] = set()
    for entry in raw.decode("utf-8", errors="replace").split("\0"):
        meta, _, _path = entry.partition("\t")
        fields = meta.split()
        if len(fields) == 3 and fields[1] == "blob":  # noqa: PLR2004 — три поля формата ls-tree
            oids.add(fields[2])
    return oids


def _listed_blobs(raw: bytes) -> list[tuple[str, str, int]]:
    """`ls-tree -r -z --long`: `mode type oid size\tpath\0`; обычные файлы (не ссылки и не подмодули)."""
    found: list[tuple[str, str, int]] = []
    for entry in raw.split(b"\0"):
        head, _, path = entry.partition(b"\t")
        fields = head.split()
        if len(fields) != 4 or fields[0] not in _REGULAR_MODES or fields[1] != b"blob":  # noqa: PLR2004 — поля ls-tree
            continue
        found.append((path.decode("utf-8", errors="replace"), fields[2].decode("ascii"), int(fields[3])))
    return found


def _branch(name: str) -> str:
    try:
        return validate_ref_name(name)
    except VcsInvalidRefError:
        raise git_error(GitErrorCode.branch_missing) from None


def _config_url(target: RemoteTarget) -> str:
    """Адрес для ленивой подгрузки блобов. https без `.git` получает суффикс, как в запускателе: с токеном редиректы
    выключены, а GitLab перенаправляет `<repo>/info/refs` на `<repo>.git/info/refs`."""
    url = target.url.display_url
    if target.url.kind in (RemoteKind.https, RemoteKind.http) and not url.endswith(".git"):
        return f"{url}.git"
    return url


def _store_config(target: RemoteTarget, packs_path: str) -> list[tuple[str, str]]:
    entries = [
        ("core.repositoryformatversion", "1"),
        ("core.symlinks", "false"),
        ("core.protectNTFS", "true"),
        ("core.protectHFS", "true"),
        ("core.fsmonitor", "false"),
        ("core.quotepath", "false"),
        ("gc.auto", "0"),
        ("maintenance.auto", "false"),
        ("fetch.recurseSubmodules", "false"),
        ("submodule.recurse", "false"),
        ("remote.origin.url", _config_url(target)),
        ("remote.origin.promisor", "true"),
        ("remote.origin.partialclonefilter", "blob:none"),
        ("extensions.partialClone", _REMOTE),
    ]
    if packs_path != ".":
        entries += [("core.sparseCheckout", "true"), ("core.sparseCheckoutCone", "false")]
    return entries


class PackWorkspaceGit:
    def __init__(self, runner: IGitRemoteRunner, config: GitConfig) -> None:
        self._runner = runner
        self._config = config

    async def clone(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, branch: str, packs_path: str, limits: WorkspaceLimits
    ) -> str:
        branch = _branch(branch)
        await asyncio.to_thread(self._fresh_dirs, dirs)
        await self._run_local(None, ["init", "--bare", "--quiet", f"--initial-branch={branch}", str(dirs.git)])
        for key, value in _store_config(target, packs_path):
            await self._local(dirs, ["config", key, value])
        if packs_path != ".":
            # Шаблон разреженной выборки без конуса: только папка паков, без файлов корня репозитория.
            info = dirs.git / "info"
            info.mkdir(exist_ok=True)
            (info / "sparse-checkout").write_text(f"/{packs_path}/\n", encoding="utf-8")
        await self._fetch(dirs, target, branch, timeout_s=self._config.clone_timeout_s)
        await self._check_store_size(dirs, limits)
        # Блобы папки паков приходят здесь, одной пачкой: checkout в частичном клоне подгружает недостающее сам.
        await self._runner.run(
            [
                "--work-tree",
                str(dirs.tree),
                "checkout",
                "--quiet",
                "--detach",
                "--no-recurse-submodules",
                remote_ref(branch),
            ],
            op=GitOp.clone,
            git_dir=dirs.git,
            target=target,
            timeout_s=self._config.clone_timeout_s,
        )
        await self._hydrate(dirs, target, packs_path=packs_path)
        return await self._tip(dirs, branch)

    async def fetch(self, dirs: WorkspaceDirs, target: RemoteTarget, *, branch: str, limits: WorkspaceLimits) -> str:
        branch = _branch(branch)
        await self._fetch(dirs, target, branch, timeout_s=self._config.fetch_timeout_s)
        await self._check_store_size(dirs, limits)
        await self._hydrate(dirs, target)
        return await self._tip(dirs, branch)

    async def released(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, branch: str, packs_path: str
    ) -> ReleasedVersions:
        branch = _branch(branch)
        ref = remote_ref(branch)
        listing = await self._local(
            dirs, ["ls-tree", "-r", "--name-only", "-z", ref, *(["--", packs_path] if packs_path != "." else [])]
        )
        prefix = "" if packs_path == "." else f"{packs_path}/"
        templates: dict[str, dict[str, str]] = {}
        for name in listing.decode("utf-8", errors="replace").split("\0"):
            rel = name[len(prefix) :] if name.startswith(prefix) else None
            if not rel or not is_registry_path(rel):
                continue
            text = await self._registry_text(dirs, target, f"{ref}:{name}")
            if text is None:
                continue
            pack, _, template, _ = rel.split("/")
            try:
                entries = parse_releases(text)
            except yaml.YAMLError:
                entries = {}  # битый реестр базы: как отсутствующий, линтер ветки покажет ошибку
            templates[template_key(pack, template)] = {v: e.digest for v, e in entries.items()}
        return ReleasedVersions(templates=templates, sha=await self._tip(dirs, branch))

    # ── срез T6: ветка, коммит, отправка, слияние базы ──

    async def status(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, packs_path: str
    ) -> WorkGitStatus:
        base = remote_ref(_branch(base_branch))
        head = (await self._local(dirs, ["rev-parse", "--verify", "HEAD^{commit}"])).decode("ascii").strip()
        branch_out = await self._run_local(dirs, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
        branch = branch_out.stdout.decode("utf-8", errors="replace").strip() if branch_out.returncode == 0 else None
        # Правила игнорирования и атрибуты git читает из блобов индекса: недостающий догружается с доступом.
        porcelain = await self._local(
            dirs,
            [
                *self._tree(dirs),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--no-renames",
                *_scope(packs_path),
            ],
            target=target,
        )
        uncommitted = _parse_porcelain(porcelain, packs_path)
        changed = {c.path: c for c in await self._changed_against(dirs, target, base, packs_path)}
        for change in uncommitted:
            if change.status is ChangeStatus.added:
                changed.setdefault(change.path, change)
        counts = (await self._local(dirs, ["rev-list", "--left-right", "--count", f"{base}...HEAD"])).decode().split()
        behind, ahead = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (0, 0)  # noqa: PLR2004
        return WorkGitStatus(
            head_sha=head,
            branch=branch,
            uncommitted=tuple(sorted(uncommitted, key=lambda c: c.path)),
            changed=tuple(sorted(changed.values(), key=lambda c: c.path)),
            ahead=ahead,
            behind=behind,
        )

    async def local_branches(self, dirs: WorkspaceDirs) -> tuple[str, ...]:
        out = await self._local(dirs, ["for-each-ref", "--format=%(refname:short)", "refs/heads/"])
        return tuple(line for line in out.decode("utf-8", errors="replace").splitlines() if line)

    async def create_branch(self, dirs: WorkspaceDirs, *, name: str) -> None:
        name = _branch(name)
        # Пустое старое значение: ветка создаётся, только если её ещё нет. Дерево и индекс не трогаются.
        await self._local(dirs, ["update-ref", f"refs/heads/{name}", "HEAD", ""])
        await self._local(dirs, ["symbolic-ref", "HEAD", f"refs/heads/{name}"])

    async def switch_branch(self, dirs: WorkspaceDirs, target: RemoteTarget, *, name: str, fetch: bool) -> str:
        name = _branch(name)
        if fetch:
            await self._fetch(dirs, target, name, timeout_s=self._config.fetch_timeout_s)
            await self._local(dirs, ["update-ref", f"refs/heads/{name}", remote_ref(name), ""])
        # Блобы ветки внутри папки паков подгружаются здесь же: команда с сетью.
        await self._runner.run(
            [*self._tree(dirs), "checkout", "--quiet", "--no-recurse-submodules", name],
            op=GitOp.fetch,
            git_dir=dirs.git,
            target=target,
            timeout_s=self._config.fetch_timeout_s,
        )
        await self._hydrate(dirs, target)
        return await self._head(dirs)

    async def commit(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, packs_path: str, message: str, author: VcsAuthor
    ) -> str | None:
        # `add -A` читает правила игнорирования и атрибуты: недостающий блоб догружается с доступом.
        await self._local(dirs, [*self._tree(dirs), "add", "-A", *_scope(packs_path)], target=target)
        # Плумбинг без поиска переименований: сравниваются только идентификаторы, блобы не читаются.
        staged = await self._run_local(
            dirs, [*self._tree(dirs), "diff-index", "--cached", "--quiet", "HEAD", "--"], check=False
        )
        if staged.returncode == 0:
            return None
        await self._local(
            dirs,
            [*_author_config(author), *self._tree(dirs), "commit", "--quiet", "--no-verify", "-m", message],
            target=target,
        )
        return await self._head(dirs)

    async def push(
        self,
        dirs: WorkspaceDirs,
        target: RemoteTarget,
        *,
        branch: str,
        push_options: Sequence[str] = (),
    ) -> PushOutcome:
        branch = _branch(branch)
        options = [part for option in push_options for part in ("-o", option)]
        result = await self._runner.run(
            [
                "push",
                "--porcelain",
                "--no-recurse-submodules",
                *options,
                "--",
                target.url.display_url,
                f"HEAD:refs/heads/{branch}",
            ],
            op=GitOp.push,
            git_dir=dirs.git,
            target=target,
            timeout_s=self._config.push_timeout_s,
        )
        return PushOutcome(sha=await self._head(dirs), remote_output=result.stderr)

    async def merge_base(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, author: VcsAuthor, message: str
    ) -> MergeOutcome:
        base = remote_ref(_branch(base_branch))
        contained = await self._run_local(dirs, ["merge-base", "--is-ancestor", base, "HEAD"], check=False)
        if contained.returncode == 0:
            return MergeOutcome(sha=await self._head(dirs), merged=False)
        try:
            await self._runner.run(
                [*_author_config(author), *self._tree(dirs), "merge", "--no-edit", "--no-verify", "-m", message, base],
                op=GitOp.fetch,
                git_dir=dirs.git,
                target=target,
                timeout_s=self._config.fetch_timeout_s,
            )
        except GitSyncError:
            unmerged = await self._run_local(
                dirs, [*self._tree(dirs), "diff", "--name-only", "-z", "--diff-filter=U"], check=False
            )
            conflicts = tuple(name for name in unmerged.stdout.decode("utf-8", errors="replace").split("\0") if name)
            await self._run_local(dirs, [*self._tree(dirs), "merge", "--abort"], check=False, target=target)
            if not conflicts:
                raise
            return MergeOutcome(sha=await self._head(dirs), merged=False, conflicts=conflicts)
        await self._hydrate(dirs, target)
        return MergeOutcome(sha=await self._head(dirs), merged=True)

    async def reset_to_base(self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str) -> str:
        base = remote_ref(_branch(base_branch))
        await self._runner.run(
            [*self._tree(dirs), "checkout", "--quiet", "--force", "--detach", "--no-recurse-submodules", base],
            op=GitOp.fetch,
            git_dir=dirs.git,
            target=target,
            timeout_s=self._config.fetch_timeout_s,
        )
        await self._hydrate(dirs, target)
        # Новые файлы, которых нет в базе, checkout не убирает.
        await self._local(dirs, [*self._tree(dirs), "clean", "-fdq", "--", "."], target=target)
        return await self._head(dirs)

    async def base_registries(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, paths: Sequence[str]
    ) -> dict[str, str]:
        ref = remote_ref(_branch(base_branch))
        texts: dict[str, str] = {}
        for path in paths:
            listed = await self._local(dirs, ["ls-tree", "-z", "--name-only", ref, "--", path])
            if not listed.strip(b"\0"):
                continue
            text = await self._registry_text(dirs, target, f"{ref}:{path}")
            if text is not None:
                texts[path] = text
        return texts

    async def diff(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, packs_path: str, max_bytes: int
    ) -> tuple[str, bool]:
        base = remote_ref(_branch(base_branch))
        # Новые файлы попадают в diff как «намерение добавить»: следующий коммит всё равно берёт их целиком.
        untracked = await self._local(
            dirs,
            [*self._tree(dirs), "ls-files", "-z", "--others", "--exclude-standard", *_scope(packs_path)],
            target=target,
        )
        names = [name for name in untracked.decode("utf-8", errors="replace").split("\0") if name]
        if names:
            await self._local(dirs, [*self._tree(dirs), "add", "--intent-to-add", "--", *names], target=target)
        result = await self._runner.run(
            [*self._tree(dirs), "diff", "--no-color", "--no-ext-diff", "--no-textconv", base, *_scope(packs_path)],
            op=GitOp.fetch,
            git_dir=dirs.git,
            target=target,
            timeout_s=self._config.fetch_timeout_s,
        )
        raw = result.stdout
        truncated = len(raw) > max_bytes
        return raw[:max_bytes].decode("utf-8", errors="replace"), truncated

    async def restore_from_base(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, paths: Sequence[str]
    ) -> None:
        base = remote_ref(_branch(base_branch))
        for path in paths:
            folder = dirs.tree / path
            if folder.is_symlink() or folder.is_file():
                folder.unlink()
            elif folder.is_dir():
                await asyncio.to_thread(shutil.rmtree, folder)
            listed = await self._local(dirs, ["ls-tree", "-z", "--name-only", base, "--", path])
            if not listed.strip(b"\0"):
                continue
            # Блобы базы в частичном клоне могут отсутствовать: команда с сетью, как checkout ветки.
            await self._runner.run(
                [*self._tree(dirs), "checkout", "--quiet", "--no-overlay", base, "--", path],
                op=GitOp.fetch,
                git_dir=dirs.git,
                target=target,
                timeout_s=self._config.fetch_timeout_s,
            )
        await self._hydrate(dirs, target)

    async def branch_paths(self, dirs: WorkspaceDirs, *, base_branch: str) -> tuple[str, ...]:
        base = remote_ref(_branch(base_branch))
        # Три точки: от точки расхождения с базой, поэтому слитая в ветку база (merge-base) сюда не попадает.
        # Нужны только деревья, блобы частичного клона не подгружаются.
        raw = await self._local(dirs, ["diff", "--name-only", "-z", "--no-renames", f"{base}...HEAD"])
        return tuple(name for name in raw.decode("utf-8", errors="replace").split("\0") if name)

    # ── срез O2: чтение версии из коммита без checkout ──

    async def revision_sha(self, dirs: WorkspaceDirs, *, name: GitRevisionName, base_branch: str) -> str | None:
        spec = "HEAD" if name == "head" else remote_ref(_branch(base_branch))
        result = await self._run_local(dirs, ["rev-parse", "--verify", "--quiet", f"{spec}^{{commit}}"], check=False)
        sha = result.stdout.decode("ascii", errors="replace").strip()
        return sha if result.returncode == 0 and sha else None

    async def revision_files(  # noqa: PLR0913 — коммит, пути и пределы
        self,
        dirs: WorkspaceDirs,
        target: RemoteTarget,
        *,
        sha: str,
        prefixes: Sequence[str],
        max_files: int,
        max_bytes: int,
    ) -> dict[str, bytes]:
        if not _SHA.fullmatch(sha):
            raise PackStudioError(PackStudioErrorCode.workspace_git_failed, hint="rev-parse: not a commit id")
        if any(prefix.startswith(":") or _PATHSPEC_GLOB.search(prefix) for prefix in prefixes):
            # Имена из адреса запроса идут в `ls-tree` как пути; магия и шаблоны путей git им не нужны.
            raise PackStudioError(PackStudioErrorCode.path_not_allowed)
        raw = await self._local(dirs, ["ls-tree", "-r", "-z", "--long", sha, "--", *prefixes], target=target)
        blobs = _listed_blobs(raw)
        if len(blobs) > max_files or sum(size for _, _, size in blobs) > max_bytes:
            raise PackStudioError(PackStudioErrorCode.workspace_too_large)
        if not blobs:
            return {}
        # Недостающие блобы частичного клона берутся одной пачкой, а не по одному на каждый `cat-file`.
        missing = await self._missing(dirs, [sha])
        absent = sorted({oid for _, oid, _ in blobs if oid in missing})
        if absent:
            await self._fetch_objects(dirs, target, absent)
        gate = asyncio.Semaphore(_READ_PARALLEL)

        async def read(oid: str) -> bytes:
            async with gate:
                return await self._local(dirs, ["cat-file", "blob", oid], target=target)

        contents = await asyncio.gather(*(read(oid) for _, oid, _ in blobs))
        return {path: data for (path, _, _), data in zip(blobs, contents, strict=True)}

    async def _changed_against(
        self, dirs: WorkspaceDirs, target: RemoteTarget, base: str, packs_path: str
    ) -> list[FileChange]:
        """Файлы рабочего дерева, которые отличаются от базы, без чтения блобов базы.

        Porcelain `git diff <база>` для файла, правленого на диске, сравнивает содержимое с блобом базы, а в частичном
        клоне после выборки базы его нет: локальная команда падала на ленивой подгрузке. `diff-index` сравнивает только
        идентификаторы; файлы, которые на диске отличаются от индекса, хэшируются здесь же и сверяются с базой.
        """
        raw = await self._local(
            dirs, [*self._tree(dirs), "diff-index", "--raw", "-z", "--no-renames", base, *_scope(packs_path)]
        )
        entries = _parse_raw(raw)
        same = await self._equal_to_base(dirs, target, [e for e in entries if e.work_unknown])
        changes: list[FileChange] = []
        for entry in entries:
            rel = _rel(entry.path, packs_path)
            if rel and entry.path not in same:
                changes.append(FileChange(rel, _status_of(entry.status)))
        return changes

    async def _equal_to_base(
        self, dirs: WorkspaceDirs, target: RemoteTarget, entries: Sequence[_RawChange]
    ) -> set[str]:
        """Пути, чей текст на диске совпадает с базой: `hash-object` с теми же преобразованиями, что у `add`."""
        files = [e for e in entries if (dirs.tree / e.path).is_file() and not (dirs.tree / e.path).is_symlink()]
        same: set[str] = set()
        for start in range(0, len(files), _HASH_BATCH):
            batch = files[start : start + _HASH_BATCH]
            result = await self._run_local(
                dirs,
                ["-C", str(dirs.tree), *self._tree(dirs), "hash-object", "--", *(e.path for e in batch)],
                check=False,
                target=target,
            )
            if result.returncode != 0:
                # Файл успели убрать или заменить папкой: от базы он точно отличается.
                continue
            hashes = result.stdout.decode("ascii", errors="replace").split()
            same.update(e.path for e, oid in zip(batch, hashes, strict=False) if oid == e.base_oid)
        return same

    @staticmethod
    def _tree(dirs: WorkspaceDirs) -> list[str]:
        return ["--work-tree", str(dirs.tree)]

    async def _head(self, dirs: WorkspaceDirs) -> str:
        return (await self._local(dirs, ["rev-parse", "--verify", "HEAD^{commit}"])).decode("ascii").strip()

    async def _registry_text(self, dirs: WorkspaceDirs, target: RemoteTarget, spec: str) -> str | None:
        # Размер спрашивается с сетью: блоба новой вершины базы в частичном клоне может ещё не быть.
        sized = await self._runner.run(
            ["cat-file", "-s", spec], op=GitOp.fetch, git_dir=dirs.git, target=target, timeout_s=_LOCAL_TIMEOUT_S
        )
        try:
            size = int(sized.stdout.decode("ascii", errors="replace").strip())
        except ValueError:
            return None
        if size > _REGISTRY_MAX_BYTES:
            return None
        blob = await self._local(dirs, ["cat-file", "blob", spec])
        return blob.decode("utf-8", errors="replace")

    async def _fetch(self, dirs: WorkspaceDirs, target: RemoteTarget, branch: str, *, timeout_s: float) -> None:
        await self._runner.run(
            [
                "fetch",
                "--filter=blob:none",
                "--no-tags",
                "--no-recurse-submodules",
                "--no-write-fetch-head",
                "--progress",
                "--",
                _REMOTE,
                f"+refs/heads/{branch}:{remote_ref(branch)}",
            ],
            op=GitOp.fetch,
            git_dir=dirs.git,
            target=target,
            timeout_s=timeout_s,
        )

    async def _check_store_size(self, dirs: WorkspaceDirs, limits: WorkspaceLimits) -> None:
        out = (await self._local(dirs, ["count-objects", "-v"])).decode("ascii", errors="replace")
        kib = 0
        for line in out.splitlines():
            key, _, value = line.partition(":")
            if key.strip() in {"size", "size-pack"}:
                kib += int(value.strip() or 0)
        if kib * _KIB > limits.max_clone_bytes:
            raise PackStudioError(PackStudioErrorCode.workspace_too_large)

    async def _tip(self, dirs: WorkspaceDirs, branch: str) -> str:
        out = await self._local(dirs, ["rev-parse", "--verify", "--quiet", f"{remote_ref(branch)}^{{commit}}"])
        return out.decode("ascii", errors="replace").strip()

    async def _local(self, dirs: WorkspaceDirs, args: list[str], *, target: RemoteTarget | None = None) -> bytes:
        return (await self._run_local(dirs, args, target=target)).stdout

    async def _run_local(
        self,
        dirs: WorkspaceDirs | None,
        args: list[str],
        *,
        check: bool = True,
        target: RemoteTarget | None = None,
    ) -> GitResult:
        """Локальная команда без сети. Её сбой это состояние хранилища на сервере, а не отказ хостинга: человек
        получает понятный код пространства с безопасной подсказкой (`hint`), а очищенный вывод git идёт в журнал.

        С `target` команда, которой не хватило объекта частичного клона, догружает его сетевой командой с доступом
        пространства (`_hydrate`) и повторяется: сама она в сеть по-прежнему не ходит.
        """
        command = _subcommand(args)
        for round_ in range(_LAZY_ROUNDS + 1):
            result = await self._runner.run_local(
                args, git_dir=dirs.git if dirs is not None else None, timeout_s=_LOCAL_TIMEOUT_S, check=False
            )
            if result.returncode == 0:
                return result
            missing = _promised_object(result.stderr)
            if missing is None or target is None or dirs is None or round_ == _LAZY_ROUNDS:
                break
            logger.info("pack studio: local git needs a missing object", command=command, round=round_ + 1)
            await self._hydrate(dirs, target, extra=(missing,))
        if not check:
            return result
        logger.warning(
            "pack studio: local git failed",
            command=command,
            detail=scrub(result.stderr)[-DETAIL_TAIL_CHARS:].strip(),
        )
        raise PackStudioError(PackStudioErrorCode.workspace_git_failed, hint=git_hint(command, result.stderr))

    async def _hydrate(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, packs_path: str | None = None, extra: Sequence[str] = ()
    ) -> None:
        """Догрузить блобы, которые может прочитать локальный git: папка паков в HEAD и в выбранных ветках сервера,
        файлы `.gitignore`, `.gitattributes`, `.gitmodules` на пути к ней и `extra`. Паки маленькие, поэтому для
        их папки блобы держатся целиком. Сеть только когда чего-то нет; проверка наличия ничего не подгружает."""
        packs = packs_path if packs_path is not None else self._packs_path(dirs)
        tips = await self._tips(dirs)
        wanted: set[str] = set(extra)
        pathspec = ["--", "."] if packs == "." else ["--", packs, *_control_paths(packs)]
        for tip in tips:
            listed = await self._run_local(dirs, ["ls-tree", "-r", "-z", tip, *pathspec], check=False)
            if listed.returncode == 0:
                wanted |= _blob_oids(listed.stdout)
        if not wanted:
            return
        missing = await self._missing(dirs, tips)
        await self._fetch_objects(dirs, target, sorted(oid for oid in wanted if oid in missing or oid in extra))

    async def _fetch_objects(self, dirs: WorkspaceDirs, target: RemoteTarget, oids: Sequence[str]) -> None:
        """Догрузить объекты по идентификаторам пачками (сеть только через запускатель, с доступом `target`)."""
        for start in range(0, len(oids), _FETCH_BATCH):
            await self._runner.run(
                [
                    "-c",
                    "fetch.negotiationAlgorithm=noop",
                    "fetch",
                    "--no-tags",
                    "--no-write-fetch-head",
                    "--no-recurse-submodules",
                    "--filter=blob:none",
                    "--",
                    _REMOTE,
                    *oids[start : start + _FETCH_BATCH],
                ],
                op=GitOp.fetch,
                git_dir=dirs.git,
                target=target,
                timeout_s=self._config.fetch_timeout_s,
            )

    async def _tips(self, dirs: WorkspaceDirs) -> list[str]:
        """HEAD (если он есть) и выбранные ветки сервера: из них берутся пути и их блобы."""
        refs = await self._run_local(dirs, ["for-each-ref", "--format=%(refname)", f"refs/remotes/{_REMOTE}/"])
        tips = [line for line in refs.stdout.decode("utf-8", errors="replace").splitlines() if line]
        head = await self._run_local(dirs, ["rev-parse", "--verify", "--quiet", "HEAD^{commit}"], check=False)
        return ["HEAD", *tips] if head.returncode == 0 else tips

    async def _missing(self, dirs: WorkspaceDirs, tips: Sequence[str]) -> set[str]:
        """Объекты деревьев `tips`, которых нет в хранилище. `--missing=print` ничего не подгружает."""
        if not tips:
            return set()
        out = await self._local(dirs, ["rev-list", "--objects", "--missing=print", "--no-walk", *tips])
        return {line[1:] for line in out.decode("ascii", errors="replace").splitlines() if line.startswith("?")}

    @staticmethod
    def _packs_path(dirs: WorkspaceDirs) -> str:
        """Папка паков из шаблона разреженной выборки (`/<папка>/`); без шаблона пространство видит весь репозиторий."""
        sparse = dirs.git / "info" / "sparse-checkout"
        try:
            pattern = sparse.read_text(encoding="utf-8").strip()
        except OSError:
            return "."
        folder = pattern.strip("/")
        return folder or "."

    @staticmethod
    def _fresh_dirs(dirs: WorkspaceDirs) -> None:
        """Клон с нуля: прежнее хранилище и дерево (неудачная попытка) убираются, папка самого пространства остаётся."""
        dirs.root.mkdir(parents=True, exist_ok=True)
        for folder in (dirs.git, dirs.tree):
            if folder.is_symlink() or folder.is_file():
                folder.unlink()
            elif folder.exists():
                shutil.rmtree(folder)
        dirs.tree.mkdir()


def workspace_dirs(root: Path) -> WorkspaceDirs:
    return WorkspaceDirs(root=root, git=root / "git", tree=root / "tree")
