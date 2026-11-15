"""Git рабочего пространства как поток предложения (docs/design/template-studio.md, 4.3 и 4.4, срез T6).

Чистые правила без процессов и сети: имя рабочей ветки, сообщение коммита по соглашению, push options GitLab, ссылка
«Открыть PR в браузере» (compare), описание PR, сводка проверок хостинга. Сеть и git живут в infra за портами
`IPackWorkspaceGit` и `IPackHosting`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from urllib.parse import quote, urlsplit

from hse_doc_studio.core.git_sync.providers import GitProvider
from hse_doc_studio.core.pack_studio.paths import TEMPLATES_DIR, VersionRef, version_ref_of

BRANCH_PREFIX = "pack-studio"
_SLUG_MAX = 40
_BRANCH_MAX = 200
_TITLE_MAX = 200
# Описание PR и MR: GitHub принимает до 65536 символов, push option GitLab идёт одной строкой протокола.
BODY_MAX = 60_000
PUSH_OPTION_MAX = 4_000
_MR_URL = re.compile(r"https?://\S+/-/merge_requests/(\d+)")
_SLUG_BAD = re.compile(r"[^a-z0-9._-]+")


class ChangeStatus(StrEnum):
    added = "added"
    modified = "modified"
    deleted = "deleted"


@dataclass(frozen=True)
class FileChange:
    """Изменённый файл: путь от папки паков пространства."""

    path: str
    status: ChangeStatus


@dataclass(frozen=True)
class WorkGitStatus:
    """Состояние git рабочего пространства.

    `branch` None: дерево стоит на вершине базы без ветки (до первого коммита). `uncommitted` правки на диске после
    последнего коммита; `changed` всё, чем пространство отличается от базы (коммиты и правки вместе). `ahead` и
    `behind` считаются от последней выборки базы.
    """

    head_sha: str
    branch: str | None
    uncommitted: tuple[FileChange, ...]
    changed: tuple[FileChange, ...]
    ahead: int
    behind: int

    @property
    def dirty(self) -> bool:
        return bool(self.uncommitted)


@dataclass(frozen=True)
class PushOutcome:
    """Что отправлено и что сервер сказал после отправки (GitLab печатает ссылку на MR в `remote:`)."""

    sha: str
    remote_output: str


@dataclass(frozen=True)
class MergeOutcome:
    """Слияние базы в рабочую ветку: `merged` False, если ветка уже содержала базу; конфликты отменяют слияние."""

    sha: str
    merged: bool
    conflicts: tuple[str, ...] = ()


# ── хостинг ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HostingRepo:
    """Репозиторий у хостинга: провайдер, путь `владелец/репозиторий` (у GitLab с подгруппами), корни сайта и API."""

    provider: GitProvider
    path: str
    web_base: str | None
    api_base: str | None
    ca_file: Path | None = None

    @property
    def owner(self) -> str:
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def web_url(self) -> str | None:
        return None if self.web_base is None else f"{self.web_base}/{self.path}"


@dataclass(frozen=True)
class RepoPermissions:
    """Что токен может в репозитории; None: хостинг не сказал (точный токен без Metadata, другой провайдер)."""

    can_push: bool | None


@dataclass(frozen=True)
class ForkRef:
    """Форк пользователя: путь у того же хостинга и адрес для git."""

    path: str
    clone_url: str


@dataclass(frozen=True)
class PullRequestRef:
    number: int
    url: str
    # False: запрос на слияние из этой ветки уже был открыт, найден существующий.
    created: bool = True


class CiState(StrEnum):
    """Сводка проверок по вершине ветки: нет проверок, идут, все прошли, что-то упало, неизвестно."""

    none = "none"
    pending = "pending"
    success = "success"
    failure = "failure"
    unknown = "unknown"


class CheckState(StrEnum):
    queued = "queued"
    running = "running"
    success = "success"
    failure = "failure"
    neutral = "neutral"
    skipped = "skipped"
    cancelled = "cancelled"


@dataclass(frozen=True)
class CiCheck:
    name: str
    state: CheckState
    url: str | None = None
    # Короткая причина от хостинга (`description` статуса, `output.title` проверки); без журналов.
    summary: str | None = None


@dataclass(frozen=True)
class CiReport:
    """Статус проверок хостинга. `available` False: хостинг не отдаёт статус этому токену или провайдеру; тогда
    `reason` это код (`ci_status_unavailable`, `pr_permission_missing`), а `web_url` ведёт на страницу проверок."""

    state: CiState
    sha: str | None
    checks: tuple[CiCheck, ...] = ()
    available: bool = True
    reason: str | None = None
    web_url: str | None = None


_FINAL_OK = frozenset({CheckState.success, CheckState.neutral, CheckState.skipped})
_RUNNING = frozenset({CheckState.queued, CheckState.running})


def summarize_checks(checks: Iterable[CiCheck]) -> CiState:
    """Упавшая проверка важнее идущей, идущая важнее прошедших; отменённая считается упавшей."""
    states = [check.state for check in checks]
    if not states:
        return CiState.none
    if any(state in {CheckState.failure, CheckState.cancelled} for state in states):
        return CiState.failure
    if any(state in _RUNNING for state in states):
        return CiState.pending
    return CiState.success if all(state in _FINAL_OK for state in states) else CiState.unknown


# ── имена, сообщения, ссылки ────────────────────────────────────────────────


def slug(text: str, *, fallback: str) -> str:
    """Часть имени ветки: латиница, цифры, `._-`; кириллица и прочее отбрасываются."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    cleaned = _SLUG_BAD.sub("-", ascii_text).strip("-.")
    cleaned = re.sub(r"[-.]{2,}", "-", cleaned)[:_SLUG_MAX].strip("-.")
    return cleaned or fallback


def changed_versions(changes: Iterable[FileChange]) -> tuple[VersionRef, ...]:
    """Версии шаблонов, которых касаются изменения, по порядку путей и без повторов."""
    seen: dict[str, VersionRef] = {}
    for change in changes:
        ref = version_ref_of(change.path)
        if ref is not None:
            bare = VersionRef(ref.pack, ref.template, ref.version)
            seen.setdefault(bare.dir, bare)
    return tuple(seen.values())


def touched_scopes(changes: Iterable[FileChange]) -> tuple[str, ...]:
    """Каталоги для проверки (4.4): шаблон для путей внутри шаблона, пак для файлов самого пака."""
    scopes: dict[str, None] = {}
    for change in changes:
        parts = change.path.split("/")
        if len(parts) >= 3 and parts[1].casefold() == TEMPLATES_DIR:  # noqa: PLR2004
            scopes.setdefault("/".join(parts[:3]))
        elif len(parts) >= 2:  # noqa: PLR2004
            scopes.setdefault(parts[0])
    return tuple(scopes)


def work_branch_name(user: str, versions: Sequence[VersionRef], now: datetime, taken: Iterable[str] = ()) -> str:
    """`pack-studio/<человек>/<пак>-<шаблон>-<версия>` (4.1) или с меткой времени, если версий не одна."""
    who = slug(user, fallback="author")
    if len(versions) == 1:
        ref = versions[0]
        tail = "-".join(slug(part, fallback="x") for part in (ref.pack, ref.template, ref.version))
    else:
        tail = now.strftime("%Y%m%d-%H%M")
    base = f"{BRANCH_PREFIX}/{who}/{tail}"[:_BRANCH_MAX]
    used = {name.casefold() for name in taken}
    name, index = base, 2
    while name.casefold() in used:
        name = f"{base}-{index}"
        index += 1
    return name


@dataclass(frozen=True)
class VersionSummary:
    """Версия в предложении: её класс по классификатору и заметки `changes` (5.8, 7.4)."""

    ref: VersionRef
    released_base: str | None = None
    minimum: str | None = None
    suggested: str | None = None
    by_number: str | None = None
    headline: Mapping[str, str] = field(default_factory=dict)
    reasons: tuple[Mapping[str, str], ...] = ()
    changes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def update_class(self) -> str | None:
        return self.by_number or self.suggested or self.minimum


def default_commit_message(versions: Sequence[VersionSummary]) -> str:
    """Conventional commits (4.3): `fix(packs)` для patch, `feat(packs)` для minor и major и без класса."""
    if not versions:
        return "chore(packs): правка паков в Студии шаблонов"
    kinds = {summary.update_class for summary in versions}
    kind = "fix" if kinds == {"patch"} else "feat"
    names = ", ".join(f"{v.ref.pack}/{v.ref.template} {v.ref.version}" for v in versions[:3])
    more = f" и ещё {len(versions) - 3}" if len(versions) > 3 else ""  # noqa: PLR2004
    return f"{kind}(packs): {names}{more}"[:_TITLE_MAX]


@dataclass(frozen=True)
class CheckSummary:
    errors: int
    warnings: int


def _version_lines(summary: VersionSummary) -> list[str]:
    ref = summary.ref
    lines = [f"### {ref.pack} / {ref.template} {ref.version}"]
    if summary.update_class:
        base = f" (от {summary.released_base})" if summary.released_base else ""
        lines.append(f"Класс: **{summary.update_class}**{base}")
        if summary.minimum and summary.minimum != summary.update_class:
            lines.append(f"Минимум по изменениям: {summary.minimum}")
    if summary.headline.get("ru"):
        lines.append(summary.headline["ru"])
    lines += [f"- {reason.get('ru') or reason.get('en', '')}" for reason in summary.reasons]
    for lang, title in (("ru", "Изменения"), ("en", "Changes")):
        notes = summary.changes.get(lang, ())
        if notes:
            lines += ["", f"{title}:", *(f"- {note}" for note in notes)]
    lines.append("")
    return lines


def proposal_body(
    versions: Sequence[VersionSummary],
    checks: CheckSummary | None,
    *,
    proposed_by: str | None,
    extra: str | None = None,
) -> str:
    """Описание PR (4.3, шаг 3): версии, класс и причины, заметки ru/en, сводка проверок, кто предложил."""
    lines: list[str] = []
    if extra and extra.strip():
        lines += [extra.strip(), ""]
    for summary in versions:
        lines += _version_lines(summary)
    if checks is not None:
        verdict = "пройдены" if checks.errors == 0 else "есть ошибки"
        lines.append(f"Проверки Студии шаблонов: {verdict}, ошибок {checks.errors}, предупреждений {checks.warnings}.")
    lines.append(
        f"Предложено в Студии шаблонов пользователем {proposed_by}." if proposed_by else "Предложено в Студии шаблонов."
    )
    return "\n".join(lines).strip()[:BODY_MAX]


def gitlab_push_options(*, target_branch: str, title: str, description: str) -> list[str]:
    """`git push -o` для MR GitLab (D8): хватает `write_repository`. Переводы строк протокол не пропускает."""
    flat = " ".join(description.split())[:PUSH_OPTION_MAX]
    return [
        "merge_request.create",
        f"merge_request.target={target_branch}",
        f"merge_request.title={' '.join(title.split())[:_TITLE_MAX]}",
        f"merge_request.description={flat}",
        "merge_request.remove_source_branch",
    ]


def merge_request_from_output(text: str) -> PullRequestRef | None:
    """Ссылка на MR, которую GitLab печатает после push (`remote:   https://.../-/merge_requests/7`)."""
    match = _MR_URL.search(text)
    if match is None:
        return None
    return PullRequestRef(number=int(match.group(1)), url=match.group(0))


def compare_url(repo: HostingRepo, *, base: str, branch: str, fork: ForkRef | None) -> str | None:
    """«Открыть PR в браузере»: страница создания запроса на слияние с готовой веткой (D8)."""
    if repo.web_url is None:
        return None
    enc = quote(branch, safe="/")
    if repo.provider is GitProvider.github:
        head = f"{fork.path.split('/', 1)[0]}:{enc}" if fork is not None else enc
        return f"{repo.web_url}/compare/{quote(base, safe='/')}...{head}?expand=1"
    if repo.provider is GitProvider.gitlab:
        source = f"{repo.web_base}/{fork.path}" if fork is not None and repo.web_base else repo.web_url
        return f"{source}/-/merge_requests/new?merge_request%5Bsource_branch%5D={quote(branch, safe='')}"
    if repo.provider is GitProvider.gitea:
        head = f"{fork.path.split('/', 1)[0]}:{enc}" if fork is not None else enc
        return f"{repo.web_url}/compare/{quote(base, safe='/')}...{head}"
    return None


def checks_page_url(repo: HostingRepo, *, branch: str | None, sha: str | None) -> str | None:
    """Страница проверок у хостинга: туда ведёт ссылка, когда статус не отдают API."""
    if repo.web_url is None:
        return None
    if repo.provider is GitProvider.github and sha:
        return f"{repo.web_url}/commit/{sha}/checks"
    if repo.provider is GitProvider.gitlab:
        ref = f"?ref={quote(branch, safe='')}" if branch else ""
        return f"{repo.web_url}/-/pipelines{ref}"
    return None


def repo_path_of(display_url: str, web_base: str | None) -> str:
    """`владелец/репозиторий` из адреса без `.git` и без пути установки (`https://host/gitlab/group/proj`)."""
    path = urlsplit(display_url).path.strip("/")
    path = path.removesuffix(".git").strip("/")
    prefix = urlsplit(web_base).path.strip("/") if web_base else ""
    if prefix and path.startswith(f"{prefix}/"):
        path = path[len(prefix) + 1 :]
    return path


def repo_key(host: str | None, port: int | None, path: str) -> str:
    """Ключ репозитория для служебного доступа: хост, порт и путь без учёта регистра и `.git`."""
    authority = (host or "").lower() + (f":{port}" if port else "")
    return f"{authority}/{path.strip('/').removesuffix('.git').strip('/').lower()}"
