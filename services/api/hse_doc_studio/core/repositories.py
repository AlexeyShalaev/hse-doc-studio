from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from hse_doc_studio.core.catalog import PackInfo, TemplateVersion
from hse_doc_studio.core.entities import (
    AgentPersona,
    AgentRunRecord,
    AIProvider,
    ChangeLogEntry,
    ChatMessage,
    ChatSession,
    ChatSummaryBlock,
    CompileRecord,
    PackSubmissionRecord,
    Project,
    SigningIdentity,
    SigningKeyMaterial,
)
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.listing import Paged, SortOrder, Window
from hse_doc_studio.core.value_objects import FormState, SignaturesState


@dataclass(frozen=True)
class BrowseEntry:
    name: str
    path: Path
    is_dir: bool
    is_hidden: bool


class IProjectRepository(Protocol):
    def get(self, folder: Path) -> Project | None: ...
    def save(self, project: Project) -> None: ...


class IProjectIndexRepository(Protocol):
    def list_known(self) -> list[Path]: ...
    def register(self, folder: Path) -> None: ...
    def unregister(self, folder: Path) -> None: ...


@runtime_checkable
class IProjectIndexLookup(Protocol):
    """Индекс, умеющий найти проект по id сам, без перебора папок (серверный каталог в Postgres)."""

    async def locate(self, project_id: UUID) -> tuple[Path, Project] | None: ...


class ICompileRepository(Protocol):
    async def get_for_project(self, project_folder: Path, compile_id: UUID) -> CompileRecord | None: ...
    # Записи документа от старых к новым (по started_at).
    async def list_for_document(self, project_folder: Path, doc_id: str) -> list[CompileRecord]: ...
    # Записи проекта в состоянии pending/running: нужны восстановлению после сбоя.
    async def list_unfinished(self, project_folder: Path) -> list[CompileRecord]: ...
    async def save(self, record: CompileRecord) -> None: ...


class ITemplateRepository(Protocol):
    def list_packs(self) -> list[PackInfo]: ...
    def get_version(self, pack_id: str, template_id: str, version: str) -> TemplateVersion | None: ...
    def list_versions(self, pack_id: str, template_id: str) -> list[str]: ...
    def version_dir(self, pack_id: str, template_id: str, version: str) -> Path | None: ...
    # Дайджест содержимого каталога версии (как в releases.yaml); None — версии нет.
    def content_digest(self, pack_id: str, template_id: str, version: str) -> str | None: ...


class ISignatureRepository(Protocol):
    def get_state(self, project_folder: Path) -> SignaturesState: ...
    def save_state(self, project_folder: Path, state: SignaturesState) -> None: ...


class IFormStateRepository(Protocol):
    # Per-form raw answers, stored at <folder>/.hse-studio/forms/<form_id>.json.
    # The repo is form-agnostic: it round-trips a FormState blob and knows
    # nothing about which fields a given form declares.
    def get_state(self, project_folder: Path, form_id: str) -> FormState | None: ...
    def save_state(self, project_folder: Path, form_id: str, state: FormState) -> None: ...


class IChangeLogRepository(Protocol):
    def list(self, project_folder: Path, doc_id: str | None = None) -> list[ChangeLogEntry]: ...
    def append(self, project_folder: Path, entry: ChangeLogEntry) -> None: ...


class IPackSubmissionRepository(Protocol):
    async def list_for_project(self, project_folder: Path) -> list[PackSubmissionRecord]: ...
    async def get(self, project_folder: Path, submission_id: UUID) -> PackSubmissionRecord | None: ...
    async def save(self, record: PackSubmissionRecord) -> None: ...


@dataclass(frozen=True)
class ScannedEntry:
    """Запись обхода дерева проекта: путь плюс уже снятая статистика.

    Статистика едет вместе с путём намеренно: она и так читается при листинге
    каталога, а повторный `stat()` на каждый элемент — лишний системный вызов,
    и на бинд-маунте Docker это заметно.
    """

    path: str
    is_dir: bool
    size: int
    mtime: float


class IFileRepository(Protocol):
    def read(self, folder: Path, path: str) -> bytes: ...
    def write(self, folder: Path, path: str, content: bytes) -> None: ...
    def scan(self, folder: Path) -> list[ScannedEntry]: ...
    def list_files(self, folder: Path) -> list[str]: ...
    def list_dirs(self, folder: Path) -> list[str]: ...
    def exists(self, folder: Path, path: str) -> bool: ...
    def delete(self, folder: Path, path: str) -> None: ...
    def move(self, folder: Path, src: str, dst: str) -> None: ...
    def mkdir(self, folder: Path, path: str) -> None: ...


class ISettingsRepository(Protocol):
    async def get(self) -> dict[str, Any]: ...
    async def save(self, settings: dict[str, Any]) -> None: ...


class ILocalSettingsReader(Protocol):
    # Синхронное чтение config.json для мест, куда await не дотянуть (подпись коммита
    # на git-подпроцессе). Только локальный режим: на сервере профиль берётся из users.
    def read_local(self) -> dict[str, Any]: ...


class IAIProviderRepository(Protocol):
    # CRUD over the local list of configured AI providers. The use case owns id
    # / created_at generation and the "keep the existing key when blank" rule;
    # the repository is a dumb persistence layer (mirrors IProjectRepository).
    async def list_all(self) -> list[AIProvider]: ...
    async def get(self, provider_id: UUID) -> AIProvider | None: ...
    async def create(self, provider: AIProvider) -> None: ...
    async def update(self, provider: AIProvider) -> None: ...
    async def delete(self, provider_id: UUID) -> bool: ...


INSTANCE_AI_PROVIDER_SORT_FIELDS = ("name", "type", "created_at")


@dataclass(frozen=True)
class InstanceAiProviderQuery:
    q: str | None = None
    types: frozenset[AIProviderType] = frozenset()
    sort: SortOrder = SortOrder("created_at")
    window: Window = Window()


class IInstanceAiProviderDirectory(Protocol):
    # Server only: shared (owner_kind=instance) providers for the admin console. Search, filter, order and
    # window are applied by the storage; personal providers of users never reach this list.
    async def list_instance(self, query: InstanceAiProviderQuery) -> Paged[AIProvider]: ...


class ISigningIdentityRepository(Protocol):
    # CRUD over signing credentials. Local: data_dir/signing_identities.json plus key
    # material in data_dir/signing_keys/<id>/; server: Postgres, the private key is
    # stored encrypted and only if the instance admin allowed it (ISigningKeyPolicy).
    async def list_all(self) -> list[SigningIdentity]: ...
    async def get(self, identity_id: UUID) -> SigningIdentity | None: ...
    # `material` is written together with the record (self-signed / PKCS#12 identities).
    async def create(self, identity: SigningIdentity, material: SigningKeyMaterial | None = None) -> None: ...
    # Removes the record together with its key material.
    async def delete(self, identity_id: UUID) -> bool: ...
    # Public part (cert.pem); None when the identity has no certificate.
    async def read_cert(self, identity_id: UUID) -> bytes | None: ...
    # Directory with key.pem + cert.pem for the duration of the block. Local: the real
    # folder, no copy; server: a 0700 temp dir wiped on exit.
    def private_key_session(self, identity_id: UUID) -> AbstractAsyncContextManager[Path]: ...


class IAgentPersonaRepository(Protocol):
    # CRUD over user-defined agent roles (data_dir/agent_personas.json). Dumb
    # persistence layer (mirrors IAIProviderRepository); the use case owns id /
    # created_at generation and validation.
    def list_all(self) -> list[AgentPersona]: ...
    def get(self, persona_id: UUID) -> AgentPersona | None: ...
    def create(self, persona: AgentPersona) -> None: ...
    def update(self, persona: AgentPersona) -> None: ...
    def delete(self, persona_id: UUID) -> bool: ...


class IFilesystemBrowser(Protocol):
    def browse(self, path: Path) -> tuple[Path | None, list[BrowseEntry]]: ...


class IChatRunRepository(Protocol):
    # Background-turn run records: the write side of an agent turn, split from the
    # transcript so a database implementation can back it independently.
    async def get_run(self, project_folder: Path, run_id: UUID) -> AgentRunRecord | None: ...
    async def list_runs(self, project_folder: Path, session_id: UUID) -> list[AgentRunRecord]: ...
    async def save_run(self, record: AgentRunRecord) -> None: ...
    async def list_all_run_ids(self, project_folder: Path) -> list[UUID]: ...  # recovery scan


class IChatRepository(IChatRunRepository, Protocol):
    # Folder-scoped persistence of agent chat sessions, their transcripts, the
    # rolling compaction summaries, and per-turn run records. Mirrors the other
    # per-project repos (e.g. IPackSubmissionRepository): getters take the
    # project folder; the use case resolves project_id → folder. The transcript
    # is append-only (see the JSON impl) so `append_message` assigns and returns
    # the monotonic seq.

    # sessions
    async def list_sessions(self, project_folder: Path) -> list[ChatSession]: ...
    async def get_session(self, project_folder: Path, session_id: UUID) -> ChatSession | None: ...
    async def save_session(self, session: ChatSession) -> None: ...
    async def delete_session(self, project_folder: Path, session_id: UUID) -> bool: ...

    # messages (append-only transcript). project_folder is passed explicitly
    # because a ChatMessage carries only session_id, not its on-disk location.
    async def append_message(self, project_folder: Path, message: ChatMessage) -> int: ...  # returns assigned seq
    async def list_messages(self, project_folder: Path, session_id: UUID) -> list[ChatMessage]: ...
    async def update_message(
        self, project_folder: Path, message: ChatMessage
    ) -> None: ...  # rare: compaction flag only
    # Mark messages with seq <= through_seq as compacted (covered by a summary) in
    # one transcript rewrite; the raw text is kept, only excluded from replay.
    async def mark_compacted(self, project_folder: Path, session_id: UUID, through_seq: int) -> int: ...

    # rolling compaction summaries
    async def list_summaries(self, project_folder: Path, session_id: UUID) -> list[ChatSummaryBlock]: ...
    async def append_summary(self, project_folder: Path, summary: ChatSummaryBlock) -> None: ...
