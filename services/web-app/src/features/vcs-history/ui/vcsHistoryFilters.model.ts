import type { VcsHistoryParams, VcsSyncFilter } from "@entities/vcs";

// Модель фильтров ленты «Недавние изменения»: отдельно от компонента, чтобы
// значения и функции не мешали Fast Refresh. Сами условия уходят на сервер,
// здесь они только собираются в запрос.

export type VcsDatePreset = "all" | "today" | "7d" | "30d" | "custom";

// "all", "mine" (по e-mail из профиля) или e-mail конкретного автора.
export type VcsAuthorFilter = string;

export const AUTHOR_ALL = "all";
export const AUTHOR_MINE = "mine";

export type VcsHistoryFilterState = {
  query: string;
  // Выбранные виды записей: известные виды и "other" для всех остальных.
  // Пусто означает «все».
  kinds: string[];
  preset: VcsDatePreset;
  from: string; // yyyy-mm-dd (свой диапазон)
  to: string; // yyyy-mm-dd (свой диапазон)
  author: VcsAuthorFilter;
  sync: VcsSyncFilter;
};

export type VcsKindOption = { kind: string; label: string; count: number };

export type VcsAuthorOption = { value: string; label: string };

export const EMPTY_VCS_FILTERS: VcsHistoryFilterState = {
  query: "",
  kinds: [],
  preset: "all",
  from: "",
  to: "",
  author: AUTHOR_ALL,
  sync: "all",
};

// Виды, которые у фильтра есть отдельной кнопкой, в порядке показа. Именные
// версии (manual) живут в своём списке слева и сюда не входят.
export const VCS_KIND_CHIPS = [
  "edit",
  "compile",
  "restore",
  "init",
  "template_update",
  "sync",
] as const;

// Все незнакомые виды (в том числе будущие) собираются в одну кнопку.
export const VCS_KIND_OTHER = "other";

export const NAMED_KIND = "manual";

const KNOWN_KINDS = new Set<string>([...VCS_KIND_CHIPS, NAMED_KIND]);

export const isVcsFiltersActive = (s: VcsHistoryFilterState): boolean =>
  s.query.trim() !== "" ||
  s.kinds.length > 0 ||
  s.preset !== "all" ||
  s.from !== "" ||
  s.to !== "" ||
  s.author !== AUTHOR_ALL ||
  s.sync !== "all";

// Кнопки видов с числом записей: только те, что встречаются в истории, и ещё
// выбранные сейчас (иначе их нельзя было бы снять).
export const kindChipIds = (
  facetKinds: Record<string, number>,
  selected: string[] = [],
): { kind: string; count: number }[] => {
  const chips: { kind: string; count: number }[] = [];
  for (const kind of VCS_KIND_CHIPS) {
    const count = facetKinds[kind] ?? 0;
    if (count > 0 || selected.includes(kind)) chips.push({ kind, count });
  }
  const otherCount = Object.entries(facetKinds)
    .filter(([kind]) => !KNOWN_KINDS.has(kind))
    .reduce((sum, [, count]) => sum + count, 0);
  if (otherCount > 0 || selected.includes(VCS_KIND_OTHER)) {
    chips.push({ kind: VCS_KIND_OTHER, count: otherCount });
  }
  return chips;
};

// Сколько записей в ленте без фильтров: все, кроме именных версий.
export const recentTotal = (facetKinds: Record<string, number>): number =>
  Object.entries(facetKinds)
    .filter(([kind]) => kind !== NAMED_KIND)
    .reduce((sum, [, count]) => sum + count, 0);

// Какие виды просить у сервера. Кнопка «Другое» раскрывается во все незнакомые
// виды из фасетов. Без выбора просим все виды, кроме именных: они в своём списке.
export const resolveKinds = (
  chips: string[],
  facetKinds: Record<string, number> | undefined,
): string[] | undefined => {
  const unknown = Object.keys(facetKinds ?? {}).filter(
    (kind) => !KNOWN_KINDS.has(kind),
  );
  if (chips.length > 0) {
    const kinds = new Set<string>();
    for (const chip of chips) {
      if (chip === VCS_KIND_OTHER) unknown.forEach((k) => kinds.add(k));
      else kinds.add(chip);
    }
    return kinds.size > 0 ? [...kinds] : undefined;
  }
  if (!facetKinds) return undefined;
  const all = Object.keys(facetKinds).filter((kind) => kind !== NAMED_KIND);
  return all.length > 0 ? all : undefined;
};

const startOfDay = (date: Date): Date =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate());

// Границы окна по датам: начало суток для «сегодня» и последних дней (чтобы
// запрос не менялся каждую секунду), конец суток для верхней границы диапазона.
export const dateWindow = (
  state: Pick<VcsHistoryFilterState, "preset" | "from" | "to">,
  now: Date = new Date(),
): { since?: string; until?: string } => {
  const today = startOfDay(now);
  const daysAgo = (days: number): Date =>
    new Date(today.getFullYear(), today.getMonth(), today.getDate() - days);
  switch (state.preset) {
    case "today":
      return { since: today.toISOString() };
    case "7d":
      return { since: daysAgo(7).toISOString() };
    case "30d":
      return { since: daysAgo(30).toISOString() };
    case "custom": {
      const window: { since?: string; until?: string } = {};
      if (state.from) {
        window.since = new Date(`${state.from}T00:00:00`).toISOString();
      }
      if (state.to) {
        window.until = new Date(`${state.to}T23:59:59.999`).toISOString();
      }
      return window;
    }
    default:
      return {};
  }
};

export type HistoryParamsContext = {
  /** E-mail автора из профиля: по нему работает «Только мои». */
  mineEmail: string | null;
  /** Сколько записей каждого вида в истории (фасеты); пока не пришли, undefined. */
  facetKinds: Record<string, number> | undefined;
  now?: Date;
};

// Условия фильтров -> параметры запроса истории (без limit и offset).
export const buildHistoryParams = (
  state: VcsHistoryFilterState,
  context: HistoryParamsContext,
): Omit<VcsHistoryParams, "limit" | "offset"> => {
  const params: Omit<VcsHistoryParams, "limit" | "offset"> = {};
  const kinds = resolveKinds(state.kinds, context.facetKinds);
  if (kinds) params.kind = kinds;

  if (state.author === AUTHOR_MINE) {
    if (context.mineEmail) params.authorEmail = context.mineEmail;
  } else if (state.author !== AUTHOR_ALL) {
    params.authorEmail = state.author;
  }

  const query = state.query.trim();
  if (query) params.q = query;

  const window = dateWindow(state, context.now);
  if (window.since) params.since = window.since;
  if (window.until) params.until = window.until;

  if (state.sync !== "all") params.sync = state.sync;
  return params;
};

// Версия пришла из репозитория и локально её ещё нет: вернуться к ней нельзя.
export const isIncomingOnly = (commit: {
  sync?: string | null | undefined;
}): boolean => commit.sync === "incoming";

export const initialsOf = (name: string): string => {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "?";
  const second = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return `${first}${second}`.toUpperCase();
};

// Чья это версия: без e-mail (старый бэкенд) или без профиля считаем своей.
export const isOwnCommit = (
  commit: { author_email?: string | null | undefined },
  mineEmail: string | null | undefined,
): boolean =>
  !mineEmail ||
  !commit.author_email ||
  commit.author_email.toLowerCase() === mineEmail.toLowerCase();
