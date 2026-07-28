import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useToastStore, type ToastKind } from "@shared/lib";

const ICON_BY_KIND = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: AlertCircle,
} satisfies Record<ToastKind, typeof Info>;

const COLOR_BY_KIND: Record<ToastKind, string> = {
  info: "var(--c-info)",
  success: "var(--c-ok)",
  warning: "var(--c-warn)",
  error: "var(--c-err)",
};

const SOFT_BY_KIND: Record<ToastKind, string> = {
  info: "var(--c-info-soft)",
  success: "var(--c-ok-soft)",
  warning: "var(--c-warn-soft)",
  error: "var(--c-err-soft)",
};

export const Toaster = () => {
  const { t: translate } = useTranslation("uiPrimitives");
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: 16,
        right: 16,
        zIndex: 200,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        maxWidth: 380,
        pointerEvents: "none",
      }}
      aria-live="polite"
    >
      {toasts.map((t) => {
        const Icon = ICON_BY_KIND[t.kind];
        const color = COLOR_BY_KIND[t.kind];
        return (
          <div
            key={t.id}
            className="card scale-in"
            role="alert"
            style={{
              padding: 12,
              gap: 10,
              display: "flex",
              alignItems: "flex-start",
              borderColor: color,
              background: SOFT_BY_KIND[t.kind],
              boxShadow: "var(--shadow-2)",
              minWidth: 280,
              pointerEvents: "auto",
            }}
          >
            <Icon size={14} style={{ color, marginTop: 1, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              {t.title && (
                <div
                  style={{
                    fontSize: 12.5,
                    fontWeight: 600,
                    marginBottom: 2,
                    color,
                  }}
                >
                  {t.title}
                </div>
              )}
              <div
                style={{
                  fontSize: 12,
                  lineHeight: 1.4,
                  wordBreak: "break-word",
                  color: "var(--fg-0)",
                }}
              >
                {t.message}
              </div>
              {t.action && (
                <button
                  type="button"
                  className="btn xs"
                  style={{ marginTop: 8 }}
                  onClick={() => {
                    t.action?.onClick();
                    dismiss(t.id);
                  }}
                >
                  {t.action.label}
                </button>
              )}
            </div>
            <button
              type="button"
              className="icon-btn sm"
              onClick={() => {
                dismiss(t.id);
              }}
              aria-label={translate("toaster.close")}
            >
              <X size={11} />
            </button>
          </div>
        );
      })}
    </div>
  );
};
