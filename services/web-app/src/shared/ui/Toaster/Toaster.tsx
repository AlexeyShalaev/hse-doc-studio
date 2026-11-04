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
        // Внизу справа, над строкой состояния: сверху уведомление закрывало
        // кнопку синхронизации и открытую под ней панель, а именно о них оно и сообщает.
        bottom: "2.5rem",
        right: "1rem",
        zIndex: 200,
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
        maxWidth: "23.75rem",
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
              padding: "0.75rem",
              gap: "0.625rem",
              display: "flex",
              alignItems: "flex-start",
              borderColor: color,
              background: SOFT_BY_KIND[t.kind],
              boxShadow: "var(--shadow-2)",
              minWidth: "17.5rem",
              pointerEvents: "auto",
            }}
          >
            <Icon
              size="0.875rem"
              style={{ color, marginTop: 1, flexShrink: 0 }}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              {t.title && (
                <div
                  style={{
                    fontSize: "0.78125rem",
                    fontWeight: 600,
                    marginBottom: "0.125rem",
                    color,
                  }}
                >
                  {t.title}
                </div>
              )}
              <div
                style={{
                  fontSize: "0.75rem",
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
                  style={{ marginTop: "0.5rem" }}
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
              <X size="0.6875rem" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
