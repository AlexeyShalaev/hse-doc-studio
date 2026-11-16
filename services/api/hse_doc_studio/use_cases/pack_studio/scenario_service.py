"""Сценарии Студии шаблонов: список, запись, удаление и прогон (template-studio-outcome.md, разделы 4.6 и 5, срез O6).

Сценарий это файл `<пак>/templates/<шаблон>/scenarios/<id>.yaml` рядом с `examples/`, вне каталога версии.

- **Запись.** Единственный побочный эффект среза: файл сценария (R15). Пишется канонический YAML (одинаковый сценарий
  всегда даёт одинаковые байты) обычным путём записи файлов пространства (`PackFilesService.put`): та же защита
  путей, замок пространства и ETag файла. Без `If-Match` файла быть не должно (`scenario_taken`), с `If-Match` он
  должен быть и совпасть по версии (`stale_file`, `scenario_not_found`). `record_snapshot` кладёт в `snapshot`
  текущий результат сценария на выбранном состоянии версии.
- **Удаление мягкое**: удаляется файл, в git он остаётся в истории и возвращается правкой (ответом «Отменить» клиент
  пишет сценарий заново без `If-Match`).
- **Прогон.** Сценарии шаблона на одной версии (старшая на диске, если не названа) и состоянии (`work_tree`, `head`,
  `base`; сценарии читаются из того же состояния): результат по вводным сценария, сравнение с утверждениями и снимком,
  статусы, покрытие правил. Расчёт идёт в пуле и под пределом времени результата (`PackOutcomeService`), ответ
  кэшируется по ключу с дайджестами файлов сценариев и несёт ETag (304 по `If-None-Match`).
- **Ничего, кроме записи файла сценария**: ни писем, ни подписей, ни приглашений, ни сборок.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.file_version import file_etag
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.model import Digest
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.outcome.scenarios import (
    MAX_SCENARIOS,
    SCENARIO_SUFFIX,
    SCENARIOS_DIR,
    Scenario,
    ScenarioError,
    check_scenario_id,
    parse_scenario,
    scenario_file_name,
    scenario_from_data,
    scenario_text,
    version_matches,
)
from hse_doc_studio.core.pack_studio.outcome.serving import LruCache, etag_matches, etag_of, request_key
from hse_doc_studio.core.pack_studio.paths import TEMPLATES_DIR
from hse_doc_studio.core.pack_studio.protocols import IPackWorkspaceFiles
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService
from hse_doc_studio.use_cases.pack_studio.outcome.scenario_runner import (
    ScenarioRunError,
    resolve_scenario,
    run_scenarios,
)
from hse_doc_studio.use_cases.pack_studio.outcome_service import (
    SCENARIO_MAX_BYTES,
    OutcomeReply,
    OutcomeState,
    PackOutcomeService,
)
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

_RUN_CACHE_ENTRIES = 64


@dataclass(frozen=True)
class ScenarioEntry:
    """Сценарий в списке: файл, ETag и разобранное содержимое; `scenario` None у файла, который не разобран."""

    id: str
    path: str
    etag: str
    scenario: Scenario | None
    error: str | None


@dataclass(frozen=True)
class ScenarioListing:
    workspace_id: UUID
    pack: str
    template: str
    dir: str
    entries: tuple[ScenarioEntry, ...]


def scenario_dir(pack: str, template: str) -> str:
    return f"{pack}/{TEMPLATES_DIR}/{template}/{SCENARIOS_DIR}"


def _invalid(reason: str, scenario: str | None = None) -> PackStudioError:
    if scenario is None:
        return PackStudioError(PackStudioErrorCode.scenario_invalid, reason=reason)
    return PackStudioError(PackStudioErrorCode.scenario_invalid, reason=reason, scenario=scenario)


def _entry(pack: str, template: str, stem: str, data: bytes) -> ScenarioEntry:
    path = f"{scenario_dir(pack, template)}/{stem}{SCENARIO_SUFFIX}"
    etag = file_etag(data)
    try:
        check_scenario_id(stem)
        scenario = parse_scenario(data.decode("utf-8"))
    except ScenarioError as exc:
        return ScenarioEntry(stem, path, etag, None, exc.reason)
    except UnicodeDecodeError:
        return ScenarioEntry(stem, path, etag, None, "the file is not UTF-8")
    return ScenarioEntry(stem, path, etag, scenario, None)


def _entries(pack: str, template: str, files: Mapping[str, bytes]) -> tuple[ScenarioEntry, ...]:
    """Файлы `*.yaml` папки сценариев по id; остальное в папке сценарием не считается."""
    names = sorted(name for name in files if name.endswith(SCENARIO_SUFFIX))
    return tuple(
        _entry(pack, template, name.removesuffix(SCENARIO_SUFFIX), files[name]) for name in names[:MAX_SCENARIOS]
    )


def _digest_of(files: Mapping[str, bytes], names: list[str]) -> dict[str, str]:
    return {name: hashlib.sha256(files[name]).hexdigest()[:16] for name in names}


class PackScenarioService:
    """Один на процесс: держит кэш прогонов; расчёт и чтение состояний версии у `PackOutcomeService`."""

    def __init__(
        self,
        outcome: PackOutcomeService,
        files: PackFilesService,
        workspaces: PackWorkspaceService,
        port: IPackWorkspaceFiles,
        *,
        cache_entries: int = _RUN_CACHE_ENTRIES,
    ) -> None:
        self._outcome = outcome
        self._files = files
        self._workspaces = workspaces
        self._port = port
        self._runs: LruCache[dict[str, Any]] = LruCache(cache_entries)

    # ── список, запись, удаление ─────────────────────────────────────────────

    async def list_scenarios(
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, state: OutcomeState = "work_tree"
    ) -> ScenarioListing:
        """Сценарии шаблона; битый файл виден с `error`. `head` и `base` читают коммит."""
        ws, files = await self._outcome.read_scenarios(actor, workspace_id, pack, template, state)
        return ScenarioListing(ws.id, pack, template, scenario_dir(pack, template), _entries(pack, template, files))

    async def put(  # noqa: PLR0913 — путь сценария, тело, снимок и условие записи
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        scenario_id: str,
        data: Mapping[str, Any],
        *,
        if_match: str | None,
        record_snapshot: OutcomeState | None = None,
        version: str | None = None,
    ) -> ScenarioEntry:
        """Запись сценария каноническим YAML. Формат проверяется здесь, допустимость вводных относительно версии при
        прогоне (сценарий переживает версии)."""
        path = self._path(pack, template, scenario_id)
        scenario = self._parse(data, scenario_id)
        _, root = await self._workspaces.ready(actor, workspace_id)
        if not await asyncio.to_thread(self._port.is_dir, root, f"{pack}/{TEMPLATES_DIR}/{template}"):
            raise PackStudioError(PackStudioErrorCode.version_not_found, version="")
        if if_match is None:
            await self._check_room(actor, workspace_id, pack, template)
        if record_snapshot is not None:
            scenario = replace(
                scenario,
                snapshot=await self._record(actor, workspace_id, pack, template, scenario, record_snapshot, version),
            )
        content = scenario_text(scenario).encode("utf-8")
        if len(content) > SCENARIO_MAX_BYTES:
            raise PackStudioError(PackStudioErrorCode.file_too_large, limit=SCENARIO_MAX_BYTES)
        written = await self._files.put(
            actor,
            workspace_id,
            path,
            content,
            if_match,
            taken=PackStudioError(PackStudioErrorCode.scenario_taken, scenario=scenario_id),
            missing=PackStudioError(PackStudioErrorCode.scenario_not_found, scenario=scenario_id),
        )
        return ScenarioEntry(scenario_id, path, written.etag, parse_scenario(content.decode("utf-8")), None)

    async def delete(
        self, actor: Actor, workspace_id: UUID, pack: str, template: str, scenario_id: str, *, if_match: str | None
    ) -> None:
        """Удаление файла сценария (в git он остаётся в истории). Нет файла: `scenario_not_found`."""
        path = self._path(pack, template, scenario_id)
        try:
            await self._files.read(actor, workspace_id, path)
        except PackStudioError as exc:
            if exc.code is PackStudioErrorCode.file_not_found:
                raise PackStudioError(PackStudioErrorCode.scenario_not_found, scenario=scenario_id) from None
            raise
        await self._files.delete(actor, workspace_id, path, if_match)

    # ── прогон ───────────────────────────────────────────────────────────────

    async def run(  # noqa: PLR0913 — путь шаблона, состояние, выбор сценариев и версии
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        *,
        state: OutcomeState = "work_tree",
        scenarios: list[str] | None = None,
        version: str | None = None,
        if_none_match: str | None = None,
    ) -> OutcomeReply:
        """Прогон сценариев шаблона на версии (`PackScenarioRun`). `scenarios` None: все. Сценарий, которого нет:
        `scenario_not_found`; вне `versions` на этой версии: `unchecked` с пояснением."""
        ctx = await self._outcome.scenario_context(actor, workspace_id, pack, template, state, version)
        files = ctx.source.scenarios
        selected = self._select(files, scenarios)
        key = request_key(
            {
                "kind": "scenario-run",
                "workspace": str(ctx.ws.id),
                "version": ctx.ref.dir,
                "state": state,
                "source": ctx.source.token,
                "revision": ctx.revision,
                "today": ctx.today.isoformat(),
                "scenarios": _digest_of(files, selected),
            }
        )
        etag = etag_of(key)
        if etag_matches(if_none_match, etag):
            return OutcomeReply(etag, None)
        cached = self._runs.get(key)
        if cached is not None:
            return OutcomeReply(etag, cached)
        parsed: dict[str, Scenario | str] = {}
        for name in selected:
            entry = _entry(pack, template, name.removesuffix(SCENARIO_SUFFIX), files[name])
            parsed[entry.id] = entry.scenario if entry.scenario is not None else (entry.error or "unreadable")
        model, examples, today = ctx.source.desc.version, ctx.examples, ctx.today
        run = await self._outcome.compute(lambda: run_scenarios(model, examples, parsed, today))
        body: dict[str, Any] = {
            "workspace_id": str(ctx.ws.id),
            "pack": ctx.ref.pack,
            "template": ctx.ref.template,
            "version": ctx.ref.version,
            "state": state,
            "revision": ctx.revision,
            **to_json(run),
        }
        self._runs.put(key, body, cost=0)
        return OutcomeReply(etag, body)

    @staticmethod
    def _select(files: Mapping[str, bytes], wanted: list[str] | None) -> list[str]:
        """Имена файлов сценариев для прогона по порядку id; неизвестный id это `scenario_not_found`."""
        names = sorted(name for name in files if name.endswith(SCENARIO_SUFFIX))
        if wanted is None:
            return names[:MAX_SCENARIOS]
        known = {name.removesuffix(SCENARIO_SUFFIX): name for name in names}
        for scenario_id in wanted:
            if scenario_id not in known:
                raise PackStudioError(PackStudioErrorCode.scenario_not_found, scenario=scenario_id)
        return sorted({known[scenario_id] for scenario_id in wanted})

    # ── внутреннее ───────────────────────────────────────────────────────────

    @staticmethod
    def _path(pack: str, template: str, scenario_id: str) -> str:
        try:
            name = scenario_file_name(scenario_id)
        except ScenarioError as exc:
            raise _invalid(exc.reason) from None
        return f"{scenario_dir(pack, template)}/{name}"

    @staticmethod
    def _parse(data: Mapping[str, Any], scenario_id: str) -> Scenario:
        try:
            return scenario_from_data(data)
        except ScenarioError as exc:
            raise _invalid(exc.reason, scenario_id) from None

    async def _check_room(self, actor: Actor, workspace_id: UUID, pack: str, template: str) -> None:
        _, files = await self._outcome.read_scenarios(actor, workspace_id, pack, template, "work_tree")
        if sum(1 for name in files if name.endswith(SCENARIO_SUFFIX)) >= MAX_SCENARIOS:
            raise _invalid(f"too many scenarios in the template (limit {MAX_SCENARIOS})")

    async def _record(  # noqa: PLR0913 — путь шаблона, сценарий, состояние и версия
        self,
        actor: Actor,
        workspace_id: UUID,
        pack: str,
        template: str,
        scenario: Scenario,
        state: OutcomeState,
        version: str | None,
    ) -> Digest:
        """Снимок: сжатый результат сценария на версии и состоянии (`record_snapshot`)."""
        if version is not None and not version_matches(scenario.versions, version):
            raise _invalid(f"version {version} is outside versions: {', '.join(scenario.versions)}")
        ctx = await self._outcome.scenario_context(
            actor, workspace_id, pack, template, state, version, scenario.versions
        )
        model, examples, today = ctx.source.desc.version, ctx.examples, ctx.today

        def work() -> Digest | ScenarioRunError:
            try:
                return resolve_scenario(model, examples, scenario, today, trace=False).digest
            except ScenarioRunError as exc:
                return exc

        recorded = await self._outcome.compute(work)
        if isinstance(recorded, ScenarioRunError):
            raise _invalid(str(recorded))
        return recorded


__all__ = ["PackScenarioService", "ScenarioEntry", "ScenarioListing", "scenario_dir"]
