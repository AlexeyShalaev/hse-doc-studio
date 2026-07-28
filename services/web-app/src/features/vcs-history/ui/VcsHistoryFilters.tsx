import { useTranslation } from "react-i18next";
import { RotateCcw, Search } from "lucide-react";
import { clsx } from "clsx";
import {
  EMPTY_VCS_FILTERS,
  type VcsDatePreset,
  type VcsHistoryFilterState,
  type VcsKindOption,
  isVcsFiltersActive,
} from "./vcsHistoryFilters.model";

// Compact filter bar over the "recent changes" timeline: free-text search,
// single-select change-type chips, and a date window (quick presets + a custom
// range). Keeps the long auto-history scannable without endless scrolling.

export type VcsHistoryFiltersProps = {
  state: VcsHistoryFilterState;
  onChange: (next: VcsHistoryFilterState) => void;
  kinds: VcsKindOption[];
  total: number;
  shown: number;
};

export const VcsHistoryFilters = ({
  state,
  onChange,
  kinds,
  total,
  shown,
}: VcsHistoryFiltersProps) => {
  const { t } = useTranslation("vcsHistory");
  const active = isVcsFiltersActive(state);
  const set = (patch: Partial<VcsHistoryFilterState>) => {
    onChange({ ...state, ...patch });
  };

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
            style={{
              position: "absolute",
              left: 10,
              color: "var(--fg-3)",
              pointerEvents: "none",
            }}
          />
          <input
            className="input"
            style={{ fontSize: 12, padding: "6px 10px 6px 30px", height: 30 }}
            placeholder={t("filters.searchPlaceholder")}
            value={state.query}
            onChange={(e) => {
              set({ query: e.target.value });
            }}
          />
        </div>

        {/* date window */}
        <select
          className="input"
          style={{
            width: "auto",
            fontSize: 12,
            padding: "6px 10px",
            height: 30,
          }}
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
            <RotateCcw size={11} />
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
            style={{
              width: "auto",
              fontSize: 12,
              padding: "5px 8px",
              height: 30,
            }}
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
            style={{
              width: "auto",
              fontSize: 12,
              padding: "5px 8px",
              height: 30,
            }}
            value={state.to}
            min={state.from || undefined}
            onChange={(e) => {
              set({ to: e.target.value });
            }}
          />
        </div>
      )}

      {/* type chips */}
      {kinds.length > 1 && (
        <div className="flex items-center" style={{ gap: 6, flexWrap: "wrap" }}>
          <button
            type="button"
            className={clsx("fchip", state.kind === "all" && "active")}
            onClick={() => {
              set({ kind: "all" });
            }}
          >
            {t("filters.kindAll")}
            <span className="fchip-count">{String(total)}</span>
          </button>
          {kinds.map((k) => (
            <button
              key={k.kind}
              type="button"
              className={clsx("fchip", state.kind === k.kind && "active")}
              onClick={() => {
                set({ kind: k.kind });
              }}
            >
              {k.label}
              <span className="fchip-count">{String(k.count)}</span>
            </button>
          ))}
        </div>
      )}

      {/* result summary */}
      <span className="dim" style={{ fontSize: 11 }}>
        {active
          ? t("filters.shown", { shown, total })
          : t("filters.changes", { count: total })}
      </span>
    </div>
  );
};
