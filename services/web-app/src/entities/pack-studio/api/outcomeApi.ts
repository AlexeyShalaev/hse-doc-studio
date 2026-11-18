import type { AxiosResponse } from "axios";
import type { ZodType } from "zod";
import { apiClient, parseResp } from "@shared/api";
import {
  PackOutcomeAtlasSchema,
  PackOutcomeCompareSchema,
  PackOutcomeExplainSchema,
  PackOutcomeImpactSchema,
  PackOutcomeInputsSchema,
  PackOutcomeLintSchema,
  PackOutcomeMatrixSchema,
  PackOutcomeSchema,
  PackScenarioEntrySchema,
  PackScenarioListSchema,
  PackScenarioRunSchema,
  type OutcomeState,
  type PackOutcome,
  type PackOutcomeAtlas,
  type PackOutcomeCompare,
  type PackOutcomeCompareRequest,
  type PackOutcomeExplain,
  type PackOutcomeExplainRequest,
  type PackOutcomeImpact,
  type PackOutcomeImpactRequest,
  type PackOutcomeInputs,
  type PackOutcomeLint,
  type PackOutcomeMatrix,
  type PackOutcomeMatrixRequest,
  type PackOutcomeRequest,
  type PackScenarioEntry,
  type PackScenarioList,
  type PackScenarioRun,
  type PackScenarioRunRequest,
  type PackScenarioWriteRequest,
} from "./outcome";
import { rethrowStale, type PackVersionRef } from "./packStudioApi";

// Эндпоинты вычислителя результата (docs/design/template-studio-outcome.md, раздел 4.6):
// /api/v1/pack-studio/workspaces/{id}/versions/{пак}/{шаблон}/{версия}/outcome*. Все только читают:
// POST нужен лишь из-за тела запроса. Клиент ничего не считает, он показывает ответ.

const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

/** Сигнал отмены в настройки запроса: прежний расчёт отменяется, когда вводные сменились. */
const cancel = (signal: AbortSignal | undefined): { signal?: AbortSignal } =>
  signal ? { signal } : {};

const workspace = (id: string) => `/pack-studio/workspaces/${enc(id)}`;

/** Корень адресов результата версии; под ним inputs, explain, atlas и остальное. */
export const outcomeBase = (id: string, ref: PackVersionRef): string =>
  `${workspace(id)}/versions/${enc(ref.pack)}/${enc(ref.template)}/${enc(ref.version)}/outcome`;

export const scenariosBase = (
  id: string,
  pack: string,
  template: string,
): string =>
  `${workspace(id)}/templates/${enc(pack)}/${enc(template)}/scenarios`;

/** Ответ вместе с ETag: следующий запрос того же ключа идёт с `If-None-Match`. */
export type OutcomeReply<T> = { data: T; etag: string | null };

/** Ответ «Почему?» вместе с ETag. */
export type OutcomeExplainReply = OutcomeReply<PackOutcomeExplain>;

const notModified = (status: number): boolean => status === 304;

/** Запрос атласа: источник, набор данных, основа таблицы и закреплённые вводные. */
export type PackOutcomeAtlasRequest = {
  state?: OutcomeState;
  /** Набор данных примера (как у расчёта). */
  example?: string | null;
  /** Сценарий как основа таблицы (вводные сценария вместо умолчаний). */
  scenario?: string | null;
  /** Закреплённые вводные (вводная, значение): режут таблицу, измерение остаётся с одним значением. */
  pin?: Record<string, string>;
};

/** Запрос линтера результата: источник и проверка Jinja-шаблонов (только рабочее дерево, дольше). */
export type PackOutcomeLintRequest = {
  state?: OutcomeState;
  jinja?: boolean;
};

/** Адрес линтера: `jinja=true` ставится только когда Jinja просят. */
export const lintQuery = (request: PackOutcomeLintRequest): string => {
  const params = new URLSearchParams();
  params.set("state", request.state ?? "work_tree");
  if (request.jinja) params.set("jinja", "true");
  return params.toString();
};

/** Адрес атласа: `pin` повторяемый (`pin=kind:research&pin=staffing:team`), в порядке имён. */
export const atlasQuery = (request: PackOutcomeAtlasRequest): string => {
  const params = new URLSearchParams();
  params.set("state", request.state ?? "work_tree");
  if (request.example) params.set("example", request.example);
  if (request.scenario) params.set("scenario", request.scenario);
  for (const [input, value] of Object.entries(request.pin ?? {}).sort(
    ([a], [b]) => (a < b ? -1 : a > b ? 1 : 0),
  )) {
    params.append("pin", `${input}:${value}`);
  }
  return params.toString();
};

/**
 * Разбор ответа с условным запросом: на 304 берётся прежний ответ без разбора тела, иначе тело
 * проходит строгую схему и приходит вместе с ETag.
 */
const settle = <T>(
  schema: ZodType<T>,
  known: OutcomeReply<T> | null | undefined,
  response: AxiosResponse,
): OutcomeReply<T> => {
  if (notModified(response.status) && known) return known;
  const etag: unknown = response.headers.etag;
  return {
    data: parseResp(schema)(response),
    etag: typeof etag === "string" ? etag : null,
  };
};

const conditional = (
  known: OutcomeReply<unknown> | null | undefined,
  signal: AbortSignal | undefined,
) => ({
  ...quiet,
  ...cancel(signal),
  headers: known?.etag ? { "If-None-Match": known.etag } : {},
  validateStatus: (status: number): boolean =>
    (status >= 200 && status < 300) || notModified(status),
});

export const packOutcomeApi = {
  /** Вводные версии: панель строится из них, ни одной вводной в клиенте не прописано. */
  inputs: (
    id: string,
    ref: PackVersionRef,
    state: OutcomeState,
    signal?: AbortSignal,
  ): Promise<PackOutcomeInputs> =>
    apiClient
      .get(`${outcomeBase(id, ref)}/inputs`, {
        ...quiet,
        params: { state },
        ...cancel(signal),
      })
      .then(parseResp(PackOutcomeInputsSchema)),
  /** Расчёт результата и трассы решений для вводных. */
  outcome: (
    id: string,
    ref: PackVersionRef,
    body: PackOutcomeRequest,
    signal?: AbortSignal,
  ): Promise<PackOutcome> =>
    apiClient
      .post(outcomeBase(id, ref), body, { ...quiet, ...cancel(signal) })
      .then(parseResp(PackOutcomeSchema)),
  /**
   * Цепочка решений, соседи и «что если» одного элемента. `known` это прежний ответ на тот же
   * запрос: уходит `If-None-Match`, а на 304 тот же ответ возвращается без разбора тела.
   */
  explain: (
    id: string,
    ref: PackVersionRef,
    body: PackOutcomeExplainRequest,
    known?: OutcomeExplainReply | null,
    signal?: AbortSignal,
  ): Promise<OutcomeExplainReply> =>
    apiClient
      .post(`${outcomeBase(id, ref)}/explain`, body, {
        ...quiet,
        ...cancel(signal),
        headers: known?.etag ? { "If-None-Match": known.etag } : {},
        validateStatus: (status) =>
          (status >= 200 && status < 300) || notModified(status),
      })
      .then((response) => {
        if (notModified(response.status) && known) return known;
        const etag: unknown = response.headers.etag;
        return {
          data: parseResp(PackOutcomeExplainSchema)(response),
          etag: typeof etag === "string" ? etag : null,
        };
      }),
  /** Сценарии шаблона; битые файлы приходят с `error`. `state`: откуда читать файлы (по умолчанию рабочее дерево). */
  scenarios: (
    id: string,
    pack: string,
    template: string,
    signal?: AbortSignal,
    state?: OutcomeState,
  ): Promise<PackScenarioList> =>
    apiClient
      .get(scenariosBase(id, pack, template), {
        ...quiet,
        ...(state && state !== "work_tree" ? { params: { state } } : {}),
        ...cancel(signal),
      })
      .then(parseResp(PackScenarioListSchema)),
  /**
   * Запись сценария каноническим YAML. Без `ifMatch` файла быть не должно (`scenario_taken`);
   * с `ifMatch` (ETag записи) правка; чужая правка даёт PackStaleFileError. «Отменить удаление»
   * это та же запись без `ifMatch` с телом удалённого сценария.
   */
  putScenario: (
    id: string,
    pack: string,
    template: string,
    scenario: string,
    body: PackScenarioWriteRequest,
    ifMatch: string | null,
  ): Promise<PackScenarioEntry> =>
    apiClient
      .put(`${scenariosBase(id, pack, template)}/${enc(scenario)}`, body, {
        ...quiet,
        ...(ifMatch ? { headers: { "If-Match": ifMatch } } : {}),
      })
      .then(parseResp(PackScenarioEntrySchema), rethrowStale),
  /** Мягкое удаление файла (в git он остаётся в истории); `ifMatch`: ETag записи. */
  deleteScenario: (
    id: string,
    pack: string,
    template: string,
    scenario: string,
    ifMatch: string | null,
  ): Promise<void> =>
    apiClient
      .delete(`${scenariosBase(id, pack, template)}/${enc(scenario)}`, {
        ...quiet,
        ...(ifMatch ? { headers: { "If-Match": ifMatch } } : {}),
      })
      .then(
        () => undefined,
        (error: unknown) => rethrowStale(error),
      ),
  /** Прогон утверждений и снимков: `scenarios: null` все, иначе перечисленные (один сценарий тоже). */
  runScenarios: (
    id: string,
    pack: string,
    template: string,
    body: PackScenarioRunRequest,
    signal?: AbortSignal,
  ): Promise<PackScenarioRun> =>
    apiClient
      .post(`${scenariosBase(id, pack, template)}/run`, body, {
        ...quiet,
        ...cancel(signal),
      })
      .then(parseResp(PackScenarioRunSchema)),
  /**
   * Атлас версии: измерения, исходы и таблица `{key, outcome}` (секунды на большой версии).
   * `known`: прежний ответ на тот же запрос (`If-None-Match`, на 304 он же и возвращается).
   * Отказы: `atlas_too_large` 413 (`limit`, `rows`), `outcome_busy` 503 (`retry_after_s`).
   */
  atlas: (
    id: string,
    ref: PackVersionRef,
    request: PackOutcomeAtlasRequest,
    known?: OutcomeReply<PackOutcomeAtlas> | null,
    signal?: AbortSignal,
  ): Promise<OutcomeReply<PackOutcomeAtlas>> =>
    apiClient
      .get(
        `${outcomeBase(id, ref)}/atlas?${atlasQuery(request)}`,
        conditional(known, signal),
      )
      .then((response) => settle(PackOutcomeAtlasSchema, known, response)),
  /**
   * Линтер результата: находки по правилам версии и атласа, покрытие правил сценариями.
   * `jinja: true` добавляет рендер шаблонов (рабочее дерево, дольше, лимит 6 в минуту).
   * Отказы: `outcome_busy` 503, `rate_limited` 429 (`retry_after`), `version_unreadable`,
   * `diff_base_unavailable` (состояние `base` без базы).
   */
  lint: (
    id: string,
    ref: PackVersionRef,
    request: PackOutcomeLintRequest,
    known?: OutcomeReply<PackOutcomeLint> | null,
    signal?: AbortSignal,
  ): Promise<OutcomeReply<PackOutcomeLint>> =>
    apiClient
      .get(
        `${outcomeBase(id, ref)}/lint?${lintQuery(request)}`,
        conditional(known, signal),
      )
      .then((response) => settle(PackOutcomeLintSchema, known, response)),
  /**
   * Сравнение двух сторон (состояние, сценарий, набор данных, вводные): изменения `+`, `~`, `-` по
   * разделам с причинами `why`. Отказы: `diff_base_unavailable` 409 (`reason`), `inputs_invalid`.
   */
  compare: (
    id: string,
    ref: PackVersionRef,
    body: PackOutcomeCompareRequest,
    known?: OutcomeReply<PackOutcomeCompare> | null,
    signal?: AbortSignal,
  ): Promise<OutcomeReply<PackOutcomeCompare>> =>
    apiClient
      .post(`${outcomeBase(id, ref)}/compare`, body, conditional(known, signal))
      .then((response) => settle(PackOutcomeCompareSchema, known, response)),
  /**
   * «До и после»: рабочее дерево против базы по сценариям шаблона и атласу. Отказы:
   * `diff_base_unavailable` 409, `outcome_too_large` 413 (`limit`, `size`), `outcome_busy`.
   */
  impact: (
    id: string,
    ref: PackVersionRef,
    body: PackOutcomeImpactRequest,
    known?: OutcomeReply<PackOutcomeImpact> | null,
    signal?: AbortSignal,
  ): Promise<OutcomeReply<PackOutcomeImpact>> =>
    apiClient
      .post(`${outcomeBase(id, ref)}/impact`, body, conditional(known, signal))
      .then((response) => settle(PackOutcomeImpactSchema, known, response)),
  /**
   * Матрица «сценарии на разделы»: статус, отпечаток и счётчик клетки. Отказы: `outcome_too_large`
   * 413, `diff_base_unavailable` 409 (при `against: base`), `outcome_busy`.
   */
  matrix: (
    id: string,
    ref: PackVersionRef,
    body: PackOutcomeMatrixRequest,
    known?: OutcomeReply<PackOutcomeMatrix> | null,
    signal?: AbortSignal,
  ): Promise<OutcomeReply<PackOutcomeMatrix>> =>
    apiClient
      .post(`${outcomeBase(id, ref)}/matrix`, body, conditional(known, signal))
      .then((response) => settle(PackOutcomeMatrixSchema, known, response)),
};
