import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  Info,
  MinusCircle,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { CheckSeverity } from "@shared/api/types";
import { CheckCard } from "./CheckCard";
import type { CheckItem, Severity } from "./types";

// Severity precedence used to pick the "worst" severity inside a group — used
// to color the group's left strip and count. Higher number wins.
const SEV_RANK: Record<Severity, number> = {
  skipped: 0,
  ok: 1,
  info: 2,
  warn: 3,
  err: 4,
};

const SEV_ICON: Record<Severity, LucideIcon> = {
  ok: CheckCircle,
  warn: AlertTriangle,
  err: XCircle,
  info: Info,
  skipped: MinusCircle,
};

// A skipped rule always forms its own group (one synthetic result per
// suppressed rule, never mixed with graded findings), so starting from the
// first item's own severity — rather than a fixed "ok" default — correctly
// keeps an all-skipped group "skipped" instead of misreporting it as passed.
const worstSeverity = (items: readonly CheckItem[]): Severity => {
  let worst: Severity = items[0]?.sev ?? "ok";
  for (const it of items) {
    if (SEV_RANK[it.sev] > SEV_RANK[worst]) worst = it.sev;
  }
  return worst;
};

export type ResultsViewProps = {
  filtered: readonly CheckItem[];
  disabledRules: ReadonlySet<string>;
  onToggleRule: (ruleId: string) => void;
  isMutating: boolean;
  // Severity override is a per-document setting; passing handlers down lets
  // a user demote/promote a rule from the result card without switching tabs.
  severityOverride?: Record<string, CheckSeverity>;
  onSetSeverity?: (ruleId: string, sev: CheckSeverity) => void;
  onResetSeverity?: (ruleId: string) => void;
  onFixWithAi?: (item: CheckItem) => void;
  onIgnoreFinding?: (item: CheckItem) => void;
  isIgnoringFinding?: boolean;
  onGoToSource?: (item: CheckItem) => void;
};

const DEFAULT_EXPAND_THRESHOLD = 3;

export const ResultsView = ({
  filtered,
  disabledRules,
  onToggleRule,
  isMutating,
  severityOverride,
  onSetSeverity,
  onResetSeverity,
  onFixWithAi,
  onIgnoreFinding,
  isIgnoringFinding,
  onGoToSource,
}: ResultsViewProps) => {
  const { t } = useTranslation("documents");
  const groups = useMemo(() => {
    const map = new Map<string, CheckItem[]>();
    for (const item of filtered) {
      const list = map.get(item.ref);
      if (list) {
        list.push(item);
      } else {
        map.set(item.ref, [item]);
      }
    }
    return [...map.entries()];
  }, [filtered]);

  const [overrides, setOverrides] = useState<Record<string, boolean>>({});

  const isExpanded = (ref: string, count: number): boolean => {
    const override = overrides[ref];
    if (override !== undefined) return override;
    return count <= DEFAULT_EXPAND_THRESHOLD;
  };

  const toggle = (ref: string, count: number): void => {
    setOverrides((prev) => {
      const prevValue = prev[ref];
      const current =
        prevValue !== undefined ? prevValue : count <= DEFAULT_EXPAND_THRESHOLD;
      return { ...prev, [ref]: !current };
    });
  };

  return (
    <div
      className="flex flex-col"
      style={{ padding: 16, gap: 12, overflowY: "auto", flex: 1, minHeight: 0 }}
    >
      {groups.map(([ref, items]) => {
        const groupProps: GroupProps = {
          refId: ref,
          items,
          expanded: isExpanded(ref, items.length),
          onToggle: () => {
            toggle(ref, items.length);
          },
          disabledRules,
          onToggleRule,
          isMutating,
        };
        if (severityOverride) groupProps.severityOverride = severityOverride;
        if (onSetSeverity) groupProps.onSetSeverity = onSetSeverity;
        if (onResetSeverity) groupProps.onResetSeverity = onResetSeverity;
        if (onFixWithAi) groupProps.onFixWithAi = onFixWithAi;
        if (onIgnoreFinding) groupProps.onIgnoreFinding = onIgnoreFinding;
        if (isIgnoringFinding !== undefined)
          groupProps.isIgnoringFinding = isIgnoringFinding;
        if (onGoToSource) groupProps.onGoToSource = onGoToSource;
        return <Group key={ref} {...groupProps} />;
      })}
      {filtered.length === 0 && (
        <div className="dim" style={{ padding: 24, textAlign: "center" }}>
          {t("checks.noneInCategory")}
        </div>
      )}
    </div>
  );
};

type GroupProps = {
  refId: string;
  items: readonly CheckItem[];
  expanded: boolean;
  onToggle: () => void;
  disabledRules: ReadonlySet<string>;
  onToggleRule: (ruleId: string) => void;
  isMutating: boolean;
  severityOverride?: Record<string, CheckSeverity>;
  onSetSeverity?: (ruleId: string, sev: CheckSeverity) => void;
  onResetSeverity?: (ruleId: string) => void;
  onFixWithAi?: (item: CheckItem) => void;
  onIgnoreFinding?: (item: CheckItem) => void;
  isIgnoringFinding?: boolean;
  onGoToSource?: (item: CheckItem) => void;
};

const Group = ({
  refId,
  items,
  expanded,
  onToggle,
  disabledRules,
  onToggleRule,
  isMutating,
  severityOverride,
  onSetSeverity,
  onResetSeverity,
  onFixWithAi,
  onIgnoreFinding,
  isIgnoringFinding,
  onGoToSource,
}: GroupProps) => {
  const { t } = useTranslation("documents");
  const count = items.length;
  const groupSev = worstSeverity(items);
  // All items in a group share the same rule_id, so they always share the
  // rule title — pick from the first item.
  const title = items[0]?.title ?? refId;
  const skippedReason = items[0]?.skippedReason;
  const SevIc = SEV_ICON[groupSev];
  const isSkipped = groupSev === "skipped";
  // A passed or skipped rule has no per-occurrence rows worth expanding — the
  // header IS the whole story, so the group is inert: no chevron, no
  // expansion, a status label instead of a violation count.
  const isPassed = groupSev === "ok" || isSkipped;
  // "skipped" has no color token in the ok/warn/err/info palette on purpose —
  // it's neutral, not a graded outcome.
  const sevColor = isSkipped ? "var(--fg-3)" : `var(--c-${groupSev})`;

  return (
    <div
      className="flex flex-col"
      style={{
        // Severity strip runs the full height of the group block — header
        // through items — visually binding the violations to their rule.
        boxShadow: `inset 3px 0 0 ${sevColor}`,
        borderRadius: 6,
        background: "transparent",
      }}
    >
      <button
        type="button"
        onClick={isPassed ? undefined : onToggle}
        className="flex items-center w-full text-left"
        style={{
          padding: "10px 12px 10px 14px",
          gap: 12,
          background: "transparent",
          border: "none",
          cursor: isPassed ? "default" : "pointer",
          borderRadius: "6px 6px 0 0",
        }}
        onMouseEnter={(e) => {
          if (!isPassed) e.currentTarget.style.background = "var(--bg-hover)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = "transparent";
        }}
      >
        {!isPassed && (
          <ChevronDown
            size={13}
            style={{
              color: "var(--fg-2)",
              flexShrink: 0,
              transform: expanded ? "rotate(0)" : "rotate(-90deg)",
              transition: "transform 0.15s",
            }}
          />
        )}
        <SevIc
          size={14}
          style={{
            color: sevColor,
            opacity: 0.9,
            flexShrink: 0,
          }}
        />
        <div className="flex-1 flex flex-col min-w-0" style={{ gap: 2 }}>
          <span
            className="truncate"
            style={{
              fontSize: 13,
              fontWeight: 500,
              color: "var(--fg-0)",
              lineHeight: 1.25,
            }}
          >
            {title}
          </span>
          <span
            className="mono dim truncate"
            style={{
              fontSize: 10.5,
              letterSpacing: "0.02em",
              lineHeight: 1.2,
            }}
            title={isSkipped ? skippedReason : undefined}
          >
            {isSkipped && skippedReason ? skippedReason : refId}
          </span>
        </div>
        <span
          className="mono shrink-0"
          style={{
            fontSize: 11,
            fontWeight: 500,
            color: sevColor,
            letterSpacing: "0.03em",
          }}
        >
          {isSkipped
            ? t("checks.skippedLabel")
            : isPassed
              ? t("checks.passedLabel")
              : `${String(count)} ${t("checks.violations", { count })}`}
        </span>
      </button>
      {expanded && !isPassed && (
        <div
          className="flex flex-col"
          style={{
            gap: 2,
            padding: "0 6px 6px 6px",
          }}
        >
          {items.map((c) => {
            const cardProps: Parameters<typeof CheckCard>[0] = {
              item: c,
              onToggleRule,
              isIgnoring: isMutating,
              isIgnored: disabledRules.has(c.ref),
              isMutating,
              isOverriddenSeverity:
                severityOverride !== undefined && c.ref in severityOverride,
            };
            if (onSetSeverity) cardProps.onSetSeverity = onSetSeverity;
            if (onResetSeverity) cardProps.onResetSeverity = onResetSeverity;
            if (onFixWithAi) cardProps.onFixWithAi = onFixWithAi;
            if (onIgnoreFinding) cardProps.onIgnoreFinding = onIgnoreFinding;
            if (isIgnoringFinding !== undefined)
              cardProps.isIgnoringFinding = isIgnoringFinding;
            if (onGoToSource) cardProps.onGoToSource = onGoToSource;
            return <CheckCard key={c.id} {...cardProps} />;
          })}
        </div>
      )}
    </div>
  );
};
