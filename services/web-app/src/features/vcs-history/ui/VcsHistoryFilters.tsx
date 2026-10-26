import { useTranslation } from "react-i18next";
import { RotateCcw, Search } from "lucide-react";
import { clsx } from "clsx";
import { VCS_SYNC_FILTERS, type VcsSyncFilter } from "@entities/vcs";
import {
  EMPTY_VCS_FILTERS,
  type VcsAuthorOption,
  type VcsDatePreset,
  type VcsHistoryFilterState,
  type VcsKindOption,
  isVcsFiltersActive,
} from "./vcsHistoryFilters.model";

// Компактная панель фильтров над лентой «Недавние изменения»: поиск, виды записей
// (можно выбрать несколько), автор, окно дат и, если подключён репозиторий,
// отметка отправки. Условия уходят на сервер, поэтому лента остаётся удобной и
// при тысячах автоматических версий.

export type VcsHistoryFiltersProps = {
  state: VcsHistoryFilterState;
  onChange: (next: VcsHistoryFilterState) => void;
  kinds: VcsKindOption[];
  /** «Все авторы», «Только мои» и люди из истории; пусто или одно: список скрыт. */
  authors: VcsAuthorOption[];
  /** Подключён репозиторий: показываем отметку отправки. */
  showSync: boolean;
  /** Сколько записей в ленте без фильтров. */
  total: number;
  /** Сколько записей загружено сейчас. */
  shown: number;
  /** На сервере есть ещё записи под эти условия. */
  hasMore: boolean;
};

const controlStyle: React.CSSProperties = {
  width: "auto",
  fontSize: 12,
  padding: "6px 10px",
  height: 30,
};

export const VcsHistoryFilters = ({
  state,
  onChange,
  kinds,
  authors,
  showSync,
  total,
  shown,
  hasMore,
}: VcsHistoryFiltersProps) => {
  const { t } = useTranslation("vcsHistory");
  const active = isVcsFiltersActive(state);
  const set = (patch: Partial<VcsHistoryFilterState>) => {
    onChange({ ...state, ...patch });
  };
  const toggleKind = (kind: string) => {
    set({
      kinds: state.kinds.includes(kind)
        ? state.kinds.filter((k) => k !== kind)
        : [...state.kinds, kind],
    });
  };
  const authorKnown = authors.some((a) => a.value === state.author);
  const authorOptions = authorKnown
    ? authors
    : [...authors, { value: state.author, label: state.author }];

  return (
    <div className="flex flex-col" style={{ gap: 8 }}>
      <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
        {/* search */}
        <div
          className="flex items-center"
          style={{ position: "relative", flex: "1 1 200px", minWidth: 160 }}
        >
          <Search
            size={13}
            aria-hidden="true"
            style={{
              position: "absolute",
              left: 10,
              color: "var(--fg-3)",
              pointerEvents: "none",
            }}
          />
          <input
            className="input"
            type="search"
            aria-label={t("filters.searchLabel")}
            style={{ fontSize: 12, padding: "6px 10px 6px 30px", height: 30 }}
            placeholder={t("filters.searchPlaceholder")}
            value={state.query}
            onChange={(e) => {
              set({ query: e.target.value });
            }}
          />
        </div>

        {/* author */}
        {authors.length > 1 && (
          <select
            className="input"
            aria-label={t("filters.authorLabel")}
            style={{ ...controlStyle, maxWidth: 190 }}
            value={state.author}
            onChange={(e) => {
              set({ author: e.target.value });
            }}
          >
            {authorOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        )}

        {/* date window */}
        <select
          className="input"
          aria-label={t("filters.dateLabel")}
          style={controlStyle}
          value={state.preset}
          onChange={(e) => {
            set({ preset: e.target.value as VcsDatePreset });
          }}
        >
          <option value="all">{t("filters.presetAll")}</option>
          <option value="today">{t("filters.presetToday")}</option>
          <option value="7d">{t("filters.preset7d")}</option>
          <option value="30d">{t("filters.preset30d")}</option>
          <option value="custom">{t("filters.presetCustom")}</option>
        </select>

        {active && (
          <button
            type="button"
            className="btn xs ghost"
            onClick={() => {
              onChange(EMPTY_VCS_FILTERS);
            }}
            title={t("filters.resetTitle")}
          >
            <RotateCcw size={11} aria-hidden="true" />
            {t("filters.reset")}
          </button>
        )}
      </div>

      {/* custom range */}
      {state.preset === "custom" && (
        <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
          <span className="dim" style={{ fontSize: 11 }}>
            {t("filters.rangeFrom")}
          </span>
          <input
            type="date"
            className="input"
            aria-label={t("filters.rangeFromLabel")}
            style={{ ...controlStyle, padding: "5px 8px" }}
            value={state.from}
            max={state.to || undefined}
            onChange={(e) => {
              set({ from: e.target.value });
            }}
          />
          <span className="dim" style={{ fontSize: 11 }}>
            {t("filters.rangeTo")}
          </span>
          <input
            type="date"
            className="input"
            aria-label={t("filters.rangeToLabel")}
            style={{ ...controlStyle, padding: "5px 8px" }}
            value={state.to}
            min={state.from || undefined}
            onChange={(e) => {
              set({ to: e.target.value });
            }}
          />
        </div>
      )}

      {/* sync segment */}
      {showSync && (
        <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
          <span className="dim" style={{ fontSize: 11 }}>
            {t("filters.syncLabel")}
          </span>
          <div
            role="group"
            aria-label={t("filters.syncLabel")}
            className="flex"
            style={{ gap: 4 }}
          >
            {VCS_SYNC_FILTERS.map((value: VcsSyncFilter) => (
              <button
                key={value}
                type="button"
                className={clsx("btn xs", state.sync === value && "primary")}
                aria-pressed={state.sync === value}
                onClick={() => {
                  set({ sync: value });
                }}
              >
                {t(`filters.sync.${value}`)}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* type chips */}
      {(kinds.length > 1 || state.kinds.length > 0) && (
        <div
          role="group"
          aria-label={t("filters.kindLabel")}
          className="flex items-center"
          style={{ gap: 6, flexWrap: "wrap" }}
          title={t("filters.kindHint")}
        >
          <button
            type="button"
            className={clsx("fchip", state.kinds.length === 0 && "active")}
            aria-pressed={state.kinds.length === 0}
            onClick={() => {
              set({ kinds: [] });
            }}
          >
            {t("filters.kindAll")}
            <span className="fchip-count">{String(total)}</span>
          </button>
          {kinds.map((k) => {
            const selected = state.kinds.includes(k.kind);
            return (
              <button
                key={k.kind}
                type="button"
                className={clsx("fchip", selected && "active")}
                aria-pressed={selected}
                onClick={() => {
                  toggleKind(k.kind);
                }}
              >
                {k.label}
                <span className="fchip-count">{String(k.count)}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* result summary */}
      <span className="dim" style={{ fontSize: 11 }} aria-live="polite">
        {active
          ? hasMore
            ? t("filters.foundMore", { count: shown })
            : t("filters.found", { count: shown })
          : t("filters.changes", { count: total })}
      </span>
    </div>
  );
};
