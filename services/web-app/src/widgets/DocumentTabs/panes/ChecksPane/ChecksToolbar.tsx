import { clsx } from "clsx";
import { Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FilterKind, Mode, SeverityCounts } from "./types";

export type ChecksToolbarProps = {
  mode: Mode;
  onModeChange: (mode: Mode) => void;
  // Results-mode props (ignored in rules mode)
  filter: FilterKind;
  onFilterChange: (filter: FilterKind) => void;
  counts: SeverityCounts;
  passRate: number;
  // Hand the currently shown findings to the agent. Omitted → button hidden.
  onFixAll?: () => void;
  // Rules-mode props
  totalRules: number;
  enabledCount: number;
};

const FILTER_ORDER: readonly FilterKind[] = [
  "all",
  "err",
  "warn",
  "info",
  "ok",
  "skipped",
];

export const ChecksToolbar = ({
  mode,
  onModeChange,
  filter,
  onFilterChange,
  counts,
  passRate,
  onFixAll,
  totalRules,
  enabledCount,
}: ChecksToolbarProps) => {
  const { t } = useTranslation("documents");
  return (
    <div
      className="flex items-center justify-between"
      style={{
        padding: "12px 18px",
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div className="flex items-center gap-3">
        {mode === "results" ? (
          <PassRateBlock passRate={passRate} />
        ) : (
          <RulesStatBlock total={totalRules} enabled={enabledCount} />
        )}
      </div>
      <div className="flex items-center" style={{ gap: 8 }}>
        {mode === "results" && onFixAll && counts.err + counts.warn > 0 && (
          <button
            type="button"
            className="btn xs"
            onClick={onFixAll}
            title={t("checks.fixWithAiTitle")}
          >
            <Sparkles size={11} />
            {t("checks.fixWithAi")}
          </button>
        )}
        {mode === "results" && (
          <SeverityFilter
            filter={filter}
            counts={counts}
            onChange={onFilterChange}
          />
        )}
        <div className="seg">
          <button
            type="button"
            className={clsx(mode === "results" && "active")}
            onClick={() => {
              onModeChange("results");
            }}
          >
            {t("checks.results")}
          </button>
          <button
            type="button"
            className={clsx(mode === "rules" && "active")}
            onClick={() => {
              onModeChange("rules");
            }}
          >
            {t("checks.rules")}
          </button>
        </div>
      </div>
    </div>
  );
};

const PassRateBlock = ({ passRate }: { passRate: number }) => {
  const { t } = useTranslation("documents");
  return (
    <div className="flex flex-col" style={{ gap: 2 }}>
      <strong style={{ fontSize: 13 }}>
        {t("checks.compliance", { rate: passRate })}
      </strong>
      <div className="progress" style={{ width: 200 }}>
        <div
          style={{
            width: `${String(passRate)}%`,
            background:
              passRate > 80
                ? "var(--c-ok)"
                : passRate > 60
                  ? "var(--c-warn)"
                  : "var(--c-err)",
          }}
        />
      </div>
    </div>
  );
};

const RulesStatBlock = ({
  total,
  enabled,
}: {
  total: number;
  enabled: number;
}) => {
  const { t } = useTranslation("documents");
  return (
    <div className="flex flex-col" style={{ gap: 2 }}>
      <strong style={{ fontSize: 13 }}>
        {t("checks.activeRules", { enabled, total })}
      </strong>
      <span className="dim" style={{ fontSize: 11 }}>
        {t("checks.rulesSubtitle")}
      </span>
    </div>
  );
};

const SeverityFilter = ({
  filter,
  counts,
  onChange,
}: {
  filter: FilterKind;
  counts: SeverityCounts;
  onChange: (filter: FilterKind) => void;
}) => {
  const { t } = useTranslation("documents");
  return (
    <div className="seg">
      {FILTER_ORDER.map((f) => (
        <button
          key={f}
          type="button"
          className={clsx(filter === f && "active")}
          onClick={() => {
            onChange(f);
          }}
        >
          {f === "all"
            ? t("checks.filterAll")
            : f === "skipped"
              ? t("checks.filterSkipped")
              : f.toUpperCase()}
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              minWidth: 16,
              height: 14,
              padding: "0 4px",
              borderRadius: 999,
              background: "var(--bg-3)",
              fontSize: 9.5,
              fontFamily: "var(--font-mono)",
              marginLeft: 4,
            }}
          >
            {counts[f]}
          </span>
        </button>
      ))}
    </div>
  );
};
