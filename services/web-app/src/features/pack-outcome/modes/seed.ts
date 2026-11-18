import type { QueryClient } from "@tanstack/react-query";
import {
  packOutcomeKeys,
  type PackOutcomeAtlas,
  type PackOutcomeCompare,
  type PackOutcomeLint,
  type PackOutcomeMatrix,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  COURSEWORK_ATLAS,
  COURSEWORK_COMPARE,
  COURSEWORK_MATRIX,
  COURSEWORK_SCENARIOS,
  buildVkrAtlas,
  pinnedAtlas,
  referenceLint,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import { resolveSides, subjectOf } from "../lib/compare";
import { parseOutcomeSearch } from "../lib/urlState";

// Данные режимов для галереи состояний (/dev/server-screens): те же эталоны контракта, что у
// подмены API, положенные прямо в кэш запросов. Сервер не нужен.

/** Состояния режимов, которые нужно увидеть без сервера. */
export type ModesSeed =
  | "ready"
  | "loading"
  | "busy"
  | "too_large"
  | "no_base"
  | "error_row"
  | "empty"
  | "identical"
  // Режим «Проверка» (F11): атлас пропущен, лимит частоты, версия не читается.
  | "skipped"
  | "rate_limited"
  | "unreadable";

type Where = { id: string; ref: PackVersionRef; search: string };

const fail = (
  client: QueryClient,
  key: readonly unknown[],
  error: ApiError,
): void => {
  client.getQueryCache().build(client, { queryKey: key }).setState({
    status: "error",
    fetchStatus: "idle",
    data: undefined,
    error,
    errorUpdateCount: 1,
    errorUpdatedAt: Date.now(),
  });
};

const hang = (client: QueryClient, key: readonly unknown[]): void => {
  void client.prefetchQuery({
    queryKey: key,
    queryFn: () => new Promise<never>(() => undefined),
  });
};

const withIdentity = <T extends { workspace_id: string }>(
  value: T,
  id: string,
  ref: PackVersionRef,
): T => ({
  ...structuredClone(value),
  workspace_id: id,
  pack: ref.pack,
  template: ref.template,
  version: ref.version,
});

/** Положить в кэш ответ того режима, что открыт в адресе (`view`), в нужном состоянии. */
export const seedModes = (
  client: QueryClient,
  { id, ref, search }: Where,
  seed: ModesSeed,
): void => {
  const url = parseOutcomeSearch(new URLSearchParams(search));
  if (url.view === "matrix") {
    const key = packOutcomeKeys.matrix(id, ref, {
      state: url.state,
      ...(url.against === "base" ? { against: "base" as const } : {}),
    });
    if (seed === "loading") {
      hang(client, key);
      return;
    }
    if (seed === "busy") {
      fail(
        client,
        key,
        new ApiError("Сервер занят расчётом.", "outcome_busy", 503, {
          reason: "timeout",
          retry_after_s: 4,
        }),
      );
      return;
    }
    if (seed === "too_large") {
      fail(
        client,
        key,
        new ApiError("Ответ слишком большой.", "outcome_too_large", 413, {
          limit: 8388608,
          size: 11534336,
        }),
      );
      return;
    }
    const matrix: PackOutcomeMatrix = withIdentity(COURSEWORK_MATRIX, id, ref);
    matrix.state = url.state;
    if (seed === "empty") matrix.rows = [];
    if (seed === "error_row") {
      const [row] = matrix.rows;
      if (row) {
        row.status = "error";
        row.message =
          "Вводная «supervisor» не подходит к версии: значение «firm».";
        row.cells = row.cells.map((cell) => ({
          ...cell,
          status: "error" as const,
          count: 0,
          fingerprint: "",
          changed: null,
        }));
      }
    }
    if (url.against === "base") {
      for (const row of matrix.rows) {
        for (const cell of row.cells) cell.changed = cell.status === "changed";
      }
    }
    client.setQueryData(key, { data: matrix, etag: null });
    return;
  }
  if (url.view === "atlas") {
    const key = packOutcomeKeys.atlas(id, ref, {
      state: url.state,
      example: url.example,
      pin: url.pin,
    });
    if (seed === "loading") {
      hang(client, key);
      return;
    }
    if (seed === "busy") {
      fail(
        client,
        key,
        new ApiError("Сервер занят расчётом.", "outcome_busy", 503, {
          reason: "overloaded",
          retry_after_s: 4,
        }),
      );
      return;
    }
    if (seed === "too_large") {
      fail(
        client,
        key,
        new ApiError("Слишком много комбинаций.", "atlas_too_large", 413, {
          limit: 2000,
          rows: 6912,
        }),
      );
      return;
    }
    const atlas: PackOutcomeAtlas = withIdentity(
      pinnedAtlas(
        ref.template === "vkr" ? buildVkrAtlas() : COURSEWORK_ATLAS,
        url.pin,
      ),
      id,
      ref,
    );
    atlas.state = url.state;
    client.setQueryData(key, { data: atlas, etag: null });
    return;
  }
  if (url.view === "lint") {
    const key = packOutcomeKeys.lint(id, ref, { state: url.state });
    if (seed === "loading") {
      hang(client, key);
      return;
    }
    if (seed === "busy") {
      fail(
        client,
        key,
        new ApiError("Сервер занят расчётом.", "outcome_busy", 503, {
          reason: "overloaded",
          retry_after_s: 4,
        }),
      );
      return;
    }
    if (seed === "rate_limited") {
      fail(
        client,
        key,
        new ApiError(
          "Слишком часто: не больше 6 проверок в минуту.",
          "rate_limited",
          429,
          {
            retry_after: 20,
          },
        ),
      );
      return;
    }
    if (seed === "unreadable") {
      fail(
        client,
        key,
        new ApiError(
          "Версию не удалось прочитать.",
          "version_unreadable",
          422,
          {
            reason: "version.yaml: строка 14, неверный отступ",
          },
        ),
      );
      return;
    }
    const lint: PackOutcomeLint = withIdentity(
      referenceLint(
        seed === "empty"
          ? "lint_empty"
          : seed === "skipped"
            ? "lint_atlas_skipped"
            : "normal",
        ref.template,
      ),
      id,
      ref,
    );
    lint.state = url.state;
    client.setQueryData(key, { data: lint, etag: null });
    return;
  }
  if (url.view === "compare") {
    const entries = COURSEWORK_SCENARIOS.scenarios;
    const sides = resolveSides(url.left, url.right, entries, false);
    const key = packOutcomeKeys.compare(id, ref, {
      left: subjectOf(sides.left, url),
      right: subjectOf(sides.right, url),
    });
    if (seed === "loading") {
      hang(client, key);
      return;
    }
    if (seed === "busy") {
      fail(
        client,
        key,
        new ApiError("Сервер занят расчётом.", "outcome_busy", 503, {
          reason: "timeout",
          retry_after_s: 2,
        }),
      );
      return;
    }
    if (seed === "no_base") {
      fail(
        client,
        key,
        new ApiError("Сравнивать не с чем.", "diff_base_unavailable", 409, {
          reason: "new_version",
        }),
      );
      return;
    }
    const compare: PackOutcomeCompare = withIdentity(
      COURSEWORK_COMPARE,
      id,
      ref,
    );
    if (seed === "identical") {
      compare.identical = true;
      compare.summary = [];
      compare.changes = [];
      compare.right.fingerprint = compare.left.fingerprint;
    }
    client.setQueryData(key, { data: compare, etag: null });
  }
};
