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
        height: 184,
        flexShrink: 0,
        borderTop: "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div
        className="flex items-center justify-between"
        style={{
          padding: "6px 8px 6px 12px",
          borderBottom: "1px solid var(--border)",
          flexShrink: 0,
        }}
      >
        <span
          className="label-up dimmer"
          style={{ fontSize: 9.5, letterSpacing: "0.1em" }}
        >
          {t("panel.title")} · {sorted.length}
        </span>
        <button
          type="button"
          className="icon-btn sm tt"
          data-tt={t("panel.hide")}
          onClick={onClose}
        >
          <X size={12} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "4px 0" }}>
        {sorted.length === 0 ? (
          <div className="dim" style={{ padding: 14, fontSize: 12 }}>
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
                  gap: 9,
                  padding: "5px 12px",
                  borderRadius: 0,
                  background: isActive ? "var(--bg-hover)" : "transparent",
                }}
                onClick={() => {
                  onSelect(d.line);
                }}
                title={d.message}
              >
                <Icon
                  size={13}
                  style={{ color: meta.color, flexShrink: 0, opacity: 0.9 }}
                />
                <span
                  className="mono shrink-0"
                  style={{
                    fontSize: 10.5,
                    color: meta.color,
                    minWidth: 44,
                    letterSpacing: "0.02em",
                  }}
                >
                  {t("panel.line", { line: d.line })}
                </span>
                <span
                  className="flex-1 truncate"
                  style={{ fontSize: 12, color: "var(--fg-0)" }}
                >
                  {d.message}
                </span>
                {d.source && (
                  <span
                    className="mono dimmer shrink-0"
                    style={{ fontSize: 10 }}
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
