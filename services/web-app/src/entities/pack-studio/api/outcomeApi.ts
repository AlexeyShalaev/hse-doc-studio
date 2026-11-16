import { apiClient, parseResp } from "@shared/api";
import {
  PackOutcomeExplainSchema,
  PackOutcomeInputsSchema,
  PackOutcomeSchema,
  PackScenarioListSchema,
  type OutcomeState,
  type PackOutcome,
  type PackOutcomeExplain,
  type PackOutcomeExplainRequest,
  type PackOutcomeInputs,
  type PackOutcomeRequest,
  type PackScenarioList,
} from "./outcome";
import type { PackVersionRef } from "./packStudioApi";

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

/** Ответ «Почему?» вместе с ETag: следующий запрос того же ключа идёт с `If-None-Match`. */
export type OutcomeExplainReply = {
  data: PackOutcomeExplain;
  etag: string | null;
};

const notModified = (status: number): boolean => status === 304;

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
  /** Сценарии шаблона; битые файлы приходят с `error`. */
  scenarios: (
    id: string,
    pack: string,
    template: string,
    signal?: AbortSignal,
  ): Promise<PackScenarioList> =>
    apiClient
      .get(scenariosBase(id, pack, template), { ...quiet, ...cancel(signal) })
      .then(parseResp(PackScenarioListSchema)),
};
