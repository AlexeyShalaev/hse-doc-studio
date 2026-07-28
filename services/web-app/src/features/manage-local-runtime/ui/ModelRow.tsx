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
        gap: 12,
        padding: "10px 12px",
        borderRadius: 6,
        border: model.recommended
          ? "1px solid var(--accent)"
          : "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div className="flex flex-col" style={{ gap: 4, minWidth: 0 }}>
        <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 12.5, fontWeight: 500 }}>{model.label}</span>
          <span className="mono dim" style={{ fontSize: 10.5 }}>
            {model.name}
          </span>
          <span
            className="mono"
            style={{
              fontSize: 10,
              padding: "1px 6px",
              borderRadius: 3,
              background: "var(--bg-3)",
              color: "var(--fg-2)",
            }}
          >
            {t("modelRow.sizeGb", { size: model.size_gb })}
          </span>
          {model.recommended && (
            <span
              className="flex items-center"
              style={{ gap: 3, fontSize: 10, color: "var(--accent)" }}
            >
              <Sparkles size={11} /> {t("modelRow.recommended")}
            </span>
          )}
        </div>
        <div className="dim" style={{ fontSize: 11 }}>
          {model.tasks.join(" · ")}
        </div>
        <div
          className="flex items-center"
          style={{ gap: 5, fontSize: 11, color: NOTE_COLOR(model) }}
        >
          {model.on_gpu ? <Zap size={11} /> : <Cpu size={11} />}
          <span>{model.note}</span>
        </div>
      </div>
      <div className="flex items-center" style={{ gap: 6, flexShrink: 0 }}>
        {installed ? (
          <span
            className="flex items-center"
            style={{ gap: 4, fontSize: 11, color: "var(--c-ok)" }}
          >
            <Check size={12} /> {t("modelRow.installed")}
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
            <Download size={11} />
            {t("modelRow.install")}
          </button>
        )}
      </div>
    </div>
  );
};
