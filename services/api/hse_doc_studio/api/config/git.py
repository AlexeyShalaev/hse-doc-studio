"""Настройки VCS и Git-синхронизации."""

from pydantic import BaseModel, Field


class VCSConfig(BaseModel):
    """ProjectVCS (system-git) settings.

    The store is per-project and isolated at ``<project>/.hse-studio/git/`` — it
    is never placed in the project root and never touches the user's own git.
    These are deployment defaults; per-project toggles (tracking, PDF, auto-commit
    on compile) live in project.meta["vcs"].
    """

    enabled: bool = Field(default=True, description="Master switch for ProjectVCS auto-tracking.")
    default_branch: str = Field(default="master", description="Initial branch name for a new project store.")
    author_name: str = Field(default="HSE Studio", description="Committer name for service commits.")
    author_email: str = Field(default="bot@hse-studio.local", description="Committer email for service commits.")
    diff_max_bytes: int = Field(default=256_000, description="Byte budget for an assembled diff before truncation.")
    track_pdf: bool = Field(
        default=False,
        description="Global default for whether compiled PDFs enter history (per-project setting overrides).",
    )
    edit_min_interval_seconds: float = Field(
        default=5.0,
        description="Throttle window for edit-commits (phase 2); edits within it are folded into the next commit.",
    )


class GitConfig(BaseModel):
    """Синхронизация проекта с удалённым git-репозиторием (HSE_STUDIO__GIT__*).

    Сеть работает только через изолированное хранилище проекта; git пользователя, его ssh-ключи
    и менеджеры паролей не читаются. Здесь параметры развёртывания, а не выбор пользователя.
    """

    enabled: bool = Field(default=True, description="Master switch for remotes, sync and clone from git.")
    ssh_binary: str = Field(default="ssh", description="ssh client used for ssh:// and scp-like remotes.")
    ssh_keyscan_binary: str = Field(default="ssh-keyscan", description="Tool that reads host keys of an ssh server.")
    scan_timeout_s: float = Field(default=10.0, description="Timeout for reading the host keys of a server.")
    git_min_version: str = Field(
        default="2.31", description="Oldest git the sync works with; older reports git_unavailable."
    )
    allow_insecure_http: bool = Field(
        default=False,
        description="Allow plain http remotes (each remote must opt in too). Off: tokens would travel in clear.",
    )
    allow_local_remotes: bool = Field(
        default=True,
        description="Allow file:// and absolute-path remotes. Local mode only; a shared server never allows them.",
    )
    probe_timeout_s: float = Field(default=20.0, description="Timeout for checking a remote address.")
    provider_detect_timeout_s: float = Field(
        default=3.0,
        description="Timeout of each request that recognizes a git server (GitLab, Gitea, GitHub Enterprise).",
    )
    token_check_timeout_s: float = Field(
        default=10.0, description="Timeout of a request to the hosting API that tells whose token it is and its scopes."
    )
    fetch_timeout_s: float = Field(default=120.0, description="Timeout for one fetch.")
    push_timeout_s: float = Field(default=300.0, description="Timeout for one push.")
    clone_timeout_s: float = Field(
        default=900.0, description="Timeout for cloning and the first push of a long history."
    )
    bundle_timeout_s: float = Field(
        default=600.0, description="Timeout for one git command over a bundle file (create, verify, unpack)."
    )
    bundle_max_bytes: int = Field(
        default=2_000_000_000,
        ge=1,
        description="Largest bundle file the Studio accepts for import or for cloning a project.",
    )
    max_incoming_blob_bytes: int = Field(
        default=512_000_000,
        ge=1,
        description=(
            "Largest single file of a remote branch the Studio reads into memory and writes to the project. "
            "A tiny pack can expand into a huge blob, so a sync, a clone or an import refuses bigger files."
        ),
    )
    max_incoming_total_bytes: int = Field(
        default=2_000_000_000,
        ge=1,
        description="Largest total size of the files one sync, clone or import takes from a remote branch.",
    )
    fetch_tick_s: float = Field(
        default=30.0, description="How often the background fetch looks for projects that are due."
    )
    fetch_startup_delay_s: float = Field(
        default=60.0, description="Delay before the first background fetch after the server starts."
    )
    fetch_concurrency: int = Field(default=2, ge=1, description="Projects fetched in the background at the same time.")
    large_file_warn_bytes: int = Field(
        default=95_000_000,
        description="Blobs from this size are reported before push: hosting services reject files near 100 MB.",
    )
