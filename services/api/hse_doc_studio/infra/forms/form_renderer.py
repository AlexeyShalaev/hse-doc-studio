from __future__ import annotations

from typing import Any

import structlog
from jinja2 import TemplateSyntaxError, UndefinedError
from jinja2.exceptions import SecurityError

from hse_doc_studio.infra.template.jinja_sandbox import form_environment

logger = structlog.get_logger()


class FormOutputRenderer:
    """Renders a form's output template (Jinja over project + answers) to text.

    Uses ChainableUndefined so missing placeholders render as empty strings
    instead of leaking raw ``{{ ... }}`` — the same behavior as the project-init
    TemplateRenderer. On any render error the raw template is returned verbatim
    so the user sees something rather than nothing.

    Шаблон вывода приходит из пака, поэтому рендер идёт в песочнице
    (`jinja_sandbox.form_environment`) с её белым списком атрибутов и пределами.
    """

    def render(self, template_text: str, context: dict[str, Any]) -> str:
        try:
            return form_environment().render_source(template_text, context)
        except SecurityError as exc:
            logger.warning("form output template violates the sandbox, returning as-is", exc=str(exc))
            return template_text
        except (TemplateSyntaxError, UndefinedError) as exc:
            logger.warning("form output template error, returning as-is", exc=str(exc))
            return template_text
        except Exception as exc:
            logger.warning("form output render error, returning as-is", exc=str(exc))
            return template_text
