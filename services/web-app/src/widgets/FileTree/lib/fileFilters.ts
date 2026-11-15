import { isEditableTextPath } from "@shared/lib/fileTypes";

// LaTeX build artifacts that clutter the tree — hidden by default behind the
// "показать сгенерированные" toggle.
const ARTIFACT_EXTENSIONS = [
  ".aux",
  ".log",
  ".synctex.gz",
  ".out",
  ".toc",
  ".fls",
  ".fdb_latexmk",
  ".bbl",
  ".blg",
  ".nav",
  ".snm",
  ".vrb",
  ".lof",
  ".lot",
  ".idx",
  ".ind",
  ".ilg",
  ".run.xml",
];

const HIDDEN_DIR_SEGMENTS = new Set([".build", ".git", ".hse-studio"]);

// Text formats we open in the editor live in @shared/lib/fileTypes (deep
// import keeps this module free of the barrel's i18n side effect); everything
// else is treated as binary here. Note: the document SourcePane additionally
// accepts .html (reveal presentation source) — the tree deliberately doesn't.

// Regenerated from project.json before every compile — editing them is futile.
// Team layouts nest a copy per base folder ("shared/common/meta.tex",
// "<author-slug>/common/meta.tex"), so match the path tail, not exact paths.
const GENERATED_FILE_TAILS = ["common/meta.tex", "common/fonts.tex"];

const segmentsOf = (path: string): string[] =>
  path.toLowerCase().split("/").filter(Boolean);

export const isHiddenDirPath = (path: string): boolean =>
  segmentsOf(path).some((seg) => HIDDEN_DIR_SEGMENTS.has(seg));

// Сборка кладёт PDF рядом с исходником под тем же именем (vkr/vkr.tex даёт vkr/vkr.pdf). Такой PDF
// прячется вместе с прочими артефактами, а PDF без исходника рядом (рисунок, скан, загруженный
// с компьютера файл) виден всегда. То же правило у истории версий (core/vcs/build_pdf.py).
const BUILD_PDF_SOURCE_EXTENSIONS = [
  ".tex",
  ".docx",
  ".doc",
  ".odt",
  ".rtf",
  ".pptx",
  ".ppt",
  ".odp",
  ".md",
  ".html",
  ".htm",
];

export const isBuildOutputPdf = (
  path: string,
  isFile: (path: string) => boolean,
): boolean => {
  if (!path.endsWith(".pdf")) return false;
  const stem = path.slice(0, -".pdf".length);
  return BUILD_PDF_SOURCE_EXTENSIONS.some((ext) => isFile(`${stem}${ext}`));
};

/**
 * Скрыто без «показать сгенерированные»: служебные папки, артефакты LaTeX и собранные PDF.
 * Без `isFile` (нет списка файлов) прячется любой PDF, как раньше.
 */
export const isHiddenPath = (
  path: string,
  isFile?: (path: string) => boolean,
): boolean => {
  const lower = path.toLowerCase();
  if (segmentsOf(path).some((seg) => HIDDEN_DIR_SEGMENTS.has(seg))) return true;
  if (lower.endsWith(".pdf")) {
    return isFile === undefined || isBuildOutputPdf(path, isFile);
  }
  return ARTIFACT_EXTENSIONS.some((ext) => lower.endsWith(ext));
};

export const isEditablePath = (path: string): boolean =>
  isEditableTextPath(path);

export const isGeneratedPath = (path: string): boolean => {
  const norm = path.toLowerCase().replace(/\\/g, "/").replace(/^\/+/, "");
  return GENERATED_FILE_TAILS.some(
    (tail) => norm === tail || norm.endsWith(`/${tail}`),
  );
};

/** Read-only in the editor: generated files, or non-text (binary) files. */
export const isReadOnlyPath = (path: string): boolean =>
  isGeneratedPath(path) || !isEditablePath(path);
