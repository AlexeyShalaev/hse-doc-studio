import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Info, X, XCircle, type LucideIcon } from "lucide-react";
import { clsx } from "clsx";
import type { EditorDiagnostic } from "@shared/ui";

type Severity = EditorDiagnostic["severity"];

const SEV_META: Record<Severity, { icon: LucideIcon; color: string }> = {
  error: { icon: XCircle, color: "var(--c-err)" },
  warning: { icon: AlertTriangle, color: "var(--c-warn)" },
  info: { icon: Info, color: "var(--c-info)" },
};

const SEV_RANK: Record<Severity, number> = { error: 0, warning: 1, info: 2 };

export type DiagnosticsPanelProps = {
  diagnostics: readonly EditorDiagnostic[];
  activeLine: number | undefined;
  onSelect: (line: number) => void;
  onClose: () => void;
};

export const DiagnosticsPanel = ({
  diagnostics,
  activeLine,
  onSelect,
  onClose,
}: DiagnosticsPanelProps) => {
  const { t } = useTranslation("sourceEdit");
  const sorted = useMemo(
    () =>
      [...diagnostics].sort(
        (a, b) =>
          a.line - b.line || SEV_RANK[a.severity] - SEV_RANK[b.severity],
      ),
    [diagnostics],
  );

  return (
    <div
      className="flex flex-col"
      style={{
        height: "11.5rem",
        flexShrink: 0,
        borderTop: "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div
        className="flex items-center justify-between"
        style={{
          padding: "0.375rem 0.5rem 0.375rem 0.75rem",
          borderBottom: "1px solid var(--border)",
          flexShrink: 0,
        }}
      >
        <span
          className="label-up dimmer"
          style={{ fontSize: "0.59375rem", letterSpacing: "0.1em" }}
        >
          {t("panel.title")} · {sorted.length}
        </span>
        <button
          type="button"
          className="icon-btn sm tt"
          data-tt={t("panel.hide")}
          onClick={onClose}
        >
          <X size="0.75rem" />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "0.25rem 0" }}>
        {sorted.length === 0 ? (
          <div
            className="dim"
            style={{ padding: "0.875rem", fontSize: "0.75rem" }}
          >
            {t("panel.empty")}
          </div>
        ) : (
          sorted.map((d, index) => {
            const meta = SEV_META[d.severity];
            const Icon = meta.icon;
            const isActive = activeLine === d.line;
            return (
              <button
                key={`${String(d.line)}-${d.source ?? "?"}-${String(index)}`}
                type="button"
                className={clsx("flex items-center w-full text-left row-btn")}
                style={{
                  gap: "0.5625rem",
                  padding: "0.3125rem 0.75rem",
                  borderRadius: 0,
                  background: isActive ? "var(--bg-hover)" : "transparent",
                }}
                onClick={() => {
                  onSelect(d.line);
                }}
                title={d.message}
              >
                <Icon
                  size="0.8125rem"
                  style={{ color: meta.color, flexShrink: 0, opacity: 0.9 }}
                />
                <span
                  className="mono shrink-0"
                  style={{
                    fontSize: "0.65625rem",
                    color: meta.color,
                    minWidth: "2.75rem",
                    letterSpacing: "0.02em",
                  }}
                >
                  {t("panel.line", { line: d.line })}
                </span>
                <span
                  className="flex-1 truncate"
                  style={{ fontSize: "0.75rem", color: "var(--fg-0)" }}
                >
                  {d.message}
                </span>
                {d.source && (
                  <span
                    className="mono dimmer shrink-0"
                    style={{ fontSize: "0.625rem" }}
                  >
                    {d.source}
                  </span>
                )}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
};
