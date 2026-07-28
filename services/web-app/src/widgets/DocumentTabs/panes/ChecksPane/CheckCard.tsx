import {
  AlertTriangle,
  CheckCircle,
  CircleSlash,
  Eye,
  ExternalLink,
  EyeOff,
  Info,
  MinusCircle,
  Sparkles,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { clsx } from "clsx";
import { SeverityMenu } from "@entities/checks";
import { EditorIcon, openInEditor, useEditors } from "@entities/system";
import type { CheckSeverity } from "@shared/api/types";
import type { CheckItem, Severity } from "./types";

const SEV_ICON: Record<Severity, LucideIcon> = {
  ok: CheckCircle,
  warn: AlertTriangle,
  err: XCircle,
  info: Info,
  // Neutral grey — distinct from the ok/warn/err palette; this is not a
  // finding, it's a rule that couldn't run against a custom document.
  skipped: MinusCircle,
};

export type CheckCardProps = {
  item: CheckItem;
  // Toggle the rule's ignored state for this document. When `isIgnored`, the
  // row is dimmed but this control stays live so the user can re-enable it.
  onToggleRule?: (ruleId: string) => void;
  isIgnoring?: boolean;
  isIgnored?: boolean;

  isOverriddenSeverity?: boolean;
  onSetSeverity?: (ruleId: string, sev: CheckSeverity) => void;
  onResetSeverity?: (ruleId: string) => void;
  isMutating?: boolean;
  // Hand this finding to the agent (open chat with a prepared fix prompt).
  onFixWithAi?: (item: CheckItem) => void;
  // Suppress THIS occurrence (not the whole rule) by inserting a `% hse-noqa`
  // comment on its source line. Requires the finding to carry file + line.
  onIgnoreFinding?: (item: CheckItem) => void;
  isIgnoringFinding?: boolean;
  // Jump to the in-app editor at this finding's line (caller routes main-file
  // findings to «Исходник» and others to «Файлы проекта»).
  onGoToSource?: (item: CheckItem) => void;
};

// Compact "hit" row inside a group. The rule title and rule_id are shown once
// in the group header, so this row carries only the per-occurrence info:
// severity icon, line number, and inline actions. No card chrome, no body
// duplication.
export const CheckCard = ({
  item,
  onToggleRule,
  isIgnoring,
  isIgnored,
  isOverriddenSeverity,
  onSetSeverity,
  onResetSeverity,
  isMutating,
  onFixWithAi,
  onIgnoreFinding,
  isIgnoringFinding,
  onGoToSource,
}: CheckCardProps) => {
  const { t } = useTranslation("documents");
  const Ic = SEV_ICON[item.sev];
  const { data: editorsData } = useEditors();
  const editors = editorsData?.editors ?? [];
  const availableEditors = editors.filter((e) => e.available);
  const canOpenInEditor =
    item.absolutePath != null && availableEditors.length > 0;
  const isSingleEditor = availableEditors.length === 1;

  // When the rule is ignored the whole row reads as muted and its per-finding
  // actions go inert — but the eye toggle must stay live so the user can turn
  // the rule back on. Opacity on one shared wrapper would dim the toggle too,
  // so the dim is scoped to this inner region; the toggle sits outside it.
  const dimStyle: CSSProperties = isIgnored
    ? { opacity: 0.4, pointerEvents: "none" }
    : {};
  const isSkipped = item.sev === "skipped";
  // "skipped" has no color token in the ok/warn/err/info palette on purpose —
  // it's neutral, not a graded outcome.
  const sevColor = isSkipped ? "var(--fg-3)" : `var(--c-${item.sev})`;

  return (
    <div
      className="flex items-center transition-colors"
      style={{
        gap: 8,
        padding: "6px 10px 6px 12px",
        borderRadius: 6,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "var(--bg-hover)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
      }}
    >
      <div
        className="flex items-center"
        style={{ gap: 10, flex: 1, minWidth: 0, ...dimStyle }}
      >
        <Ic
          size={14}
          style={{
            color: sevColor,
            flexShrink: 0,
            opacity: 0.9,
          }}
        />
        <div
          className="flex flex-col"
          style={{
            flex: 1,
            minWidth: 0,
            gap: isSkipped && item.skippedReason ? 1 : 0,
          }}
        >
          <span
            className="truncate"
            style={{
              fontSize: 12.5,
              fontWeight: 500,
              color: "var(--fg-0)",
            }}
            title={item.title}
          >
            {item.title}
          </span>
          {isSkipped && item.skippedReason && (
            <span
              className="truncate"
              style={{ fontSize: 11, color: "var(--fg-3)" }}
              title={item.skippedReason}
            >
              {item.skippedReason}
            </span>
          )}
        </div>
        {item.line != null &&
          (onGoToSource ? (
            <button
              type="button"
              className="mono shrink-0 tt tt-end"
              data-tt={t("checks.card.openAtLine", { line: item.line })}
              onClick={() => {
                onGoToSource(item);
              }}
              style={{
                fontSize: 11,
                fontWeight: 500,
                color: sevColor,
                letterSpacing: "0.02em",
                background: "transparent",
                border: "none",
                borderBottom:
                  "1px dashed color-mix(in oklab, currentColor 45%, transparent)",
                cursor: "pointer",
                padding: 0,
              }}
            >
              :{item.line}
            </button>
          ) : (
            <span
              className="mono shrink-0"
              style={{
                fontSize: 11,
                fontWeight: 500,
                color: sevColor,
                opacity: 0.85,
                letterSpacing: "0.02em",
              }}
              title={t("checks.card.line", { line: item.line })}
            >
              :{item.line}
            </span>
          ))}

        {/* Overriding severity on a skipped rule is meaningless — it wasn't
            graded at all, there's nothing to promote/demote. */}
        {onSetSeverity && !isSkipped && (
          <SeverityMenu
            severity={item.sev}
            isOverridden={isOverriddenSeverity ?? false}
            disabled={isMutating ?? false}
            onSet={(sev) => {
              onSetSeverity(item.ref, sev);
            }}
            onReset={() => {
              onResetSeverity?.(item.ref);
            }}
          />
        )}

        {/* No source location for a skipped rule — nothing for the agent to
            fix. */}
        {onFixWithAi && !isSkipped && (
          <button
            type="button"
            className="icon-btn sm tt tt-end"
            data-tt={t("checks.card.fixWithAi")}
            onClick={() => {
              onFixWithAi(item);
            }}
            style={{ background: "transparent", color: "var(--accent)" }}
          >
            <Sparkles size={12} />
          </button>
        )}

        {onIgnoreFinding && item.file != null && item.line != null && (
          <button
            type="button"
            className="icon-btn sm tt tt-end"
            data-tt={t("checks.card.ignoreFinding")}
            disabled={isIgnoringFinding ?? false}
            onClick={() => {
              onIgnoreFinding(item);
            }}
            style={{ background: "transparent" }}
          >
            <CircleSlash size={12} />
          </button>
        )}

        {canOpenInEditor && item.absolutePath && (
          <>
            {isSingleEditor ? (
              <button
                type="button"
                className="icon-btn sm tt tt-end"
                data-tt={t("checks.card.openInEditorNamed", {
                  editor:
                    availableEditors[0]?.label ??
                    t("checks.card.editorFallback"),
                })}
                onClick={() => {
                  const editor = availableEditors[0];
                  if (editor) {
                    openInEditor(
                      editor.scheme,
                      item.absolutePath!,
                      item.line ?? 1,
                    );
                  }
                }}
                style={{ background: "transparent" }}
              >
                <ExternalLink size={12} />
              </button>
            ) : (
              <DropdownMenu.Root>
                <DropdownMenu.Trigger asChild>
                  <button
                    type="button"
                    className="icon-btn sm tt tt-end"
                    data-tt={t("checks.card.openInEditor")}
                    style={{ background: "transparent" }}
                  >
                    <ExternalLink size={12} />
                  </button>
                </DropdownMenu.Trigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.Content
                    className={clsx(
                      "z-50 min-w-[12rem] overflow-hidden rounded-r-3 border border-border bg-bg-1",
                      "shadow-elev-pop",
                      "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
                      "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
                      "origin-top-right",
                    )}
                    sideOffset={6}
                    align="end"
                  >
                    {availableEditors.map((e) => (
                      <DropdownMenu.Item
                        key={e.id}
                        className={clsx(
                          "flex cursor-pointer select-none items-center gap-2 outline-none",
                          "focus:bg-bg-hover",
                        )}
                        style={{ padding: "8px 12px" }}
                        onSelect={() => {
                          openInEditor(
                            e.scheme,
                            item.absolutePath!,
                            item.line ?? 1,
                          );
                        }}
                      >
                        <span style={{ color: "var(--fg-0)" }}>
                          <EditorIcon editorId={e.id} size={14} />
                        </span>
                        <span style={{ fontSize: 12.5 }}>{e.label}</span>
                      </DropdownMenu.Item>
                    ))}
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>
            )}
          </>
        )}
      </div>

      {onToggleRule && (
        <button
          type="button"
          className="icon-btn sm tt tt-end"
          data-tt={
            isIgnored
              ? t("checks.card.enableRuleBack")
              : t("checks.card.ignoreRuleInDocument")
          }
          disabled={isIgnoring ?? false}
          onClick={() => {
            onToggleRule(item.ref);
          }}
          style={{
            background: "transparent",
            ...(isIgnored ? { color: "var(--accent)" } : {}),
          }}
        >
          {isIgnored ? <Eye size={12} /> : <EyeOff size={12} />}
        </button>
      )}
    </div>
  );
};
