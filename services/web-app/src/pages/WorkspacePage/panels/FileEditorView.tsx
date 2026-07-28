import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { FileQuestion, FolderTree } from "lucide-react";
import { SourceEditor, useProjectDiagnostics } from "@features/source-edit";
import { isEditablePath, isGeneratedPath } from "@widgets/FileTree";
import { toPosixPath } from "@shared/lib";
import type { EditorDiagnostic } from "@shared/ui";

export type FileEditorViewProps = {
  projectId: string;
};

const NO_DIAGNOSTICS: EditorDiagnostic[] = [];

const EmptyDetail = () => {
  const { t } = useTranslation("workspace");
  return (
    <div
      className="flex flex-1 items-center justify-center"
      style={{ padding: 24 }}
    >
      <div
        className="flex flex-col items-center"
        style={{ gap: 12, textAlign: "center", maxWidth: 320 }}
      >
        <div
          className="flex items-center justify-center"
          style={{
            width: 42,
            height: 42,
            borderRadius: "var(--r-3)",
            background: "var(--bg-2)",
            color: "var(--fg-3)",
            border: "1px solid var(--border)",
          }}
        >
          <FolderTree size={20} />
        </div>
        <h2
          className="dim"
          style={{ margin: 0, fontSize: 15, fontWeight: 600 }}
        >
          {t("files.editorTitle")}
        </h2>
        <p className="dim" style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}>
          {t("files.editorHint")}
        </p>
      </div>
    </div>
  );
};

type BinaryDetailProps = {
  path: string;
};

const BinaryDetail = ({ path }: BinaryDetailProps) => {
  const { t } = useTranslation("workspace");
  return (
    <div
      className="flex flex-1 items-center justify-center"
      style={{ padding: 24 }}
    >
      <div
        className="flex flex-col items-center"
        style={{ gap: 10, textAlign: "center", maxWidth: 340 }}
      >
        <FileQuestion size={28} style={{ color: "var(--fg-3)" }} />
        <div className="mono dim" style={{ fontSize: 11.5 }}>
          {path}
        </div>
        <p className="dim" style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}>
          {t("files.binaryHint")}
        </p>
      </div>
    </div>
  );
};

/**
 * Canvas half of the Files mode: hosts the code editor for `?file=<path>`.
 * The tree itself lives in the Files panel (the shell), which writes the
 * search param — this view only reads it, so the `?file=…&line=<n>` deep link
 * a checks finding produces keeps working no matter who set it.
 */
export const FileEditorView = ({ projectId }: FileEditorViewProps) => {
  const { t } = useTranslation("workspace");
  const [searchParams, setSearchParams] = useSearchParams();
  // Selection lives in the URL (`?file=…`) so it's deep-linkable and a finding
  // clicked in «Проверки» can open the right file here. Normalise separators so
  // a backslash path from a finding matches the tree's forward-slash paths.
  const rawFile = searchParams.get("file");
  const selectedPath = rawFile != null ? toPosixPath(rawFile) : null;
  const lineParam = searchParams.get("line");
  const parsedLine = lineParam != null ? Number(lineParam) : Number.NaN;
  const revealLine =
    Number.isFinite(parsedLine) && parsedLine > 0 ? parsedLine : undefined;

  const diagnosticsByFile = useProjectDiagnostics(projectId);
  const diagnostics = useMemo(
    () =>
      selectedPath
        ? (diagnosticsByFile.get(selectedPath) ?? NO_DIAGNOSTICS)
        : NO_DIAGNOSTICS,
    [diagnosticsByFile, selectedPath],
  );

  const clearLineParam = useCallback(() => {
    const params = new URLSearchParams(searchParams);
    if (params.has("line")) {
      params.delete("line");
      setSearchParams(params, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const revealProps =
    revealLine != null ? { revealLine, onRevealConsumed: clearLineParam } : {};

  return (
    <div
      className="flex flex-col"
      style={{
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        background: "var(--bg-0)",
      }}
    >
      {!selectedPath ? (
        <EmptyDetail />
      ) : isEditablePath(selectedPath) ? (
        <SourceEditor
          projectId={projectId}
          relativePath={selectedPath}
          diagnostics={diagnostics}
          readOnly={isGeneratedPath(selectedPath)}
          readOnlyReason={t("files.generatedReadOnly")}
          {...revealProps}
        />
      ) : (
        <BinaryDetail path={selectedPath} />
      )}
    </div>
  );
};
