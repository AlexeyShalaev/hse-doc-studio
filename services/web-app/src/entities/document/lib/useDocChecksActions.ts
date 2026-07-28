import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import type { ChecksOverrideDto, CheckSeverity } from "@shared/api/types";
import { useDocument, useUpdateDocument } from "../api/documentQueries";

export type DocChecksActions = {
  currentOverride: Required<ChecksOverrideDto>;
  /** Replace the full override with the current state plus `patch`. */
  updateOverride: (
    patch: Partial<ChecksOverrideDto>,
    options?: { onSuccessToast?: string },
  ) => void;
  ignoreRule: (ruleId: string) => void;
  /**
   * Flip a rule's ignored state for this document: disable it if active, or
   * re-enable it (force-enable, so it survives a disabled category) if ignored.
   */
  toggleRule: (ruleId: string) => void;
  setSeverity: (ruleId: string, severity: CheckSeverity) => void;
  resetSeverity: (ruleId: string) => void;
  severityOverride: Record<string, CheckSeverity>;
  isPending: boolean;
};

/**
 * Per-document `checks_override` mutations (ignore rule, override/reset
 * severity), shared between the «Проверки» tab and the editor's inline
 * finding menu. The backend replaces the whole `checks_override` on each
 * PATCH, so every mutation sends the full current state plus the delta.
 */
export const useDocChecksActions = (
  projectId: string,
  docId: string,
): DocChecksActions => {
  const { t } = useTranslation("documents");
  const { data: doc } = useDocument(projectId, docId);
  const { mutate: updateDocument, isPending } = useUpdateDocument();

  const currentOverride = useMemo<Required<ChecksOverrideDto>>(
    () => ({
      disabled_categories: doc?.checks_override?.disabled_categories ?? [],
      disabled: doc?.checks_override?.disabled ?? [],
      enabled: doc?.checks_override?.enabled ?? [],
      severity_override: doc?.checks_override?.severity_override ?? {},
    }),
    [doc?.checks_override],
  );

  const updateOverride = useCallback(
    (
      patch: Partial<ChecksOverrideDto>,
      options?: { onSuccessToast?: string },
    ) => {
      updateDocument(
        {
          projectId,
          docId,
          data: { checks_override: { ...currentOverride, ...patch } },
        },
        options?.onSuccessToast
          ? { onSuccess: () => toast.info(options.onSuccessToast ?? "") }
          : undefined,
      );
    },
    [projectId, docId, currentOverride, updateDocument],
  );

  const ignoreRule = useCallback(
    (ruleId: string) => {
      if (currentOverride.disabled.includes(ruleId)) return;
      updateOverride(
        { disabled: [...currentOverride.disabled, ruleId] },
        { onSuccessToast: t("checksActions.ruleDisabled", { ruleId }) },
      );
    },
    [currentOverride.disabled, updateOverride, t],
  );

  const toggleRule = useCallback(
    (ruleId: string) => {
      if (currentOverride.disabled.includes(ruleId)) {
        // Re-enable: drop from `disabled` AND add to `enabled`. The explicit
        // `enabled` entry force-enables the rule even when its category sits in
        // `disabled_categories` (symmetric with handleToggleRule in «Правила»).
        updateOverride(
          {
            disabled: currentOverride.disabled.filter((id) => id !== ruleId),
            enabled: [...new Set([...currentOverride.enabled, ruleId])],
          },
          { onSuccessToast: t("checksActions.ruleEnabled", { ruleId }) },
        );
      } else {
        updateOverride(
          {
            disabled: [...currentOverride.disabled, ruleId],
            enabled: currentOverride.enabled.filter((id) => id !== ruleId),
          },
          { onSuccessToast: t("checksActions.ruleDisabled", { ruleId }) },
        );
      }
    },
    [currentOverride.disabled, currentOverride.enabled, updateOverride, t],
  );

  const setSeverity = useCallback(
    (ruleId: string, severity: CheckSeverity) => {
      updateOverride({
        severity_override: {
          ...currentOverride.severity_override,
          [ruleId]: severity,
        },
      });
    },
    [currentOverride.severity_override, updateOverride],
  );

  const resetSeverity = useCallback(
    (ruleId: string) => {
      const { [ruleId]: _omit, ...rest } = currentOverride.severity_override;
      updateOverride({ severity_override: rest });
    },
    [currentOverride.severity_override, updateOverride],
  );

  return {
    currentOverride,
    updateOverride,
    ignoreRule,
    toggleRule,
    setSeverity,
    resetSeverity,
    severityOverride: currentOverride.severity_override,
    isPending,
  };
};
