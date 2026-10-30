import { useId, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { localeTag } from "../../lib/i18n/localeTag";
import { Select } from "../Select";
import { Spinner } from "../Spinner";

// Листание серверного списка. Два режима:
//  - offset: «1–50 из 12 345», первая, назад, номер страницы для перехода,
//    вперёд, последняя и размер страницы;
//  - cursor: журнал, «Показать ещё» и сколько уже показано; «из N» только
//    когда сервер дал оценку (без фильтров).
// Числа с разделителями тысяч по языку интерфейса.

export type OffsetPaginationProps = {
  mode?: "offset";
  /** Номер страницы с нуля. */
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  /** Варианты размера страницы; без onPageSizeChange переключателя нет. */
  pageSizes?: readonly number[] | undefined;
  onPageSizeChange?: ((size: number) => void) | undefined;
  /** Идёт запрос: кнопки остаются, рядом с числами крутилка. */
  busy?: boolean | undefined;
  className?: string | undefined;
};

export type CursorPaginationProps = {
  mode: "cursor";
  /** Сколько строк уже на экране. */
  shown: number;
  hasMore: boolean;
  onLoadMore: () => void;
  loading?: boolean | undefined;
  /** Оценка общего числа; null при фильтрах, тогда «из N» не пишется. */
  totalEstimate?: number | null | undefined;
  pageSize?: number | undefined;
  pageSizes?: readonly number[] | undefined;
  onPageSizeChange?: ((size: number) => void) | undefined;
  className?: string | undefined;
};

export type PaginationProps = OffsetPaginationProps | CursorPaginationProps;

const fmt = (n: number): string => n.toLocaleString(localeTag());

/**
 * Покажет ли листание по страницам что-нибудь. Листать некуда, пока всё
 * помещается на первую страницу самого малого размера: «По 50», серые
 * «Назад/Вперёд» и «Страница 1 из 1» только шумят (то же правило, что
 * needsPager у коротких списков). Пустой список тоже. Обёртки с рамкой или
 * отступом спрашивают это, чтобы не оставлять пустую полосу.
 */
export const offsetPagerShown = ({
  page,
  pageSize,
  total,
  pageSizes,
}: Pick<
  OffsetPaginationProps,
  "page" | "pageSize" | "total" | "pageSizes"
>): boolean =>
  total > 0 && (page > 0 || total > Math.min(pageSize, ...(pageSizes ?? [])));

export const Pagination = (props: PaginationProps) =>
  props.mode === "cursor" ? (
    <CursorPager {...props} />
  ) : (
    <OffsetPager {...props} />
  );

const SizeSelect = ({
  pageSize,
  pageSizes,
  onChange,
}: {
  pageSize: number;
  pageSizes: readonly number[];
  onChange: (size: number) => void;
}) => {
  const { t } = useTranslation("uiPrimitives");
  return (
    <span className="pager-size">
      <Select
        value={String(pageSize)}
        onValueChange={(value) => {
          onChange(Number(value));
        }}
        ariaLabel={t("pagination.pageSize")}
        options={pageSizes.map((size) => ({
          value: String(size),
          label: t("pagination.perPage", { n: fmt(size) }),
        }))}
      />
    </span>
  );
};

const OffsetPager = ({
  page,
  pageSize,
  total,
  onPageChange,
  pageSizes,
  onPageSizeChange,
  busy = false,
  className,
}: OffsetPaginationProps) => {
  const { t } = useTranslation("uiPrimitives");
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (!offsetPagerShown({ page, pageSize, total, pageSizes })) return null;
  const from = total === 0 ? 0 : page * pageSize + 1;
  const to = Math.min(total, (page + 1) * pageSize);
  const atStart = page <= 0;
  const atEnd = page + 1 >= pages;
  const go = (next: number) => {
    const clamped = Math.min(Math.max(0, next), pages - 1);
    if (clamped !== page) onPageChange(clamped);
  };
  return (
    <nav
      aria-label={t("dataTable.pagination")}
      className={clsx("pager", className)}
    >
      <span className="pager-range" aria-live="polite">
        {t("dataTable.range", {
          from: fmt(from),
          to: fmt(to),
          total: fmt(total),
        })}
        {busy && <Spinner size="sm" />}
      </span>
      <span className="pager-controls">
        {pageSizes && onPageSizeChange && (
          <SizeSelect
            pageSize={pageSize}
            pageSizes={pageSizes}
            onChange={onPageSizeChange}
          />
        )}
        {pages > 2 && (
          <button
            type="button"
            className="btn sm ghost pager-icon"
            disabled={atStart}
            aria-label={t("pagination.first")}
            title={t("pagination.first")}
            onClick={() => {
              go(0);
            }}
          >
            <ChevronsLeft size={14} aria-hidden="true" />
          </button>
        )}
        <button
          type="button"
          className="btn sm"
          disabled={atStart}
          onClick={() => {
            go(page - 1);
          }}
        >
          <ChevronLeft size={13} aria-hidden="true" />
          {t("dataTable.prev")}
        </button>
        <PageJump page={page} pages={pages} onJump={go} />
        <button
          type="button"
          className="btn sm"
          disabled={atEnd}
          onClick={() => {
            go(page + 1);
          }}
        >
          {t("dataTable.next")}
          <ChevronRight size={13} aria-hidden="true" />
        </button>
        {pages > 2 && (
          <button
            type="button"
            className="btn sm ghost pager-icon"
            disabled={atEnd}
            aria-label={t("pagination.last")}
            title={t("pagination.last")}
            onClick={() => {
              go(pages - 1);
            }}
          >
            <ChevronsRight size={14} aria-hidden="true" />
          </button>
        )}
      </span>
    </nav>
  );
};

/** «Страница [ 3 ] из 247»: номер можно ввести и нажать Enter. */
const PageJump = ({
  page,
  pages,
  onJump,
}: {
  page: number;
  pages: number;
  onJump: (page: number) => void;
}) => {
  const { t } = useTranslation("uiPrimitives");
  const id = useId();
  // Черновик номера живёт, пока не сменилась страница: потом поле снова
  // показывает текущую.
  const [draft, setDraft] = useState<{ page: number; text: string } | null>(
    null,
  );
  const text = draft?.page === page ? draft.text : String(page + 1);
  const setText = (value: string) => {
    setDraft({ page, text: value });
  };
  if (pages <= 1) {
    return (
      <span className="pager-of">
        {t("dataTable.pageOf", { page: 1, pages: 1 })}
      </span>
    );
  }
  const commit = () => {
    const n = Number(text.replace(/\s/g, ""));
    if (Number.isInteger(n) && n >= 1) onJump(Math.min(n, pages) - 1);
    setDraft(null);
  };
  return (
    <span className="pager-of">
      <label htmlFor={id}>{t("pagination.page")}</label>
      <input
        id={id}
        className="input pager-input"
        inputMode="numeric"
        value={text}
        aria-label={t("pagination.jump", { pages: fmt(pages) })}
        onChange={(event) => {
          setText(event.target.value.replace(/[^\d]/g, ""));
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit();
          }
          if (event.key === "Escape") setDraft(null);
        }}
        onBlur={commit}
        style={{
          width: `${String(Math.max(3, String(pages).length + 1.5))}ch`,
        }}
      />
      <span>{t("pagination.of", { pages: fmt(pages) })}</span>
    </span>
  );
};

const CursorPager = ({
  shown,
  hasMore,
  onLoadMore,
  loading = false,
  totalEstimate = null,
  pageSize,
  pageSizes,
  onPageSizeChange,
  className,
}: CursorPaginationProps) => {
  const { t } = useTranslation("uiPrimitives");
  if (shown === 0 && !hasMore) return null;
  return (
    <nav
      aria-label={t("dataTable.pagination")}
      className={clsx("pager", className)}
    >
      <span className="pager-range" aria-live="polite">
        {totalEstimate != null && totalEstimate >= shown
          ? t("pagination.shownOf", {
              count: shown,
              n: fmt(shown),
              total: fmt(totalEstimate),
            })
          : t("pagination.shown", { count: shown, n: fmt(shown) })}
      </span>
      <span className="pager-controls">
        {pageSize !== undefined && pageSizes && onPageSizeChange && (
          <SizeSelect
            pageSize={pageSize}
            pageSizes={pageSizes}
            onChange={onPageSizeChange}
          />
        )}
        {hasMore ? (
          <button
            type="button"
            className="btn sm"
            disabled={loading}
            onClick={onLoadMore}
          >
            {loading && <Spinner size="sm" />}
            {t("pagination.more")}
          </button>
        ) : (
          <span className="pager-end">{t("pagination.end")}</span>
        )}
      </span>
    </nav>
  );
};

Pagination.displayName = "Pagination";
