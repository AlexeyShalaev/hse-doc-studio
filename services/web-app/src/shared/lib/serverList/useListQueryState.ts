import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";
import type { SortingState } from "@tanstack/react-table";
import {
  DEFAULT_PAGE_SIZE,
  PAGE_SIZES,
  SEARCH_MAX_LENGTH,
  type ListRequestParams,
} from "./types";

// Состояние серверного списка в адресе страницы: поиск, фильтры, сортировка,
// страница и её размер. Ссылка воспроизводит вид, «Назад» в браузере
// возвращает прошлый. Смена поиска, фильтра, сортировки или размера сбрасывает
// страницу на первую. Значения по умолчанию в адрес не пишутся.
//
// Ключи адреса: q, sort (поле или -поле), page (с единицы), size и имена
// фильтров; несколько значений фильтра повтором ключа. prefix разводит ключи,
// когда на странице два списка (например, «m.q» у участников).

export type ListFilterSpec = {
  /** Несколько значений повтором параметра (status=a&status=b). */
  multi?: boolean;
  /** Допустимые значения (enum): чужие из адреса отбрасываются. */
  values?: readonly string[];
  /**
   * Дата дня (ГГГГ-ММ-ДД) в адресе, а в запросе граница в ISO 8601 с зоной:
   * from включительно с начала дня, to до начала следующего дня.
   */
  date?: "from" | "to";
};

export type SortParam<S extends string> = S | `-${S}`;

export type ListStateOptions<F extends string, S extends string> = {
  /** Приставка ключей адреса, если списков на странице несколько. */
  prefix?: string;
  /** offset: страницы с total; cursor: журнал с «Показать ещё». */
  mode?: "offset" | "cursor";
  filters?: Readonly<Record<F, ListFilterSpec>>;
  /** Разрешённые поля сортировки сервера и порядок по умолчанию. */
  sort?: { fields: readonly S[]; default: SortParam<S> };
  pageSize?: number;
  pageSizes?: readonly number[];
};

export type ListSort<S extends string> = { field: S; desc: boolean };

type FilterInput = string | readonly string[] | null;

export type ListQueryState<
  F extends string = string,
  S extends string = string,
> = {
  /** Поиск после задержки, обрезанный; "" значит без поиска. */
  q: string;
  setQ: (next: string) => void;
  /** Значения всех фильтров; у невыбранного пустой массив. */
  filters: Readonly<Record<F, readonly string[]>>;
  /** Первое значение фильтра или "". */
  filter: (name: F) => string;
  setFilter: (name: F, value: FilterInput) => void;
  /** Несколько фильтров одним переходом (например, from и to). */
  setFilters: (patch: Partial<Record<F, FilterInput>>) => void;
  sort: ListSort<S> | null;
  setSort: (next: ListSort<S> | null) => void;
  /** Сортировка в виде TanStack Table: отдаётся DataTable как есть. */
  sorting: SortingState;
  onSortingChange: (next: SortingState) => void;
  /** Номер страницы с нуля. */
  page: number;
  setPage: (page: number, options?: { replace?: boolean }) => void;
  pageSize: number;
  setPageSize: (size: number) => void;
  pageSizes: readonly number[];
  offset: number;
  /** Есть поиск или хоть один фильтр: пустой ответ значит «ничего не найдено». */
  isFiltered: boolean;
  activeFilterCount: number;
  /** Сбросить поиск и фильтры; сортировка и размер страницы остаются. */
  reset: () => void;
  /** Параметры запроса: limit, offset, q, sort и фильтры. */
  params: ListRequestParams;
  /** Ключ для queryKey: меняется вместе с params. */
  key: string;
};

const parseSort = <S extends string>(
  raw: string | null,
  fields: readonly S[],
): ListSort<S> | null => {
  if (!raw) return null;
  const desc = raw.startsWith("-");
  const field = (desc ? raw.slice(1) : raw) as S;
  return fields.includes(field) ? { field, desc } : null;
};

const sortToParam = <S extends string>(sort: ListSort<S>): string =>
  sort.desc ? `-${sort.field}` : sort.field;

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Граница дня в местном времени: начало дня или начало следующего. */
export const dayBoundaryIso = (day: string, edge: "from" | "to"): string => {
  const [y, m, d] = day.split("-").map(Number);
  const date = new Date(
    y ?? 1970,
    (m ?? 1) - 1,
    (d ?? 1) + (edge === "to" ? 1 : 0),
  );
  return date.toISOString();
};

const cleanValues = (
  values: readonly string[],
  spec: ListFilterSpec,
): string[] => {
  const unique = [...new Set(values.map((v) => v.trim()).filter(Boolean))];
  const allowed = spec.values
    ? unique.filter((v) => spec.values?.includes(v))
    : unique;
  const dated = spec.date ? allowed.filter((v) => DAY.test(v)) : allowed;
  return spec.multi ? dated : dated.slice(0, 1);
};

export const useListQueryState = <
  F extends string = never,
  S extends string = never,
>(
  options: ListStateOptions<F, S> = {},
): ListQueryState<F, S> => {
  const [params, setParams] = useSearchParams();
  const {
    prefix = "",
    mode = "offset",
    filters: specs,
    sort: sortSpec,
    pageSize: defaultSize = DEFAULT_PAGE_SIZE,
    pageSizes = PAGE_SIZES,
  } = options;
  const k = useCallback((name: string) => `${prefix}${name}`, [prefix]);
  const names = useMemo(
    () => (specs ? (Object.keys(specs) as F[]) : []),
    [specs],
  );

  const q = (params.get(k("q")) ?? "").trim().slice(0, SEARCH_MAX_LENGTH);

  const filters = useMemo(() => {
    const out = {} as Record<F, readonly string[]>;
    for (const name of names) {
      const spec = specs?.[name] ?? {};
      out[name] = cleanValues(params.getAll(k(name)), spec);
    }
    return out;
  }, [names, specs, params, k]);

  const sortDefault = sortSpec
    ? parseSort(sortSpec.default, sortSpec.fields)
    : null;
  const sort = sortSpec
    ? (parseSort(params.get(k("sort")), sortSpec.fields) ?? sortDefault)
    : null;

  const sizeRaw = Number(params.get(k("size")));
  const pageSize = pageSizes.includes(sizeRaw) ? sizeRaw : defaultSize;
  const pageRaw = Number(params.get(k("page")));
  const page =
    mode === "offset" && Number.isInteger(pageRaw) && pageRaw > 1
      ? pageRaw - 1
      : 0;

  /** Правка адреса; без keepPage страница сбрасывается на первую. */
  const update = useCallback(
    (
      edit: (next: URLSearchParams) => void,
      { replace = false, keepPage = false } = {},
    ) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          edit(next);
          if (!keepPage) next.delete(k("page"));
          return next;
        },
        { replace },
      );
    },
    [setParams, k],
  );

  const writeFilter = useCallback(
    (next: URLSearchParams, name: F, value: FilterInput) => {
      next.delete(k(name));
      const spec = specs?.[name] ?? {};
      const list =
        value === null ? [] : typeof value === "string" ? [value] : value;
      for (const v of cleanValues(list, spec)) next.append(k(name), v);
    },
    [specs, k],
  );

  const setQ = useCallback(
    (value: string) => {
      const text = value.trim().slice(0, SEARCH_MAX_LENGTH);
      // Набор текста не плодит записи истории: «Назад» ведёт к прошлому виду.
      update(
        (next) => {
          if (text) next.set(k("q"), text);
          else next.delete(k("q"));
        },
        { replace: true },
      );
    },
    [update, k],
  );

  const setFilter = useCallback(
    (name: F, value: FilterInput) => {
      update((next) => {
        writeFilter(next, name, value);
      });
    },
    [update, writeFilter],
  );

  const setFilters = useCallback(
    (patch: Partial<Record<F, FilterInput>>) => {
      update((next) => {
        for (const name of Object.keys(patch) as F[]) {
          writeFilter(next, name, patch[name] ?? null);
        }
      });
    },
    [update, writeFilter],
  );

  const setSort = useCallback(
    (value: ListSort<S> | null) => {
      update((next) => {
        const isDefault =
          value === null ||
          (sortDefault !== null &&
            value.field === sortDefault.field &&
            value.desc === sortDefault.desc);
        if (isDefault) next.delete(k("sort"));
        else next.set(k("sort"), sortToParam(value));
      });
    },
    [update, k, sortDefault],
  );

  const onSortingChange = useCallback(
    (next: SortingState) => {
      const first = next[0];
      setSort(first ? { field: first.id as S, desc: first.desc } : null);
    },
    [setSort],
  );

  const setPage = useCallback(
    (value: number, { replace = false }: { replace?: boolean } = {}) => {
      update(
        (next) => {
          if (value > 0) next.set(k("page"), String(value + 1));
          else next.delete(k("page"));
        },
        { replace, keepPage: true },
      );
    },
    [update, k],
  );

  const setPageSize = useCallback(
    (size: number) => {
      update((next) => {
        if (size === defaultSize || !pageSizes.includes(size))
          next.delete(k("size"));
        else next.set(k("size"), String(size));
      });
    },
    [update, k, defaultSize, pageSizes],
  );

  const reset = useCallback(() => {
    update((next) => {
      next.delete(k("q"));
      for (const name of names) next.delete(k(name));
    });
  }, [update, k, names]);

  const activeFilterCount = names.filter(
    (name) => filters[name].length > 0,
  ).length;

  const request = useMemo(() => {
    const out: ListRequestParams = { limit: pageSize };
    if (mode === "offset") out.offset = page * pageSize;
    if (q) out.q = q;
    if (sort && mode === "offset") out.sort = sortToParam(sort);
    for (const name of names) {
      const values = filters[name];
      if (values.length === 0) continue;
      const spec = specs?.[name] ?? {};
      const wire = spec.date
        ? values.map((v) => dayBoundaryIso(v, spec.date ?? "from"))
        : [...values];
      out[name] = spec.multi ? wire : (wire[0] ?? "");
    }
    return out;
  }, [pageSize, mode, page, q, sort, names, filters, specs]);

  const key = useMemo(() => JSON.stringify(request), [request]);

  return {
    q,
    setQ,
    filters,
    filter: (name) => filters[name][0] ?? "",
    setFilter,
    setFilters,
    sort,
    setSort,
    sorting: sort ? [{ id: sort.field, desc: sort.desc }] : [],
    onSortingChange,
    page,
    setPage,
    pageSize,
    setPageSize,
    pageSizes,
    offset: page * pageSize,
    isFiltered: q !== "" || activeFilterCount > 0,
    activeFilterCount,
    reset,
    params: request,
    key,
  };
};
