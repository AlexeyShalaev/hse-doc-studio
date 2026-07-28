from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.agent.entities import ToolSpec
from hse_doc_studio.core.agent.protocols import IToolHandler
from hse_doc_studio.core.enums import ToolKind


@dataclass(frozen=True)
class ToolDefinition:
    # One entry in the tool registry: the schema advertised to the model, its
    # permission class (read auto-runs; write/exec gated by IApprovalGate), the
    # handler that executes it, and whether it is safe to expose to weak/local
    # models (the reduced catalog drops the rest).
    spec: ToolSpec
    kind: ToolKind
    handler: IToolHandler
    weak_model_safe: bool = True
    # Needs a project in context (ctx.project_id). App/system tools (theme,
    # engine, create_project, list_projects/templates, ask_user) set this False
    # so the unified agent can use them outside any project.
    requires_project: bool = True
