from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.infra.pdf.extract import extract_pdf_text
from hse_doc_studio.use_cases.files.get_file import GetFileInput, GetFileUC

_DEFAULT_MAX_CHARS = 8000

_SPEC = ToolSpec(
    name="read_pdf",
    description=(
        "Прочитать текст из СОБРАННОГО PDF документа — увидеть итоговую вёрстку: число "
        "страниц и реальный текст после компиляции. `path` — путь к .pdf, напр. vkr/vkr.pdf "
        "(сначала собери документ). `pages` — необязательный диапазон, напр. '1-3', '5' или "
        "'1,4,7'. Полезно для проверки оформления, переполнений и положения объектов."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Путь к .pdf относительно корня проекта"},
            "pages": {"type": "string", "description": "Диапазон страниц: '1-3', '5' или '1,4,7'"},
            "max_chars": {"type": "integer", "description": "Максимум символов", "default": _DEFAULT_MAX_CHARS},
        },
        "required": ["path"],
    },
)


class ReadPdfTool:
    def __init__(self, get_file_uc: GetFileUC) -> None:
        self._get_file = get_file_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        path = str(args.get("path", "")).strip()
        if not path:
            return ToolResult.error("specify the path parameter" if lang == Lang.en else "укажите параметр path")
        if not path.lower().endswith(".pdf"):
            return ToolResult.error(
                "read_pdf reads only .pdf; use read_tex for .tex"
                if lang == Lang.en
                else "read_pdf читает только .pdf; для .tex используй read_tex"
            )
        try:
            out = await self._get_file.execute(GetFileInput(project_id=ctx.project_id, path=path))
        except FileNotFoundError:
            return ToolResult.error(
                f"PDF not found: {path} — compile the document first (compile_document)"
                if lang == Lang.en
                else f"PDF не найден: {path} — сначала собери документ (compile_document)"
            )
        except Exception as exc:  # noqa: BLE001 — clean message to the model, never crash the loop
            return ToolResult.error(
                f"could not read {path}: {type(exc).__name__}"
                if lang == Lang.en
                else f"не удалось прочитать {path}: {type(exc).__name__}"
            )

        pages = _parse_pages(args.get("pages"))
        max_chars = max(500, _as_int(args.get("max_chars"), _DEFAULT_MAX_CHARS))
        try:
            text, total = extract_pdf_text(out.content, pages=pages, max_chars=max_chars)
        except Exception:  # noqa: BLE001 — corrupt / non-PDF bytes
            return ToolResult.error(
                f"could not parse PDF {path} (corrupt or not a PDF)"
                if lang == Lang.en
                else f"не удалось разобрать PDF {path} (повреждён или не PDF)"
            )

        empty_note = (
            "(no text extracted from the PDF — it may be a scan/images)"
            if lang == Lang.en
            else "(в PDF не извлёкся текст — возможно, это скан/картинки)"
        )
        body = text or empty_note
        # extract_pdf_text emits the marker in the interface language; recognise both.
        truncated = "[... обрезано]" in body or "[... truncated]" in body
        header = f"{path} — {total} p." if lang == Lang.en else f"{path} — {total} стр."
        return ToolResult.ok(f"{header}\n\n{body}", truncated=truncated)


def _parse_pages(value: object) -> list[int] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    result: list[int] = []
    for part in value.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            if lo.isdigit() and hi.isdigit():
                result.extend(range(int(lo), int(hi) + 1))
        elif part.isdigit():
            result.append(int(part))
    return result or None


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default
