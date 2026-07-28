import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  Check,
  CircleSlash,
  EyeOff,
  Info,
  RotateCcw,
  Sparkles,
  Wand2,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
import type { CheckSeverity } from "@shared/api/types";
import type { EditorDiagnostic } from "@shared/ui";

export type DiagnosticActions = {
  onFixWithAi: (diagnostic: EditorDiagnostic) => void;
  onIgnoreRule: (ruleId: string) => void;
  onSetSeverity: (ruleId: string, severity: CheckSeverity) => void;
  onResetSeverity: (ruleId: string) => void;
  severityOverride: Record<string, CheckSeverity>;
  /** Apply a deterministic one-click fix (typography etc.), when present. */
  onApplyFix?: (diagnostic: EditorDiagnostic) => void;
  /** Suppress just this occurrence via a `% hse-noqa` comment in the source. */
  onIgnoreFinding?: (diagnostic: EditorDiagnostic) => void;
};

type DiagnosticActionMenuProps = {
  left: number;
  top: number;
  items: readonly EditorDiagnostic[];
  actions: DiagnosticActions;
  onClose: () => void;
};

const MENU_WIDTH = 304;

const SEV_META: Record<
  EditorDiagnostic["severity"],
  { icon: LucideIcon; color: string }
> = {
  error: { icon: XCircle, color: "var(--c-err)" },
  warning: { icon: AlertTriangle, color: "var(--c-warn)" },
  info: { icon: Info, color: "var(--c-info)" },
};

const EDITOR_TO_CHECK_SEV: Record<EditorDiagnostic["severity"], CheckSeverity> =
  {
    error: "err",
    warning: "warn",
    info: "info",
  };

const SEVERITY_OPTIONS: CheckSeverity[] = ["err", "warn", "info"];

export const DiagnosticActionMenu = ({
  left,
  top,
  items,
  actions,
  onClose,
}: DiagnosticActionMenuProps) => {
  const { t } = useTranslation("sourceEdit");
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const x = Math.max(8, Math.min(left, window.innerWidth - MENU_WIDTH - 8));
  const y = Math.min(top + 4, window.innerHeight - 16);

  return (
    <>
      <div
        onMouseDown={onClose}
        style={{ position: "fixed", inset: 0, zIndex: 60 }}
      />
      <div
        className="flex flex-col"
        style={{
          position: "fixed",
          left: x,
          top: y,
          width: MENU_WIDTH,
          maxHeight: "min(60vh, 420px)",
          overflowY: "auto",
          zIndex: 61,
          background: "var(--bg-1)",
          border: "1px solid var(--border)",
          borderRadius: "var(--r-3)",
          boxShadow: "var(--shadow-pop, 0 12px 40px rgba(0,0,0,0.45))",
          padding: 4,
        }}
        onMouseDown={(event) => {
          event.stopPropagation();
        }}
      >
        {items.map((d, index) => {
          const ruleId = d.source;
          const meta = SEV_META[d.severity];
          const Icon = meta.icon;
          const currentSev = EDITOR_TO_CHECK_SEV[d.severity];
          const isOverridden =
            ruleId != null && ruleId in actions.severityOverride;
          return (
            <div
              key={`${String(d.line)}-${ruleId ?? "?"}-${String(index)}`}
              className="flex flex-col"
              style={{
                gap: 4,
                padding: 6,
                borderTop: index > 0 ? "1px solid var(--border)" : undefined,
              }}
            >
              <div
                className="flex items-start gap-2"
                style={{ padding: "2px 4px" }}
              >
                <Icon
                  size={13}
                  style={{ color: meta.color, flexShrink: 0, marginTop: 1 }}
                />
                <div className="flex flex-col min-w-0" style={{ gap: 1 }}>
                  <span
                    style={{
                      fontSize: 12.5,
                      color: "var(--fg-0)",
                      lineHeight: 1.3,
                    }}
                  >
                    {d.message}
                  </span>
                  {ruleId && (
                    <span className="mono dimmer" style={{ fontSize: 10 }}>
                      {t("actionMenu.ruleLine", { ruleId, line: d.line })}
                    </span>
                  )}
                </div>
              </div>

              {d.fix && actions.onApplyFix && (
                <button
                  type="button"
                  className="row-btn"
                  style={{ gap: 8, color: "var(--c-ok)" }}
                  onClick={() => {
                    actions.onApplyFix?.(d);
                    onClose();
                  }}
                >
                  <Wand2 size={13} style={{ flexShrink: 0 }} />
                  <span>{d.fix.title ?? t("actionMenu.applyFix")}</span>
                </button>
              )}

              <button
                type="button"
                className="row-btn"
                style={{ gap: 8, color: "var(--accent)" }}
                onClick={() => {
                  actions.onFixWithAi(d);
                  onClose();
                }}
              >
                <Sparkles size={13} style={{ flexShrink: 0 }} />
                <span>{t("actionMenu.fixWithAi")}</span>
              </button>

              {ruleId && (
                <>
                  <div
                    className="flex items-center"
                    style={{ gap: 5, padding: "2px 8px", flexWrap: "wrap" }}
                  >
                    <span className="dimmer" style={{ fontSize: 11 }}>
                      {t("actionMenu.severity")}
                    </span>
                    {SEVERITY_OPTIONS.map((opt) => {
                      const active = opt === currentSev;
                      if (active) {
                        return (
                          <span
                            key={opt}
                            className={clsx("sev", opt)}
                            title={t("actionMenu.currentSeverity")}
                            style={{
                              minWidth: 56,
                              justifyContent: "center",
                              gap: 3,
                              fontWeight: 700,
                              boxShadow: `0 0 0 1.5px var(--c-${opt})`,
                            }}
                          >
                            <Check size={10} />
                            {opt.toUpperCase()}
                          </span>
                        );
                      }
                      return (
                        <button
                          key={opt}
                          type="button"
                          className={clsx("sev", opt)}
                          title={t("actionMenu.changeSeverity", {
                            severity: opt.toUpperCase(),
                          })}
                          style={{
                            minWidth: 56,
                            justifyContent: "center",
                            cursor: "pointer",
                            opacity: 0.45,
                          }}
                          onClick={() => {
                            actions.onSetSeverity(ruleId, opt);
                            onClose();
                          }}
                        >
                          {opt.toUpperCase()}
                        </button>
                      );
                    })}
                    {isOverridden && (
                      <button
                        type="button"
                        className="icon-btn sm tt"
                        data-tt={t("actionMenu.resetSeverity")}
                        onClick={() => {
                          actions.onResetSeverity(ruleId);
                          onClose();
                        }}
                      >
                        <RotateCcw size={11} />
                      </button>
                    )}
                  </div>

                  {actions.onIgnoreFinding && (
                    <button
                      type="button"
                      className="row-btn"
                      style={{ gap: 8 }}
                      onClick={() => {
                        actions.onIgnoreFinding?.(d);
                        onClose();
                      }}
                    >
                      <CircleSlash size={13} style={{ flexShrink: 0 }} />
                      <span>{t("actionMenu.ignoreFinding")}</span>
                    </button>
                  )}

                  <button
                    type="button"
                    className="row-btn"
                    style={{ gap: 8 }}
                    onClick={() => {
                      actions.onIgnoreRule(ruleId);
                      onClose();
                    }}
                  >
                    <EyeOff size={13} style={{ flexShrink: 0 }} />
                    <span>{t("actionMenu.ignoreRule")}</span>
                  </button>
                </>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
};
