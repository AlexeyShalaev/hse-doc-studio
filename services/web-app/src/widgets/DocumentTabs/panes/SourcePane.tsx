import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Download, FileQuestion } from "lucide-react";
import type { z } from "zod";
import {
  classifyCustomFile,
  getDocMeta,
  useDocChecksActions,
} from "@entities/document";
import type { DocumentResponseSchema } from "@entities/document";
import { buildFixFindingPrompt } from "@entities/checks";
import { SourceEditor, type DiagnosticActions } from "@features/source-edit";
import { env } from "@shared/config";
import { isEditableTextPath, useWorkspaceStore } from "@shared/lib";

type Document = z.infer<typeof DocumentResponseSchema>;

export type SourcePaneProps = {
  projectId: string;
  doc: Document;
};

export const SourcePane = ({ projectId, doc }: SourcePaneProps) => {
  const { t } = useTranslation("documents");
  // Pass the doc so meta.file comes from the API (team-aware path).
  const meta = getDocMeta(doc.id, doc);
  const [searchParams, setSearchParams] = useSearchParams();
  const askAgent = useWorkspaceStore((state) => state.askAgent);
  const { ignoreRule, setSeverity, resetSeverity, severityOverride } =
    useDocChecksActions(projectId, doc.id);

  // A `?line=N` param (set when a finding is clicked in «Проверки») asks the
  // editor to scroll to that line. It's consumed once, then cleared so it
  // doesn't re-fire on every tab switch.
  const lineParam = searchParams.get("line");
  const parsed = lineParam != null ? Number(lineParam) : Number.NaN;
  const revealLine = Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;

  const clearLineParam = useCallback(() => {
    const params = new URLSearchParams(searchParams);
    if (params.has("line")) {
      params.delete("line");
      setSearchParams(params, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // Inline finding menu actions — the same set as the «Проверки» tab.
  const diagnosticActions: DiagnosticActions = useMemo(
    () => ({
      onFixWithAi: (d) => {
        askAgent(
          buildFixFindingPrompt({
            docCode: meta.code,
            docId: doc.id,
            ruleId: d.source ?? "",
            message: d.message,
            file: meta.file,
            line: d.line,
          }),
        );
      },
      onIgnoreRule: ignoreRule,
      onSetSeverity: setSeverity,
      onResetSeverity: resetSeverity,
      severityOverride,
    }),
    [
      askAgent,
      meta.code,
      meta.file,
      doc.id,
      ignoreRule,
      setSeverity,
      resetSeverity,
      severityOverride,
    ],
  );

  const revealProps =
    revealLine != null ? { revealLine, onRevealConsumed: clearLineParam } : {};

  // Binary sources (the pptx presentation variant, or a custom upload in a
  // recognized office/PDF format — the Office/Preview tabs are its real
  // editor/viewer) can't be opened in CodeMirror — offer a download instead.
  // `.html` (reveal variant) IS a text source a student may edit, so it's
  // allowed here even though the FileTree treats built HTML as an opaque
  // artifact. A custom file in an UNRECOGNIZED format has no other tab that
  // can show it at all — same VS-Code-like fallback as PreviewPane: assume
  // it's text and let the user try, rather than refusing outright.
  const customCls =
    doc.custom_file != null ? classifyCustomFile(meta.file) : null;
  const isCustomTextFallback = customCls === "unknown";
  if (
    !isEditableTextPath(meta.file, [".html", ".htm"]) &&
    !isCustomTextFallback
  ) {
    const fileName = meta.file.split("/").pop() ?? meta.file;
    const downloadHref = `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/files/${meta.file}`;
    return (
      <div
        className="flex flex-1 items-center justify-center"
        style={{ padding: 24 }}
      >
        <div
          className="flex flex-col items-center"
          style={{ gap: 12, textAlign: "center", maxWidth: 360 }}
        >
          <FileQuestion size={28} style={{ color: "var(--fg-3)" }} />
          <div className="mono dim" style={{ fontSize: 11.5 }}>
            {meta.file}
          </div>
          <p
            className="dim"
            style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}
          >
            {t("source.binaryHint")}
          </p>
          <a href={downloadHref} className="btn" download={fileName}>
            <Download size={12} />
            {t("source.download")}
          </a>
        </div>
      </div>
    );
  }

  // The document's main .tex, editable. Its check findings (incl. compile-log
  // errors) drive the gutter/inline markers via `docId`.
  return (
    <SourceEditor
      projectId={projectId}
      relativePath={meta.file}
      docId={doc.id}
      diagnosticActions={diagnosticActions}
      {...revealProps}
    />
  );
};
