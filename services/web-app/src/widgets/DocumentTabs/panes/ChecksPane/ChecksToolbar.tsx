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
        padding: "0.75rem 1.125rem",
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
      <div className="flex items-center" style={{ gap: "0.5rem" }}>
        {mode === "results" && onFixAll && counts.err + counts.warn > 0 && (
          <button
            type="button"
            className="btn xs"
            onClick={onFixAll}
            title={t("checks.fixWithAiTitle")}
          >
            <Sparkles size="0.6875rem" />
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
    <div className="flex flex-col" style={{ gap: "0.125rem" }}>
      <strong style={{ fontSize: "0.8125rem" }}>
        {t("checks.compliance", { rate: passRate })}
      </strong>
      <div className="progress" style={{ width: "12.5rem" }}>
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
    <div className="flex flex-col" style={{ gap: "0.125rem" }}>
      <strong style={{ fontSize: "0.8125rem" }}>
        {t("checks.activeRules", { enabled, total })}
      </strong>
      <span className="dim" style={{ fontSize: "0.6875rem" }}>
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
              minWidth: "1rem",
              height: "0.875rem",
              padding: "0 0.25rem",
              borderRadius: "999px",
              background: "var(--bg-3)",
              fontSize: "0.59375rem",
              fontFamily: "var(--font-mono)",
              marginLeft: "0.25rem",
            }}
          >
            {counts[f]}
          </span>
        </button>
      ))}
    </div>
  );
};
