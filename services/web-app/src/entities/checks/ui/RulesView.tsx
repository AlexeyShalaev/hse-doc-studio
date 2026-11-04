import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { pickLocalized } from "@shared/lib";
import type { CheckRuleResponse, CheckSeverity } from "@shared/api/types";
import { SeverityMenu } from "./SeverityMenu";
import { formatSource } from "../lib/formatSource";

export type RulesViewProps = {
  rulesBySource: readonly (readonly [string, readonly CheckRuleResponse[]])[];
  categoriesWithCounts: readonly (readonly [string, number])[];
  disabledCategories: ReadonlySet<string>;
  severityOverride: Record<string, CheckSeverity>;
  isMutating: boolean;
  onToggleCategory: (category: string) => void;
  onToggleSource: (ruleIds: readonly string[], anyEnabled: boolean) => void;
  onToggleRule: (ruleId: string, currentlyEnabled: boolean) => void;
  onSetSeverity: (ruleId: string, severity: CheckSeverity) => void;
  onResetSeverity: (ruleId: string) => void;
};

export const RulesView = ({
  rulesBySource,
  categoriesWithCounts,
  disabledCategories,
  severityOverride,
  isMutating,
  onToggleCategory,
  onToggleSource,
  onToggleRule,
  onSetSeverity,
  onResetSeverity,
}: RulesViewProps) => {
  const { t } = useTranslation("checks");
  return (
    <div
      className="flex flex-col"
      style={{
        padding: "1rem",
        gap: "1rem",
        overflowY: "auto",
        flex: 1,
        minHeight: 0,
      }}
    >
      {categoriesWithCounts.length > 0 && (
        <CategoryChips
          categoriesWithCounts={categoriesWithCounts}
          disabledCategories={disabledCategories}
          isMutating={isMutating}
          onToggle={onToggleCategory}
        />
      )}

      {rulesBySource.length === 0 && (
        <div className="dim" style={{ padding: "1.5rem", textAlign: "center" }}>
          {t("rules.empty")}
        </div>
      )}

      {rulesBySource.map(([source, rules]) => (
        <SourceGroup
          key={source}
          source={source}
          rules={rules}
          severityOverride={severityOverride}
          isMutating={isMutating}
          onToggleSource={onToggleSource}
          onToggleRule={onToggleRule}
          onSetSeverity={onSetSeverity}
          onResetSeverity={onResetSeverity}
        />
      ))}
    </div>
  );
};

type CategoryChipsProps = {
  categoriesWithCounts: readonly (readonly [string, number])[];
  disabledCategories: ReadonlySet<string>;
  isMutating: boolean;
  onToggle: (category: string) => void;
};

const CategoryChips = ({
  categoriesWithCounts,
  disabledCategories,
  isMutating,
  onToggle,
}: CategoryChipsProps) => {
  const { t } = useTranslation("checks");
  return (
    <div className="flex flex-col" style={{ gap: "0.375rem" }}>
      <span
        className="label-up dimmer"
        style={{ fontSize: "0.59375rem", letterSpacing: "0.1em" }}
      >
        {t("rules.categories")}
      </span>
      <div className="flex flex-wrap" style={{ gap: "0.375rem" }}>
        {categoriesWithCounts.map(([cat, count]) => {
          const off = disabledCategories.has(cat);
          return (
            <button
              key={cat}
              type="button"
              className={clsx("chip", off ? "subtle" : "accent")}
              style={{
                cursor: "pointer",
                opacity: off ? 0.55 : 1,
                textDecoration: off ? "line-through" : "none",
              }}
              disabled={isMutating}
              onClick={() => {
                onToggle(cat);
              }}
              title={
                off ? t("rules.enableCategory") : t("rules.disableCategory")
              }
            >
              {cat}
              <span className="mono dim" style={{ fontSize: "0.59375rem" }}>
                {count}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

type SourceGroupProps = {
  source: string;
  rules: readonly CheckRuleResponse[];
  severityOverride: Record<string, CheckSeverity>;
  isMutating: boolean;
  onToggleSource: (ruleIds: readonly string[], anyEnabled: boolean) => void;
  onToggleRule: (ruleId: string, currentlyEnabled: boolean) => void;
  onSetSeverity: (ruleId: string, severity: CheckSeverity) => void;
  onResetSeverity: (ruleId: string) => void;
};

const SourceGroup = ({
  source,
  rules,
  severityOverride,
  isMutating,
  onToggleSource,
  onToggleRule,
  onSetSeverity,
  onResetSeverity,
}: SourceGroupProps) => {
  const { t } = useTranslation("checks");
  const enabledCount = rules.filter((r) => r.enabled).length;
  const anyEnabled = enabledCount > 0;

  return (
    <div className="flex flex-col" style={{ gap: "0.375rem" }}>
      <div
        className="flex items-center justify-between"
        style={{ padding: "0 0.25rem" }}
      >
        <div className="flex items-center" style={{ gap: "0.5rem" }}>
          <span style={{ fontSize: "0.78125rem", fontWeight: 600 }}>
            {formatSource(source, rules[0]?.source_label)}
          </span>
          <span className="mono dimmer" style={{ fontSize: "0.625rem" }}>
            {source}
          </span>
        </div>
        <div className="flex items-center" style={{ gap: "0.625rem" }}>
          <span className="dim" style={{ fontSize: "0.6875rem" }}>
            {enabledCount} / {rules.length}
          </span>
          <button
            type="button"
            className="btn xs ghost"
            disabled={isMutating || rules.length === 0}
            onClick={() => {
              onToggleSource(
                rules.map((r) => r.rule_id),
                anyEnabled,
              );
            }}
          >
            {anyEnabled ? t("rules.disableAll") : t("rules.enableAll")}
          </button>
        </div>
      </div>
      <div className="card flex flex-col" style={{ padding: 0 }}>
        {rules.map((r, idx) => (
          <RuleRow
            key={r.rule_id}
            rule={r}
            isFirst={idx === 0}
            isOverridden={severityOverride[r.rule_id] !== undefined}
            isMutating={isMutating}
            onToggleRule={onToggleRule}
            onSetSeverity={onSetSeverity}
            onResetSeverity={onResetSeverity}
          />
        ))}
      </div>
    </div>
  );
};

type RuleRowProps = {
  rule: CheckRuleResponse;
  isFirst: boolean;
  isOverridden: boolean;
  isMutating: boolean;
  onToggleRule: (ruleId: string, currentlyEnabled: boolean) => void;
  onSetSeverity: (ruleId: string, severity: CheckSeverity) => void;
  onResetSeverity: (ruleId: string) => void;
};

const RuleRow = ({
  rule,
  isFirst,
  isOverridden,
  isMutating,
  onToggleRule,
  onSetSeverity,
  onResetSeverity,
}: RuleRowProps) => {
  const { i18n } = useTranslation();
  return (
    <div
      className="flex items-center"
      style={{
        padding: "0.5625rem 0.75rem",
        gap: "0.75rem",
        borderTop: isFirst ? "none" : "1px solid var(--border)",
        opacity: rule.enabled ? 1 : 0.55,
      }}
    >
      <SeverityMenu
        severity={rule.effective_severity}
        isOverridden={isOverridden}
        disabled={isMutating}
        onSet={(sev) => {
          onSetSeverity(rule.rule_id, sev);
        }}
        onReset={() => {
          onResetSeverity(rule.rule_id);
        }}
      />
      <div className="flex flex-col min-w-0 flex-1" style={{ gap: "0.125rem" }}>
        <span style={{ fontSize: "0.78125rem", fontWeight: 500 }}>
          {pickLocalized(rule.title, i18n.language, rule.rule_id)}
        </span>
        <span className="mono dim" style={{ fontSize: "0.65625rem" }}>
          {rule.rule_id}
        </span>
      </div>
      <span
        role="switch"
        aria-checked={rule.enabled}
        tabIndex={0}
        className={clsx(
          "toggle",
          rule.enabled && "on",
          isMutating && "disabled",
        )}
        onClick={() => {
          if (!isMutating) onToggleRule(rule.rule_id, rule.enabled);
        }}
        onKeyDown={(e) => {
          if (e.key === " " || e.key === "Enter") {
            e.preventDefault();
            if (!isMutating) onToggleRule(rule.rule_id, rule.enabled);
          }
        }}
      />
    </div>
  );
};
