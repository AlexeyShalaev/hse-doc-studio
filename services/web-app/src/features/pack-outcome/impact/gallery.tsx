import type { QueryClient } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import {
  packOutcomeKeys,
  packStudioKeys,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  referenceImpact,
  type ModesBehavior,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import { ImpactBlock } from "./ImpactBlock";

// Состояния блока «Что изменится в результате» без сервера: ответ положен в кэш запросов.

const REF: PackVersionRef = {
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.6",
};

type Seed =
  | { kind: "data"; behavior: ModesBehavior }
  | { kind: "loading" }
  | { kind: "error"; error: ApiError };

const REQUEST = { base: "base", include_atlas: true } as const;

const fail = (
  client: QueryClient,
  key: readonly unknown[],
  error: ApiError,
) => {
  client.getQueryCache().build(client, { queryKey: key }).setState({
    status: "error",
    fetchStatus: "idle",
    data: undefined,
    error,
    errorUpdateCount: 1,
    errorUpdatedAt: Date.now(),
  });
};

const base = (reason: string) =>
  new ApiError("Сравнивать не с чем.", "diff_base_unavailable", 409, {
    reason,
  });

const SPECS: { id: string; title: string; note: string; seed: Seed }[] = [
  {
    id: "po_impact_changed",
    title: "До и после: изменится результат",
    note: "Эталон PackOutcomeImpact/coursework: «в 1 из 3 сценариев», счётчики по разделам, атлас, сценарии со статусами и дифф по раскрытию.",
    seed: { kind: "data", behavior: "normal" },
  },
  {
    id: "po_impact_same",
    title: "До и после: без изменений",
    note: "Все сценарии без изменений: отметка «я знаю» не нужна.",
    seed: { kind: "data", behavior: "impact_same" },
  },
  {
    id: "po_impact_error",
    title: "До и после: сценарий с ошибкой",
    note: "Вводная есть только в новой версии: сценарий раскрыт, сообщение сервера.",
    seed: { kind: "data", behavior: "impact_error" },
  },
  {
    id: "po_impact_atlas_null",
    title: "До и после: атлас слишком большой",
    note: "atlas: null, сравнение только по сценариям.",
    seed: { kind: "data", behavior: "impact_atlas_null" },
  },
  {
    id: "po_impact_empty",
    title: "До и после: сценариев нет",
    note: "Подсказка создать сценарий и ссылка на экран «Результат».",
    seed: { kind: "data", behavior: "impact_empty" },
  },
  {
    id: "po_impact_loading",
    title: "До и после: считаю",
    note: "Скелет, полоса хода и «Отменить расчёт».",
    seed: { kind: "loading" },
  },
  {
    id: "po_impact_no_git",
    title: "До и после: папка без git",
    note: "diff_base_unavailable, причина no_git.",
    seed: { kind: "error", error: base("no_git") },
  },
  {
    id: "po_impact_no_base",
    title: "До и после: базы нет",
    note: "diff_base_unavailable, причина no_base.",
    seed: { kind: "error", error: base("no_base") },
  },
  {
    id: "po_impact_new_version",
    title: "До и после: версия новая",
    note: "diff_base_unavailable, причина new_version.",
    seed: { kind: "error", error: base("new_version") },
  },
  {
    id: "po_impact_busy",
    title: "До и после: сервер занят",
    note: "outcome_busy после трёх повторов: текст и «Повторить».",
    seed: {
      kind: "error",
      error: new ApiError("Занят", "outcome_busy", 503, { retry_after_s: 5 }),
    },
  },
  {
    id: "po_impact_too_large",
    title: "До и после: ответ слишком большой",
    note: "outcome_too_large: куда посмотреть различия.",
    seed: {
      kind: "error",
      error: new ApiError("Большой", "outcome_too_large", 413, {
        limit: 8388608,
        size: 11534336,
      }),
    },
  },
];

export const getImpactGalleryEntries = (): GalleryEntry[] =>
  SPECS.map((spec) => {
    const id = `gallery-${spec.id}`;
    return {
      id: spec.id,
      title: spec.title,
      note: spec.note,
      frame: "page" as const,
      width: 560,
      seed: (client: QueryClient) => {
        client.setQueryData(packStudioKeys.tree(id), {
          workspace_id: id,
          base_sha: null,
          packs: [],
          files: [],
          truncated: false,
        });
        const key = packOutcomeKeys.impact(id, REF, REQUEST);
        if (spec.seed.kind === "data") {
          const data = {
            ...referenceImpact(spec.seed.behavior),
            workspace_id: id,
          };
          client.setQueryData(key, { data, etag: null });
        } else if (spec.seed.kind === "error") {
          fail(client, key, spec.seed.error);
        } else {
          void client.prefetchQuery({
            queryKey: key,
            queryFn: () => new Promise<never>(() => undefined),
          });
        }
      },
      render: () => (
        <MemoryRouter>
          <ImpactBlock
            workspaceId={id}
            versions={[REF]}
            onReport={() => undefined}
          />
        </MemoryRouter>
      ),
    };
  });
