import { useTranslation } from "react-i18next";
import { Check, Download } from "lucide-react";
import type { RegistryModel } from "@entities/ai-runtime";

export type RegistryModelRowProps = {
  model: RegistryModel;
  installed: boolean;
  busy: boolean;
  onInstall: () => void;
};

export const RegistryModelRow = ({
  model,
  installed,
  busy,
  onInstall,
}: RegistryModelRowProps) => {
  const { t } = useTranslation("localRuntime");
  return (
    <div
      className="flex items-center justify-between"
      style={{
        gap: 12,
        padding: "10px 12px",
        borderRadius: 6,
        border: "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div className="flex flex-col" style={{ gap: 4, minWidth: 0 }}>
        <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
          <span className="mono" style={{ fontSize: 12.5, fontWeight: 500 }}>
            {model.name}
          </span>
          {model.pulls && (
            <span className="dim" style={{ fontSize: 10.5 }}>
              ↓ {model.pulls}
            </span>
          )}
          {model.capabilities.map((cap) => (
            <span
              key={cap}
              className="mono"
              style={{
                fontSize: 10,
                padding: "1px 6px",
                borderRadius: 3,
                background: "var(--bg-3)",
                color: "var(--fg-2)",
              }}
            >
              {cap}
            </span>
          ))}
        </div>
        {model.description && (
          <div className="dim" style={{ fontSize: 11 }}>
            {model.description}
          </div>
        )}
      </div>
      <div className="flex items-center" style={{ gap: 6, flexShrink: 0 }}>
        {installed ? (
          <span
            className="flex items-center"
            style={{ gap: 4, fontSize: 11, color: "var(--c-ok)" }}
          >
            <Check size={12} /> {t("registryRow.installed")}
          </span>
        ) : (
          <button
            type="button"
            className="btn xs"
            onClick={onInstall}
            disabled={busy}
            title={t("registryRow.installLatestTitle")}
          >
            <Download size={11} />
            {t("registryRow.install")}
          </button>
        )}
      </div>
    </div>
  );
};
