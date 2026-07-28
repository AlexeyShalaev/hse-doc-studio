import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, Upload } from "lucide-react";
import { useAIProviders } from "@entities/ai-provider";
import { toast } from "@shared/lib";
import { useExportData } from "../model/useExportData";
import { useImportData } from "../model/useImportData";
import type {
  ExportBundle,
  ImportRequest,
  MergeStrategy,
} from "../api/exportImportApi";

type ExportMode = "plain" | "encrypted";

const headingStyle: React.CSSProperties = {
  margin: 0,
  fontSize: 14,
  fontWeight: 600,
  color: "var(--fg-0)",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 11,
  fontWeight: 600,
  color: "var(--fg-2)",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  marginBottom: 8,
};

const fieldStyle: React.CSSProperties = {
  background: "var(--bg-0)",
  border: "1px solid var(--border)",
  borderRadius: "var(--r-2)",
  padding: "7px 10px",
  fontSize: 12,
  color: "var(--fg-0)",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const choiceRow: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  fontSize: 12.5,
  cursor: "pointer",
  color: "var(--fg-1)",
};

// Minimal shape guard so we reject a non-bundle JSON before POSTing it.
const looksLikeBundle = (data: unknown): data is ExportBundle => {
  if (typeof data !== "object" || data === null) return false;
  const obj = data as Record<string, unknown>;
  return typeof obj.encrypted === "boolean" && Array.isArray(obj.ai_providers);
};

export const ExportImportSection = () => {
  const { t } = useTranslation("exportImport");
  const [includeSettings, setIncludeSettings] = useState(true);
  const [includeProviders, setIncludeProviders] = useState(true);
  const [includePersonas, setIncludePersonas] = useState(true);
  const [exportMode, setExportMode] = useState<ExportMode>("plain");
  const [exportPassword, setExportPassword] = useState("");

  const [mergeStrategy, setMergeStrategy] = useState<MergeStrategy>("skip");
  const [pendingBundle, setPendingBundle] = useState<ExportBundle | null>(null);
  const [importPassword, setImportPassword] = useState("");

  const fileInputRef = useRef<HTMLInputElement>(null);

  const exportMutation = useExportData();
  const importMutation = useImportData();
  const { data: providers } = useAIProviders();

  const nothingSelected =
    !includeSettings && !includeProviders && !includePersonas;

  // Encryption only protects provider API keys. With none in the export there is
  // nothing to encrypt — and an "encrypted" bundle with no ciphertext would
  // accept any password on import. So we gate the option on having a real key.
  const exportableKeyCount = (providers ?? []).filter(
    (p) => p.type !== "ollama" && p.has_api_key,
  ).length;
  const canEncrypt = includeProviders && exportableKeyCount > 0;
  const effectiveMode: ExportMode = canEncrypt ? exportMode : "plain";

  const modeHint =
    effectiveMode === "encrypted"
      ? t("export.hintEncrypted")
      : t("export.hintPlain");
  const typeHint = canEncrypt ? modeHint : t("export.hintNothingToEncrypt");

  const handleExport = () => {
    if (nothingSelected) {
      toast.error(t("toast.selectWhatToExport"));
      return;
    }
    if (effectiveMode === "encrypted" && !exportPassword) {
      toast.error(t("toast.enterEncryptionPassword"));
      return;
    }
    exportMutation.mutate(
      {
        include_settings: includeSettings,
        include_ai_providers: includeProviders,
        include_agent_personas: includePersonas,
        encryption_password:
          effectiveMode === "encrypted" ? exportPassword : null,
      },
      {
        onSuccess: () => {
          toast.success(
            effectiveMode === "encrypted"
              ? t("toast.fileSavedEncrypted")
              : t("toast.fileSaved"),
          );
          setExportPassword("");
        },
      },
    );
  };

  const runImport = (bundle: ExportBundle, password: string | null) => {
    const request: ImportRequest = {
      ...bundle,
      merge_strategy: mergeStrategy,
      decryption_password: password,
    };
    importMutation.mutate(request, {
      onSuccess: (result) => {
        const parts = [
          result.settings_imported ? t("toast.resultSettings") : null,
          t("toast.resultProviders", {
            imported: result.ai_providers_imported,
            skipped: result.ai_providers_skipped,
          }),
          t("toast.resultPersonas", {
            imported: result.agent_personas_imported,
            skipped: result.agent_personas_skipped,
          }),
        ].filter((p): p is string => p !== null);
        if (result.errors.length > 0) {
          toast.warning(
            result.errors.join("; "),
            t("toast.importWithErrorsTitle"),
          );
        } else {
          toast.success(parts.join(" · "), t("toast.importDoneTitle"));
        }
        setImportPassword("");
        setPendingBundle(null);
      },
    });
  };

  const handleFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Reset the input so picking the same file again re-fires onChange.
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = typeof e.target?.result === "string" ? e.target.result : "";
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch {
        toast.error(t("toast.readFileError"));
        return;
      }
      if (!looksLikeBundle(parsed)) {
        toast.error(t("toast.notAnExportFile"));
        return;
      }
      if (parsed.encrypted) {
        setPendingBundle(parsed);
        toast.info(t("toast.encryptedFileHint"));
        return;
      }
      runImport(parsed, null);
    };
    reader.readAsText(file);
  };

  const handleDecryptImport = () => {
    if (!pendingBundle) return;
    if (!importPassword) {
      toast.error(t("toast.enterDecryptionPassword"));
      return;
    }
    runImport(pendingBundle, importPassword);
  };

  return (
    <div className="flex flex-col" style={{ gap: 20 }}>
      {/* ── Export ─────────────────────────────────────────────── */}
      <div
        id="data-export"
        className="flex flex-col settings-anchor"
        style={{ gap: 12 }}
      >
        <h4 style={headingStyle}>{t("export.heading")}</h4>
        <p style={{ margin: 0, fontSize: 12, color: "var(--fg-2)" }}>
          {t("export.description")}
        </p>

        <div>
          <span style={labelStyle}>{t("export.includeLabel")}</span>
          <div className="flex flex-col" style={{ gap: 8 }}>
            <label style={choiceRow}>
              <input
                type="checkbox"
                checked={includeSettings}
                onChange={(e) => {
                  setIncludeSettings(e.target.checked);
                }}
              />
              {t("export.includeSettings")}
            </label>
            <label style={choiceRow}>
              <input
                type="checkbox"
                checked={includeProviders}
                onChange={(e) => {
                  setIncludeProviders(e.target.checked);
                }}
              />
              {t("export.includeProviders")}
            </label>
            <label style={choiceRow}>
              <input
                type="checkbox"
                checked={includePersonas}
                onChange={(e) => {
                  setIncludePersonas(e.target.checked);
                }}
              />
              {t("export.includePersonas")}
            </label>
          </div>
        </div>

        <div>
          <span style={labelStyle}>{t("export.typeLabel")}</span>
          <div className="flex" style={{ gap: 16, marginBottom: 6 }}>
            <label style={choiceRow}>
              <input
                type="radio"
                name="exportMode"
                checked={effectiveMode === "plain"}
                onChange={() => {
                  setExportMode("plain");
                  setExportPassword("");
                }}
              />
              {t("export.modePlain")}
            </label>
            <label
              style={{
                ...choiceRow,
                ...(canEncrypt
                  ? {}
                  : { color: "var(--fg-3)", cursor: "not-allowed" }),
              }}
            >
              <input
                type="radio"
                name="exportMode"
                checked={effectiveMode === "encrypted"}
                disabled={!canEncrypt}
                onChange={() => {
                  setExportMode("encrypted");
                }}
              />
              {t("export.modeEncrypted")}
            </label>
          </div>
          <p style={{ margin: 0, fontSize: 11, color: "var(--fg-3)" }}>
            {typeHint}
          </p>
        </div>

        {effectiveMode === "encrypted" && (
          <div>
            <span style={labelStyle}>{t("export.passwordLabel")}</span>
            <input
              type="password"
              value={exportPassword}
              onChange={(e) => {
                setExportPassword(e.target.value);
              }}
              placeholder={t("export.passwordPlaceholder")}
              style={fieldStyle}
            />
          </div>
        )}

        <div>
          <button
            type="button"
            className="btn primary"
            onClick={handleExport}
            disabled={exportMutation.isPending || nothingSelected}
          >
            <Download size={13} />
            {exportMutation.isPending
              ? t("export.downloadButtonPending")
              : t("export.downloadButton")}
          </button>
        </div>
      </div>

      <div style={{ height: 1, background: "var(--border)" }} />

      {/* ── Import ─────────────────────────────────────────────── */}
      <div
        id="data-import"
        className="flex flex-col settings-anchor"
        style={{ gap: 12 }}
      >
        <h4 style={headingStyle}>{t("import.heading")}</h4>
        <p style={{ margin: 0, fontSize: 12, color: "var(--fg-2)" }}>
          {t("import.description")}
        </p>

        <div>
          <span style={labelStyle}>{t("import.mergeLabel")}</span>
          <select
            value={mergeStrategy}
            onChange={(e) => {
              setMergeStrategy(e.target.value as MergeStrategy);
            }}
            style={fieldStyle}
          >
            <option value="skip">{t("import.mergeSkip")}</option>
            <option value="replace">{t("import.mergeReplace")}</option>
          </select>
        </div>

        {pendingBundle?.encrypted && (
          <div
            className="flex flex-col"
            style={{
              gap: 8,
              padding: 10,
              background: "var(--bg-2)",
              borderRadius: "var(--r-2)",
            }}
          >
            <span style={labelStyle}>{t("import.decryptPasswordLabel")}</span>
            <input
              type="password"
              value={importPassword}
              onChange={(e) => {
                setImportPassword(e.target.value);
              }}
              placeholder={t("import.decryptPasswordPlaceholder")}
              style={fieldStyle}
            />
            <div>
              <button
                type="button"
                className="btn primary"
                onClick={handleDecryptImport}
                disabled={importMutation.isPending}
              >
                {importMutation.isPending
                  ? t("import.decryptButtonPending")
                  : t("import.decryptButton")}
              </button>
            </div>
          </div>
        )}

        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            onChange={handleFile}
            style={{ display: "none" }}
          />
          <button
            type="button"
            className="btn"
            onClick={() => {
              fileInputRef.current?.click();
            }}
            disabled={importMutation.isPending}
          >
            <Upload size={13} />
            {importMutation.isPending
              ? t("import.pickFileButtonPending")
              : t("import.pickFileButton")}
          </button>
        </div>
      </div>
    </div>
  );
};
