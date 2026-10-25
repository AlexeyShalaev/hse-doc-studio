from __future__ import annotations


class TemplateUpdateError(Exception):
    """Base for template update failures (a client-visible, localized message)."""


class TemplateVersionUnavailableError(TemplateUpdateError):
    """The target (or current) template version is not available in this Studio."""


class TemplateUpdatePlanOutdatedError(TemplateUpdateError):
    """The project changed since the preview: the plan must be recomputed (HTTP 409)."""


class TemplateUpdateInProgressError(TemplateUpdateError):
    """Another template update of this project is running or was interrupted (HTTP 409)."""


class TemplateUpdateNotRevertibleError(TemplateUpdateError):
    """The update to revert is unknown or is no longer in the project's history."""
