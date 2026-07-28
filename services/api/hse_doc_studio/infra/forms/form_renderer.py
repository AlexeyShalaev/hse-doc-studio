from __future__ import annotations

from typing import Any

import structlog
from jinja2 import ChainableUndefined, Environment, TemplateSyntaxError, UndefinedError

logger = structlog.get_logger()


class FormOutputRenderer:
    """Renders a form's output template (Jinja over project + answers) to text.

    Uses ChainableUndefined so missing placeholders render as empty strings
    instead of leaking raw ``{{ ... }}`` — the same behavior as the project-init
    TemplateRenderer. On any render error the raw template is returned verbatim
    so the user sees something rather than nothing.
    """

    def render(self, template_text: str, context: dict[str, Any]) -> str:
        try:
            env = Environment(undefined=ChainableUndefined, keep_trailing_newline=True)  # noqa: S701
            return env.from_string(template_text).render(**context)
        except (TemplateSyntaxError, UndefinedError) as exc:
            logger.warning("form output template error, returning as-is", exc=str(exc))
            return template_text
        except Exception as exc:
            logger.warning("form output render error, returning as-is", exc=str(exc))
            return template_text
