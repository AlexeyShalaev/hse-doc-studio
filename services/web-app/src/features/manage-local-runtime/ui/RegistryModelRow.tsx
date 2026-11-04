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
        gap: "0.75rem",
        padding: "0.625rem 0.75rem",
        borderRadius: "0.375rem",
        border: "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div className="flex flex-col" style={{ gap: "0.25rem", minWidth: 0 }}>
        <div
          className="flex items-center"
          style={{ gap: "0.5rem", flexWrap: "wrap" }}
        >
          <span
            className="mono"
            style={{ fontSize: "0.78125rem", fontWeight: 500 }}
          >
            {model.name}
          </span>
          {model.pulls && (
            <span className="dim" style={{ fontSize: "0.65625rem" }}>
              ↓ {model.pulls}
            </span>
          )}
          {model.capabilities.map((cap) => (
            <span
              key={cap}
              className="mono"
              style={{
                fontSize: "0.625rem",
                padding: "1px 0.375rem",
                borderRadius: "0.1875rem",
                background: "var(--bg-3)",
                color: "var(--fg-2)",
              }}
            >
              {cap}
            </span>
          ))}
        </div>
        {model.description && (
          <div className="dim" style={{ fontSize: "0.6875rem" }}>
            {model.description}
          </div>
        )}
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
            <Check size="0.75rem" /> {t("registryRow.installed")}
          </span>
        ) : (
          <button
            type="button"
            className="btn xs"
            onClick={onInstall}
            disabled={busy}
            title={t("registryRow.installLatestTitle")}
          >
            <Download size="0.6875rem" />
            {t("registryRow.install")}
          </button>
        )}
      </div>
    </div>
  );
};
