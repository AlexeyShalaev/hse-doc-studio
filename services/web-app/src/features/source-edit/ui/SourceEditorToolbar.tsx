import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Code,
  Eye,
  FileText,
  Info,
  Lock,
  MessageSquareWarning,
  RefreshCw,
  Save,
  WrapText,
  XCircle,
} from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import type { SourceEditorMode } from "@shared/lib";
import type { EditorStats } from "@shared/ui";

export type SaveStatus = "saved" | "dirty" | "saving" | "error";

export type DiagnosticCounts = {
  error: number;
  warning: number;
  info: number;
};

const STATUS_META: Record<SaveStatus, { color: string }> = {
  saved: { color: "var(--c-ok)" },
  dirty: { color: "var(--c-warn)" },
  saving: { color: "var(--fg-2)" },
  error: { color: "var(--c-err)" },
};

export type SourceEditorToolbarProps = {
  relativePath: string;
  readOnly: boolean;
  readOnlyReason: string | undefined;
  status: SaveStatus;
  counts: DiagnosticCounts;
  /** Show the «Код | Визуальный» switch (LaTeX documents only). */
  modeAvailable: boolean;
  mode: SourceEditorMode;
  onModeChange: (mode: SourceEditorMode) => void;
  wrapLines: boolean;
  onToggleWrap: () => void;
  inlineDiagnostics: boolean;
  onToggleInline: () => void;
  panelOpen: boolean;
  onTogglePanel: () => void;
  onPrevProblem: () => void;
  onNextProblem: () => void;
  isDirty: boolean;
  onSave: () => void;
  /** Live word/char/caret stats (null until the editor reports them). */
  stats?: EditorStats | null;
};

export const SourceEditorToolbar = ({
  relativePath,
  readOnly,
  readOnlyReason,
  status,
  counts,
  modeAvailable,
  mode,
  onModeChange,
  wrapLines,
  onToggleWrap,
  inlineDiagnostics,
  onToggleInline,
  panelOpen,
  onTogglePanel,
  onPrevProblem,
  onNextProblem,
  isDirty,
  onSave,
  stats,
}: SourceEditorToolbarProps) => {
  const { t } = useTranslation("sourceEdit");
  const st = STATUS_META[status];
  const total = counts.error + counts.warning + counts.info;
  const parts = relativePath.split("/");
  const fileName = parts.pop() ?? relativePath;
  const directory = parts.join("/");

  return (
    <div className="source-editor-toolbar">
      <div className="source-editor-identity">
        <span className="source-editor-file-icon" aria-hidden="true">
          <FileText size={14} />
        </span>
        <span className="source-editor-file-copy">
          <span className="source-editor-file-name" title={relativePath}>
            {fileName}
          </span>
          {directory && (
            <span className="source-editor-file-path" title={relativePath}>
              {directory}
            </span>
          )}
        </span>
        {readOnly && (
          <span
            className="chip tt source-editor-readonly"
            data-tt={readOnlyReason ?? t("toolbar.readOnlyDefault")}
          >
            <Lock size={10} />
            {t("toolbar.readOnly")}
          </span>
        )}
        {stats && (
          <span
            className="source-editor-stats tt"
            data-tt={t("toolbar.statsTooltip")}
          >
            <span>
              {stats.selectedChars > 0
                ? t("toolbar.statsSelected", {
                    words: stats.selectedWords,
                    chars: stats.selectedChars,
                  })
                : t("toolbar.statsTotal", {
                    words: stats.words,
                    chars: stats.chars,
                  })}
            </span>
            <span className="source-editor-caret-stat">
              {t("toolbar.statsCaret", {
                line: stats.line,
                column: stats.column,
              })}
            </span>
          </span>
        )}
      </div>

      <div className="source-editor-actions">
        {modeAvailable && (
          <div
            className="source-mode-switch"
            role="group"
            aria-label={t("toolbar.mode.label")}
          >
            <button
              type="button"
              className={clsx(mode === "visual" && "active")}
              aria-pressed={mode === "visual"}
              onClick={() => {
                onModeChange("visual");
              }}
            >
              <Eye size={13} />
              <span>{t("toolbar.mode.visual")}</span>
            </button>
            <button
              type="button"
              className={clsx(mode === "code" && "active")}
              aria-pressed={mode === "code"}
              onClick={() => {
                onModeChange("code");
              }}
            >
              <Code size={13} />
              <span>{t("toolbar.mode.code")}</span>
            </button>
          </div>
        )}

        {total > 0 && (
          <div
            className="source-editor-diagnostics-actions"
            role="group"
            aria-label={t("toolbar.diagnosticsLabel")}
          >
            <button
              type="button"
              className={clsx(
                "source-editor-issue-count tt",
                panelOpen && "active",
              )}
              data-tt={t("toolbar.togglePanel")}
              aria-label={t("toolbar.togglePanel")}
              aria-pressed={panelOpen}
              onClick={onTogglePanel}
            >
              {counts.error > 0 && (
                <span style={{ color: "var(--c-err)" }}>
                  <XCircle size={12} />
                  {counts.error}
                </span>
              )}
              {counts.warning > 0 && (
                <span style={{ color: "var(--c-warn)" }}>
                  <AlertTriangle size={12} />
                  {counts.warning}
                </span>
              )}
              {counts.error === 0 && counts.warning === 0 && (
                <span style={{ color: "var(--c-info)" }}>
                  <Info size={12} />
                  {counts.info}
                </span>
              )}
            </button>
            <button
              type="button"
              className="icon-btn sm tt"
              data-tt={t("toolbar.prevProblem")}
              aria-label={t("toolbar.prevProblem")}
              onClick={onPrevProblem}
            >
              <ChevronUp size={14} />
            </button>
            <button
              type="button"
              className="icon-btn sm tt"
              data-tt={t("toolbar.nextProblem")}
              aria-label={t("toolbar.nextProblem")}
              onClick={onNextProblem}
            >
              <ChevronDown size={14} />
            </button>
            <button
              type="button"
              className={clsx("icon-btn sm tt", inlineDiagnostics && "active")}
              data-tt={t("toolbar.inlineMessages")}
              aria-label={t("toolbar.inlineMessages")}
              aria-pressed={inlineDiagnostics}
              onClick={onToggleInline}
            >
              <MessageSquareWarning size={13} />
            </button>
          </div>
        )}

        {mode !== "visual" && (
          <button
            type="button"
            className={clsx("icon-btn sm tt", wrapLines && "active")}
            data-tt={t("toolbar.wrapLines")}
            aria-label={t("toolbar.wrapLines")}
            aria-pressed={wrapLines}
            onClick={onToggleWrap}
          >
            <WrapText size={13} />
          </button>
        )}

        <span
          className="source-editor-save-status"
          style={{ color: st.color }}
          role="status"
          aria-live="polite"
        >
          {status === "saving" ? (
            <RefreshCw size={11} className="spin" />
          ) : status === "saved" ? (
            <Check size={12} />
          ) : status === "error" ? (
            <AlertTriangle size={12} />
          ) : (
            <span className="source-editor-dirty-dot" />
          )}
          <span>{t(`toolbar.status.${status}`)}</span>
        </span>

        {!readOnly && (
          <button
            type="button"
            className="btn sm source-editor-save-button tt"
            data-tt={t("toolbar.saveTooltip")}
            aria-label={t("toolbar.saveTooltip")}
            onClick={onSave}
            disabled={!isDirty}
          >
            <Save size={12} />
            <span>{t("toolbar.save")}</span>
          </button>
        )}
      </div>
    </div>
  );
};
