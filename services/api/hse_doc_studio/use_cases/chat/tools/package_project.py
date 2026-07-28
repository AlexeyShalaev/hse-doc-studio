from __future__ import annotations

from collections.abc import Sequence

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.catalog import SubmissionProfile
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.submission.create_submission import CreateSubmissionInput, CreateSubmissionUC
from hse_doc_studio.use_cases.submission.get_submission_profiles import (
    GetSubmissionProfilesInput,
    GetSubmissionProfilesUC,
)

_SPEC = ToolSpec(
    name="package_project",
    description=(
        "Собрать комплект документов проекта в архив (упаковка по профилю сдачи). "
        "Если профиль не указан и он единственный — берётся он; если профилей несколько, "
        "инструмент вернёт список — выбери и повтори с profile_id."
    ),
    parameters={
        "type": "object",
        "properties": {
            "profile_id": {
                "type": "string",
                "description": "Идентификатор профиля сдачи (необязательно, если профиль один)",
            }
        },
    },
)


def _profiles_text(profiles: Sequence[SubmissionProfile], lang: Lang) -> str:
    primary = "en" if lang == Lang.en else "ru"
    secondary = "ru" if lang == Lang.en else "en"
    return ", ".join(f"{p.id} ({p.name.get(primary) or p.name.get(secondary) or p.id})" for p in profiles)


def _pick_profile(
    raw_profile: object, profiles: Sequence[SubmissionProfile], lang: Lang
) -> tuple[str, ToolResult | None]:
    """Resolve the profile id from tool args. Returns (id, early_result): when
    early_result is set, return it (ask-to-choose or not-found); otherwise id is valid.
    """
    # null / "none" / "null" / empty all mean "not provided".
    profile_id = "" if raw_profile is None else str(raw_profile).strip()
    if profile_id.lower() in {"none", "null"}:
        profile_id = ""
    if not profile_id:
        if len(profiles) == 1:
            return profiles[0].id, None
        listing = _profiles_text(profiles, lang)
        return "", ToolResult.ok(
            "no submission profile specified — pick one and call again with profile_id. Available: " + listing
            if lang == Lang.en
            else "не указан профиль сдачи — выбери один и вызови снова с profile_id. Доступные: " + listing
        )
    if profile_id not in {p.id for p in profiles}:
        listing = _profiles_text(profiles, lang)
        return "", ToolResult.error(
            f"profile «{profile_id}» not found. Available: " + listing
            if lang == Lang.en
            else f"профиль «{profile_id}» не найден. Доступные: " + listing
        )
    return profile_id, None


class PackageProjectTool:
    def __init__(
        self,
        create_submission_uc: CreateSubmissionUC,
        get_submission_profiles_uc: GetSubmissionProfilesUC,
    ) -> None:
        self._create = create_submission_uc
        self._get_profiles = get_submission_profiles_uc

    def definition(self) -> ToolDefinition:
        # Heavy, side-effecting (writes an archive), so exec + approval-gated.
        return ToolDefinition(spec=_SPEC, kind=ToolKind.exec_, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        try:
            profiles_out = await self._get_profiles.execute(GetSubmissionProfilesInput(project_id=ctx.project_id))
        except (ValueError, NotFoundError) as exc:
            return ToolResult.error(str(exc))
        profiles = profiles_out.profiles
        if not profiles:
            return ToolResult.error(
                "the project template has no submission profiles"
                if lang == Lang.en
                else "в шаблоне проекта нет профилей сдачи"
            )

        profile_id, early = _pick_profile(args.get("profile_id"), profiles, lang)
        if early is not None:
            return early

        try:
            out = await self._create.execute(
                CreateSubmissionInput(
                    project_id=ctx.project_id,
                    profile_id=profile_id,
                    items=[],
                    extra_items=[],
                    archive_format="zip",
                )
            )
        except (ValueError, NotFoundError) as exc:
            return ToolResult.error(str(exc))
        archive = out.submission.output_path.name
        return ToolResult.ok(
            f"package assembled for profile «{profile_id}»: archive {archive}"
            if lang == Lang.en
            else f"комплект собран по профилю «{profile_id}»: архив {archive}"
        )
