import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { z } from "zod";
import {
  type ProjectResponseSchema,
  useProjectCheckRules,
  useUpdateProject,
} from "@entities/project";
import { RulesView } from "@entities/checks";
import type {
  CheckRuleResponse,
  ChecksOverrideDto,
  CheckSeverity,
} from "@shared/api/types";
import { SectionCard } from "./SectionCard";

type Project = z.infer<typeof ProjectResponseSchema>;

export type ProjectChecksSectionProps = {
  project: Project;
};

// Project-level rules management — mirrors document-level UI from ChecksPane
// but mutates project.checks_override instead of document.checks_override.
// Reuses the same RulesView with project-scoped handlers.
export const ProjectChecksSection = ({
  project,
}: ProjectChecksSectionProps) => {
  const { t } = useTranslation("workspace");
  const { data: rulesData, isLoading } = useProjectCheckRules(project.id);
  const { mutate: updateProject, isPending: isMutating } = useUpdateProject();

  // The backend replaces the full `checks_override` on each PATCH — every
  // mutation must merge with the current value or unrelated overrides get
  // wiped. Same pattern as ChecksPane.
  const currentOverride: Required<ChecksOverrideDto> = useMemo(
    () => ({
      disabled_categories: project.checks_override?.disabled_categories ?? [],
      disabled: project.checks_override?.disabled ?? [],
      enabled: project.checks_override?.enabled ?? [],
      severity_override: project.checks_override?.severity_override ?? {},
    }),
    [project.checks_override],
  );

  const updateOverride = (patch: Partial<ChecksOverrideDto>) => {
    updateProject({
      id: project.id,
      data: { checks_override: { ...currentOverride, ...patch } },
    });
  };

  const disabledCategories = useMemo(
    () => new Set(currentOverride.disabled_categories),
    [currentOverride.disabled_categories],
  );

  const handleToggleRule = (ruleId: string, currentlyEnabled: boolean) => {
    if (currentlyEnabled) {
      updateOverride({
        disabled: [...currentOverride.disabled, ruleId],
        enabled: currentOverride.enabled.filter((id) => id !== ruleId),
      });
    } else {
      updateOverride({
        disabled: currentOverride.disabled.filter((id) => id !== ruleId),
        enabled: [...new Set([...currentOverride.enabled, ruleId])],
      });
    }
  };

  const handleSetSeverity = (ruleId: string, severity: CheckSeverity) => {
    updateOverride({
      severity_override: {
        ...currentOverride.severity_override,
        [ruleId]: severity,
      },
    });
  };

  const handleResetSeverity = (ruleId: string) => {
    const { [ruleId]: _omit, ...rest } = currentOverride.severity_override;
    updateOverride({ severity_override: rest });
  };

  const handleToggleCategory = (category: string) => {
    const next = disabledCategories.has(category)
      ? currentOverride.disabled_categories.filter((c) => c !== category)
      : [...currentOverride.disabled_categories, category];
    updateOverride({ disabled_categories: next });
  };

  const handleToggleSource = (
    ruleIds: readonly string[],
    anyEnabled: boolean,
  ) => {
    const idSet = new Set(ruleIds);
    if (anyEnabled) {
      updateOverride({
        disabled: [...new Set([...currentOverride.disabled, ...ruleIds])],
        enabled: currentOverride.enabled.filter((id) => !idSet.has(id)),
      });
    } else {
      updateOverride({
        disabled: currentOverride.disabled.filter((id) => !idSet.has(id)),
        enabled: [...new Set([...currentOverride.enabled, ...ruleIds])],
      });
    }
  };

  const rulesBySource = useMemo<
    readonly (readonly [string, readonly CheckRuleResponse[]])[]
  >(() => {
    const grouped = new Map<string, CheckRuleResponse[]>();
    for (const r of rulesData ?? []) {
      const list = grouped.get(r.source) ?? [];
      list.push(r);
      grouped.set(r.source, list);
    }
    return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [rulesData]);

  const categoriesWithCounts = useMemo<
    readonly (readonly [string, number])[]
  >(() => {
    const counts = new Map<string, number>();
    for (const r of rulesData ?? []) {
      if (r.category) {
        counts.set(r.category, (counts.get(r.category) ?? 0) + 1);
      }
    }
    return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [rulesData]);

  return (
    <SectionCard title={t("projectChecks.title")} fullSpan>
      <span className="dim" style={{ fontSize: 12 }}>
        {t("projectChecks.subtitle")}
      </span>
      <div
        style={{
          margin: "0 -18px -18px",
          padding: 0,
          maxHeight: 600,
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
      >
        {isLoading ? (
          <div className="dim" style={{ padding: 24, textAlign: "center" }}>
            {t("projectChecks.loading")}
          </div>
        ) : (
          <RulesView
            rulesBySource={rulesBySource}
            categoriesWithCounts={categoriesWithCounts}
            disabledCategories={disabledCategories}
            severityOverride={currentOverride.severity_override}
            isMutating={isMutating}
            onToggleCategory={handleToggleCategory}
            onToggleSource={handleToggleSource}
            onToggleRule={handleToggleRule}
            onSetSeverity={handleSetSeverity}
            onResetSeverity={handleResetSeverity}
          />
        )}
      </div>
    </SectionCard>
  );
};
