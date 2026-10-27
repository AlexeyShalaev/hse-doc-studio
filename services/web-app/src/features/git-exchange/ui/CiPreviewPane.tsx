import { FileCode2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CiPreview } from "@entities/git-sync";
import { Notice } from "@shared/ui/ConflictKit";
import { CodeEditor } from "@shared/ui/CodeEditor";
import { CopyField } from "@shared/ui/CopyField";
import { Spinner } from "@shared/ui/Spinner";
import { ciFileState, type CiFileState } from "../model/ciOptions";
import { CheckRow } from "./CheckRow";
import { CopyButton } from "./CopyButton";

export type CiPreviewPaneProps = {
  preview: CiPreview | null;
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
  /** Настройки не годятся для файла: предпросмотр не считается. */
  invalid: boolean;
  overwrite: boolean;
  onOverwriteChange: (value: boolean) => void;
  /** В проекте есть файлы под NDA: сборка на чужом сервисе их выдаст третьим лицам. */
  hasNda: boolean;
  ndaAck: boolean;
  onNdaAckChange: (value: boolean) => void;
  disabled?: boolean;
};

const STATE_COLOR: Record<CiFileState, string> = {
  new: "var(--c-ok)",
  same: "var(--c-info)",
  differs: "var(--c-warn)",
};

// Правая часть окна автосборки: путь файла и его состояние в проекте, сам файл
// (только чтение), подтверждения замены и NDA, команда для сборки у себя.
export const CiPreviewPane = ({
  preview,
  isLoading,
  error,
  onRetry,
  invalid,
  overwrite,
  onOverwriteChange,
  hasNda,
  ndaAck,
  onNdaAckChange,
  disabled = false,
}: CiPreviewPaneProps) => {
  const { t } = useTranslation("gitExchange");
  const file = preview?.files[0] ?? null;
  const state = file ? ciFileState(file) : null;

  if (!file && invalid) {
    return (
      <div
        className="flex flex-col items-center justify-center dim"
        style={{
          flex: 1,
          minHeight: 260,
          gap: 8,
          textAlign: "center",
          fontSize: 12.5,
          borderRadius: "var(--r-3)",
          border: "1px dashed var(--border-strong)",
        }}
        data-testid="ci-preview-invalid"
      >
        <FileCode2 size={22} aria-hidden="true" />
        {t("ci.preview.invalid")}
      </div>
    );
  }
  if (!file) {
    if (error !== null) {
      return (
        <Notice
          tone="err"
          role="alert"
          text={error === "" ? t("ci.preview.failed") : error}
          action={
            <button type="button" className="btn xs" onClick={onRetry}>
              {t("ci.preview.retry")}
            </button>
          }
        />
      );
    }
    return (
      <div
        className="flex items-center justify-center dim"
        style={{ flex: 1, minHeight: 260, gap: 8, fontSize: 12.5 }}
        role="status"
        data-testid="ci-preview-loading"
      >
        <Spinner size="sm" />
        {t("ci.preview.loading")}
      </div>
    );
  }

  return (
    <div className="flex flex-col" style={{ gap: 12, minWidth: 0 }}>
      <div className="flex items-center" style={{ gap: 8, minWidth: 0 }}>
        <FileCode2
          size={14}
          aria-hidden="true"
          style={{ color: "var(--fg-2)" }}
        />
        <span
          className="mono truncate"
          title={file.path}
          style={{ flex: 1, minWidth: 0, fontSize: 12.5 }}
          data-testid="ci-path"
        >
          {file.path}
        </span>
        {isLoading && <Spinner size="sm" />}
        {state && (
          <span
            className="badge"
            data-testid={`ci-state-${state}`}
            style={{ color: STATE_COLOR[state], fontSize: 11 }}
          >
            {t(`ci.state.${state}`)}
          </span>
        )}
        <CopyButton value={file.content} label={t("ci.preview.copy")} />
      </div>

      <div
        data-testid="ci-yaml"
        aria-busy={isLoading}
        style={{
          height: 280,
          display: "flex",
          flexDirection: "column",
          borderRadius: "var(--r-2)",
          border: "1px solid var(--border)",
          overflow: "hidden",
          opacity: isLoading ? 0.6 : 1,
          transition: "opacity 120ms",
        }}
      >
        <CodeEditor
          value={file.content}
          readOnly
          wrapLines
          language="yaml"
          inlineDiagnostics={false}
          ariaLabel={t("ci.preview.editorLabel", { path: file.path })}
        />
      </div>

      {error !== null && (
        <Notice
          tone="err"
          role="alert"
          text={error === "" ? t("ci.preview.failed") : error}
          action={
            <button type="button" className="btn xs" onClick={onRetry}>
              {t("ci.preview.retry")}
            </button>
          }
        />
      )}

      {state === "same" && (
        <Notice tone="info" role="status" text={t("ci.exists.same")} />
      )}
      {state === "differs" && (
        <div className="flex flex-col" style={{ gap: 8 }}>
          <Notice tone="warn" role="status" text={t("ci.exists.differs")} />
          <CheckRow
            checked={overwrite}
            disabled={disabled}
            onChange={onOverwriteChange}
            testId="ci-overwrite"
          >
            {t("ci.exists.overwrite")}
          </CheckRow>
        </div>
      )}

      {hasNda && (
        <div className="flex flex-col" style={{ gap: 8 }}>
          <Notice tone="warn" role="status" text={t("ci.nda.warning")} />
          <CheckRow
            checked={ndaAck}
            disabled={disabled}
            onChange={onNdaAckChange}
            testId="ci-nda"
          >
            {t("ci.nda.ack")}
          </CheckRow>
        </div>
      )}

      {preview && preview.notes.length > 0 && (
        <ul
          className="dim"
          style={{
            margin: 0,
            paddingLeft: 18,
            fontSize: 11.5,
            lineHeight: 1.55,
          }}
        >
          {preview.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      {preview && preview.command !== "" && (
        <div className="flex flex-col" style={{ gap: 6 }}>
          <span style={{ fontSize: 12, fontWeight: 500 }}>
            {t("ci.local.title")}
          </span>
          <CopyField value={preview.command} label={t("ci.local.title")} />
          <span className="dim" style={{ fontSize: 11.5, lineHeight: 1.5 }}>
            {t("ci.local.hint")}
          </span>
        </div>
      )}
    </div>
  );
};
