import { useTranslation } from "react-i18next";
import { Check, Cpu, Download, Sparkles, Zap } from "lucide-react";
import type { CatalogModel } from "@entities/ai-runtime";

const NOTE_COLOR = (m: CatalogModel): string => {
  if (m.on_gpu) return "var(--c-ok)";
  if (m.runnable) return "var(--c-warn)";
  return "var(--fg-2)";
};

export type ModelRowProps = {
  model: CatalogModel;
  installed: boolean;
  disabled: boolean;
  disabledReason?: string | undefined;
  onInstall: () => void;
};

export const ModelRow = ({
  model,
  installed,
  disabled,
  disabledReason,
  onInstall,
}: ModelRowProps) => {
  const { t } = useTranslation("localRuntime");
  return (
    <div
      className="flex items-center justify-between"
      style={{
        gap: "0.75rem",
        padding: "0.625rem 0.75rem",
        borderRadius: "0.375rem",
        border: model.recommended
          ? "1px solid var(--accent)"
          : "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div className="flex flex-col" style={{ gap: "0.25rem", minWidth: 0 }}>
        <div
          className="flex items-center"
          style={{ gap: "0.5rem", flexWrap: "wrap" }}
        >
          <span style={{ fontSize: "0.78125rem", fontWeight: 500 }}>
            {model.label}
          </span>
          <span className="mono dim" style={{ fontSize: "0.65625rem" }}>
            {model.name}
          </span>
          <span
            className="mono"
            style={{
              fontSize: "0.625rem",
              padding: "1px 0.375rem",
              borderRadius: "0.1875rem",
              background: "var(--bg-3)",
              color: "var(--fg-2)",
            }}
          >
            {t("modelRow.sizeGb", { size: model.size_gb })}
          </span>
          {model.recommended && (
            <span
              className="flex items-center"
              style={{
                gap: "0.1875rem",
                fontSize: "0.625rem",
                color: "var(--accent)",
              }}
            >
              <Sparkles size="0.6875rem" /> {t("modelRow.recommended")}
            </span>
          )}
        </div>
        <div className="dim" style={{ fontSize: "0.6875rem" }}>
          {model.tasks.join(" · ")}
        </div>
        <div
          className="flex items-center"
          style={{
            gap: "0.3125rem",
            fontSize: "0.6875rem",
            color: NOTE_COLOR(model),
          }}
        >
          {model.on_gpu ? <Zap size="0.6875rem" /> : <Cpu size="0.6875rem" />}
          <span>{model.note}</span>
        </div>
      </div>
      <div
        className="flex items-center"
        style={{ gap: "0.375rem", flexShrink: 0 }}
      >
        {installed ? (
          <span
            className="flex items-center"
            style={{
              gap: "0.25rem",
              fontSize: "0.6875rem",
              color: "var(--c-ok)",
            }}
          >
            <Check size="0.75rem" /> {t("modelRow.installed")}
          </span>
        ) : (
          <button
            type="button"
            className="btn xs"
            onClick={onInstall}
            disabled={disabled}
            title={
              disabled
                ? (disabledReason ?? t("modelRow.unavailable"))
                : t("modelRow.installTitle")
            }
          >
            <Download size="0.6875rem" />
            {t("modelRow.install")}
          </button>
        )}
      </div>
    </div>
  );
};
