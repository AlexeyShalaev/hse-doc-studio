// Matches the backend's convertible-extension allowlist (Gotenberg/
// LibreOffice-backed OfficeConvertManager) — keep in sync if it changes.
const CONVERTIBLE_EXTS = new Set([
  ".doc",
  ".docx",
  ".odt",
  ".rtf",
  ".ppt",
  ".pptx",
  ".odp",
  ".xls",
  ".xlsx",
  ".ods",
]);

export type CustomFileClass = "pdf" | "convertible" | "unknown";

const extOf = (filename: string): string => {
  const dot = filename.lastIndexOf(".");
  return dot >= 0 ? filename.slice(dot).toLowerCase() : "";
};

export const classifyCustomFile = (filename: string): CustomFileClass => {
  const ext = extOf(filename);
  if (ext === ".pdf") return "pdf";
  if (CONVERTIBLE_EXTS.has(ext)) return "convertible";
  return "unknown";
};

/**
 * Every convertible extension is also a format ONLYOFFICE Document Server can
 * actually EDIT (word/cell/slide) — same allowlist, different question ("can
 * we open a real editor for this?" vs "can we render a PDF preview?"). Used to
 * gate the in-app «Office» tab for both the template pptx variant and any
 * custom upload in one of these formats.
 */
export const isOfficeEditablePath = (path: string): boolean =>
  classifyCustomFile(path) === "convertible";

export type CustomFileLike = {
  custom_file?:
    | {
        ext: string;
      }
    | null
    | undefined;
  signing_available?: boolean | undefined;
};

export type CustomFileSignability =
  | "template"
  | "pdf"
  | "convertible"
  | "unsignable";

/**
 * Derives the signing surface for a document from its custom-file state.
 * `signing_available` alone can't distinguish "pdf" from "convertible with a
 * ready preview" — both come back `true` — so the ext classification decides
 * which editor branch (plain PDF vs preview-gated) DocSignaturesPane shows.
 */
export const getCustomFileSignability = (
  doc: CustomFileLike | null | undefined,
): CustomFileSignability => {
  const customFile = doc?.custom_file;
  if (customFile == null) return "template";
  const cls = classifyCustomFile(`file${customFile.ext}`);
  if (cls === "pdf") return "pdf";
  if (cls === "convertible") return "convertible";
  return "unsignable";
};
