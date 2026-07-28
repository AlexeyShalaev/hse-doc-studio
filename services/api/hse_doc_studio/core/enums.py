from __future__ import annotations

from enum import StrEnum


class ProjectKind(StrEnum):
    research = "research"
    project = "project"


class ProjectStaffing(StrEnum):
    solo = "solo"
    team = "team"


class Lang(StrEnum):
    ru = "ru"
    en = "en"


class EngineType(StrEnum):
    xelatex = "xelatex"
    lualatex = "lualatex"
    pdflatex = "pdflatex"


class DocumentStatus(StrEnum):
    draft = "draft"
    building = "building"
    ok = "ok"
    warn = "warn"
    err = "err"
    locked = "locked"


class CompileStatus(StrEnum):
    pending = "pending"
    running = "running"
    success = "success"
    failure = "failure"
    cancelled = "cancelled"


class CheckSeverity(StrEnum):
    info = "info"
    warn = "warn"
    err = "err"
    # Synthetic, runtime-only: a rule an engine can't evaluate against a custom
    # (non-template) document — never counted as an error/warning anywhere
    # aggregation happens (see CheckRunner.run_all custom_mode suppression).
    skipped = "skipped"


class CheckEngine(StrEnum):
    regex = "regex"
    structural = "structural"
    log_parse = "log_parse"
    external = "external"
    file_exists = "file_exists"
    tex_command_count = "tex_command_count"
    python = "python"
    reference_check = "reference_check"
    typography = "typography"


class TemplateVersionStatus(StrEnum):
    stable = "stable"
    beta = "beta"
    deprecated = "deprecated"


class MetaFieldType(StrEnum):
    string = "string"
    bool_ = "bool"
    person = "person"
    select = "select"
    # A font family choice (main/sans/mono). Behaves like a textual field (gets a
    # `default`, stored in project.meta as a family-name string) but the UI
    # renders a font picker with previews instead of a plain input.
    font = "font"


class FormFieldType(StrEnum):
    # Field kinds the generic, pack-driven form engine can render. Kept
    # deliberately minimal — every kind maps to one frontend renderer and one
    # answer value shape (see core.catalog.FormFieldDef / core.value_objects):
    #   bool        -> bool                         markdown -> no answer (display only)
    #   text        -> str                          select   -> str (option id)
    #   textarea    -> str                          multiselect -> list[str] (option ids)
    #   number      -> int | float                  table    -> list[dict[str, str]] (column id -> cell)
    bool_ = "bool"
    text = "text"
    textarea = "textarea"
    number = "number"
    select = "select"
    multiselect = "multiselect"
    table = "table"
    markdown = "markdown"


class RequiredAt(StrEnum):
    create = "create"
    finalize = "finalize"
    never = "never"


class MetaFieldAuto(StrEnum):
    # Dynamic default for a meta field, computed at project-creation time when the
    # user leaves the field blank (see core.meta_defaults). Distinct from the
    # static `default` literal — `auto` derives the value from "now".
    #   academic_year -> end year of the current HSE academic year (the defense
    #                    year): Sep..Dec -> next calendar year, Jan..Aug -> this one.
    academic_year = "academic_year"


class PersonRole(StrEnum):
    university = "university"
    company = "company"


class RequirementFormatKind(StrEnum):
    # How requirement definitions/references are detected in .tex sources.
    macro = "macro"  # \req{ID}{text} + \reqref{ID} (default)
    id = "id"  # bare ID regex; definitions live in designated documents
    custom = "custom"  # user-supplied def/ref regexes


class ChangeLogKind(StrEnum):
    compile_ok = "compile_ok"
    compile_fail = "compile_fail"
    edit = "edit"
    manual_note = "manual_note"
    sign = "sign"
    pack_submission = "pack_submission"


class VcsCommitKind(StrEnum):
    # Why a ProjectVCS snapshot was taken. `compile` mirrors ChangeLogKind.compile_ok
    # (a successful build); kept distinct from the overloaded word "build". Detected
    # from the commit's `Hse-Kind:` trailer, not by parsing the subject.
    init = "init"
    edit = "edit"
    compile = "compile"
    manual = "manual"
    restore = "restore"


class VcsChange(StrEnum):
    # git name-status change classes (first letter of the status code).
    added = "A"
    modified = "M"
    deleted = "D"
    renamed = "R"
    copied = "C"


class VcsTagKind(StrEnum):
    # A lightweight git tag is a plain bookmark ("tag"); an annotated tag (with a
    # message) is treated as a "release" milestone. No "checkpoint" — that word is
    # reserved for submission packaging.
    tag = "tag"
    release = "release"


class VcsRestoreMode(StrEnum):
    # snapshot = safe default: the working tree is reset to the target commit and a
    # new `restore` commit records it — HEAD/history are never rewritten, so it is
    # fully undoable. hard = destructive `git reset --hard` (UI-only, behind an
    # explicit confirm; never exposed to the agent).
    snapshot = "snapshot"
    hard = "hard"


class SigningIdentityKind(StrEnum):
    # How the private key is accessed at signing time.
    self_signed = "self_signed"  # generated in-app, key stored locally (data_dir)
    pkcs12 = "pkcs12"  # imported .p12/.pfx bundle, key stored locally
    pkcs11 = "pkcs11"  # hardware token / smartcard via PKCS#11 library


class SignMode(StrEnum):
    # What cryptographic treatment is applied when producing the signed PDF.
    image = "image"  # default: current PNG-overlay only, no crypto
    image_crypto = "image_crypto"  # PNG appearance + embedded PAdES signature
    crypto_invisible = "crypto_invisible"  # PAdES only, no visible appearance
    detached = "detached"  # produce a separate .sig (CAdES detached)


class AIProviderType(StrEnum):
    # `claude` routes to the Anthropic SDK; `openai`, `openai_compat` and
    # `ollama` all route to the OpenAI SDK. `openai` hides base_url (defaults to
    # api.openai.com); `openai_compat` surfaces it for any compatible endpoint
    # (vLLM, LM Studio, OpenRouter, …); `ollama` is the SAME OpenAI-compatible
    # path but is auto-managed by the local runtime (base_url + models are kept
    # in sync by the backend, no api_key) and rendered read-only in the UI.
    claude = "claude"
    openai = "openai"
    openai_compat = "openai_compat"
    ollama = "ollama"


class GpuVendor(StrEnum):
    # Detected accelerator family, used to size local-model recommendations.
    nvidia = "nvidia"
    apple = "apple"  # Apple Silicon (Metal, unified memory)
    amd = "amd"
    none = "none"  # no usable GPU detected → CPU-only inference


class OllamaRuntimeMode(StrEnum):
    # How the local Ollama runtime is currently reachable.
    native = "native"  # a user-run Ollama already listening (best GPU on every OS)
    docker = "docker"  # our backend-managed `ollama/ollama` container
    none = "none"  # nothing serving yet (installable: native binary or container)


# ── AI agent chat ────────────────────────────────────────────────────────────


class ToolKind(StrEnum):
    # Permission class of an agent tool. `read` tools auto-run; `write`/`exec`
    # (`exec_` to avoid shadowing the builtin) are gated by the approval gate;
    # `ask` pauses the run for structured user input instead of executing.
    read = "read"
    write = "write"
    exec_ = "exec"
    ask = "ask"


class ApiShape(StrEnum):
    # The two request/response shapes the agent provider normalizes over.
    openai = "openai"  # provider types openai | openai_compat | ollama
    anthropic = "anthropic"  # provider type claude


class StopReason(StrEnum):
    # Why a model round-trip ended (normalized across providers).
    tool_calls = "tool_calls"  # model wants tools run → loop continues
    end_turn = "end_turn"  # final answer, no tools → loop stops
    max_tokens = "max_tokens"
    error = "error"
    cancelled = "cancelled"


class EditFormat(StrEnum):
    # How edit_tex expects the model to express a change. Picked per model.
    search_replace = "search_replace"  # high-level diff blocks (strong models)
    whole_file = "whole_file"  # full updated file (weak/local models)


class ChatMessageRole(StrEnum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"
    summary = "summary"  # a compaction summary standing in for older turns


class ChatContentKind(StrEnum):
    text = "text"
    tool_call = "tool_call"
    tool_result = "tool_result"


class AgentRunStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    interrupted = "interrupted"  # server restarted/crashed mid-run (recovery)
    awaiting_approval = "awaiting_approval"  # paused for a write/exec tool the user must approve


class ToolApprovalDecision(StrEnum):
    auto = "auto"  # read tool, ran without asking
    approved = "approved"
    rejected = "rejected"
    pending = "pending"  # awaiting the user's decision


class AgentEventType(StrEnum):
    # The SSE event taxonomy streamed to the client during a run.
    token = "token"  # noqa: S105 — SSE event name (assistant text delta), not a secret
    message = "message"  # a completed persisted message
    tool_call = "tool_call"
    tool_result = "tool_result"
    iteration = "iteration"
    usage = "usage"
    compaction = "compaction"
    approval_required = "approval_required"
    question_required = "question_required"  # run paused for structured user answers
    done = "done"
    error = "error"
