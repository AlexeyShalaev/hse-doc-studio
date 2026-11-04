import { useState, type ComponentType } from "react";
import { useTranslation } from "react-i18next";
import { MonitorCog, Store, UploadCloud } from "lucide-react";
import { GoogleFontsSource } from "./GoogleFontsSource";
import { SystemFontsSource } from "./SystemFontsSource";
import { UploadFontsSource } from "./UploadFontsSource";

type FontSource = "google" | "system" | "upload";

type SourceTab = {
  id: FontSource;
  labelKey: string;
  icon: ComponentType<{ size?: number | string }>;
};

const SOURCES: SourceTab[] = [
  { id: "system", labelKey: "fonts.sourceSystem", icon: MonitorCog },
  { id: "google", labelKey: "fonts.sourceGoogle", icon: Store },
  { id: "upload", labelKey: "fonts.sourceUpload", icon: UploadCloud },
];

export const FontBrowser = () => {
  const { t } = useTranslation("settings");
  const [source, setSource] = useState<FontSource>("system");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div>
        <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>
          {t("fonts.addTitle")}
        </span>
      </div>

      {/* Source segmented control */}
      <div
        className="flex"
        style={{
          gap: "0.125rem",
          padding: "0.1875rem",
          borderRadius: "0.5rem",
          background: "var(--bg-2)",
          border: "1px solid var(--border)",
        }}
        role="tablist"
      >
        {SOURCES.map(({ id, labelKey, icon: Icon }) => {
          const active = source === id;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => {
                setSource(id);
              }}
              className="flex items-center justify-center"
              style={{
                flex: 1,
                gap: "0.375rem",
                padding: "0.4375rem 0.625rem",
                borderRadius: "0.375rem",
                border: "none",
                fontSize: "0.75rem",
                fontWeight: active ? 600 : 500,
                cursor: "pointer",
                color: active ? "var(--fg-0)" : "var(--fg-2)",
                background: active ? "var(--bg-0, var(--bg-1))" : "transparent",
                boxShadow: active ? "0 1px 2px rgba(0,0,0,0.08)" : "none",
              }}
            >
              <Icon size="0.875rem" />
              {t(labelKey)}
            </button>
          );
        })}
      </div>

      {source === "google" && <GoogleFontsSource />}
      {source === "system" && <SystemFontsSource />}
      {source === "upload" && <UploadFontsSource />}
    </div>
  );
};
