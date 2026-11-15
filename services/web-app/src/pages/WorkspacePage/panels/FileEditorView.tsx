import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Download, FileQuestion, FolderTree } from "lucide-react";
import { fileContentUrl, useFileTree } from "@entities/document";
import { SourceEditor, useProjectDiagnostics } from "@features/source-edit";
import { isEditablePath, isGeneratedPath } from "@widgets/FileTree";
import { toPosixPath } from "@shared/lib";
import { PdfViewer, type EditorDiagnostic } from "@shared/ui";

export type FileEditorViewProps = {
  projectId: string;
};

const NO_DIAGNOSTICS: EditorDiagnostic[] = [];

const EmptyDetail = () => {
  const { t } = useTranslation("workspace");
  return (
    <div
      className="flex flex-1 items-center justify-center"
      style={{ padding: "1.5rem" }}
    >
      <div
        className="flex flex-col items-center"
        style={{ gap: "0.75rem", textAlign: "center", maxWidth: "20rem" }}
      >
        <div
          className="flex items-center justify-center"
          style={{
            width: "2.625rem",
            height: "2.625rem",
            borderRadius: "var(--r-3)",
            background: "var(--bg-2)",
            color: "var(--fg-3)",
            border: "1px solid var(--border)",
          }}
        >
          <FolderTree size="1.25rem" />
        </div>
        <h2
          className="dim"
          style={{ margin: 0, fontSize: "0.9375rem", fontWeight: 600 }}
        >
          {t("files.editorTitle")}
        </h2>
        <p
          className="dim"
          style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.5 }}
        >
          {t("files.editorHint")}
        </p>
      </div>
    </div>
  );
};

// Картинки, которые браузер показывает сам. SVG тоже: в `<img>` его скрипты не исполняются.
const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"];

const isImagePath = (path: string): boolean => {
  const lower = path.toLowerCase();
  return IMAGE_EXTENSIONS.some((ext) => lower.endsWith(ext));
};

type BinaryDetailProps = {
  projectId: string;
  path: string;
};

/**
 * Не текстовый файл: картинку и PDF показываем, остальное предлагаем скачать. В текстовый
 * редактор такие файлы не попадают, иначе загруженный PNG открылся бы мусором.
 */
const BinaryDetail = ({ projectId, path }: BinaryDetailProps) => {
  const { t } = useTranslation("workspace");
  const { data: items } = useFileTree(projectId);
  // Версия файла в адресе: после замены загрузкой картинка и PDF перечитываются.
  const version = items?.find((item) => item.path === path)?.modified_at ?? "";
  const url = fileContentUrl(projectId, path);
  const name = path.split("/").pop() ?? path;
  const download = (
    <a href={url} className="btn" download={name}>
      <Download size="0.75rem" />
      {t("files.download")}
    </a>
  );

  if (path.toLowerCase().endsWith(".pdf")) {
    return (
      <PdfViewer
        url={url}
        refreshKey={version}
        ariaLabel={path}
        toolbarExtras={download}
      />
    );
  }

  if (isImagePath(path)) {
    return (
      <div
        className="flex flex-1 flex-col items-center"
        style={{ padding: "1rem", gap: "0.75rem", minHeight: 0 }}
      >
        <div
          className="flex items-center"
          style={{ gap: "0.75rem", maxWidth: "100%" }}
        >
          <span
            className="mono dim truncate"
            style={{ fontSize: "0.71875rem" }}
          >
            {path}
          </span>
          {download}
        </div>
        <div
          className="flex flex-1 items-center justify-center"
          style={{ minHeight: 0, width: "100%", overflow: "auto" }}
        >
          <img
            src={version ? `${url}?v=${encodeURIComponent(version)}` : url}
            alt={t("files.imagePreview", { name })}
            style={{
              maxWidth: "100%",
              maxHeight: "100%",
              objectFit: "contain",
              background: "var(--bg-2)",
              borderRadius: "var(--r-2)",
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex flex-1 items-center justify-center"
      style={{ padding: "1.5rem" }}
    >
      <div
        className="flex flex-col items-center"
        style={{ gap: "0.625rem", textAlign: "center", maxWidth: "21.25rem" }}
      >
        <FileQuestion size="1.75rem" style={{ color: "var(--fg-3)" }} />
        <div className="mono dim" style={{ fontSize: "0.71875rem" }}>
          {path}
        </div>
        <p
          className="dim"
          style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.5 }}
        >
          {t("files.binaryHint")}
        </p>
        {download}
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
        <BinaryDetail projectId={projectId} path={selectedPath} />
      )}
    </div>
  );
};
