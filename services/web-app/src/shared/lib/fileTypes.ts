// Text formats we open in the CodeMirror editor; everything else is treated
// as binary. Single source of truth shared by the FileTree widget (project
// files panel) and the document SourcePane, so both agree on what is text.
//
// `.html` is intentionally NOT in the base list: the FileTree treats built
// reveal.js output as an opaque artifact. Callers that legitimately edit HTML
// sources (the presentation reveal variant) pass it via `extraExtensions`.
export const EDITABLE_TEXT_EXTENSIONS = [
  ".tex",
  ".bib",
  ".cls",
  ".sty",
  ".ltx",
  ".dtx",
  ".def",
  ".txt",
  ".md",
  ".markdown",
  ".yml",
  ".yaml",
  ".json",
  ".csv",
  ".cfg",
  ".ini",
  ".toml",
  ".bst",
];

export const isEditableTextPath = (
  path: string,
  extraExtensions: string[] = [],
): boolean => {
  const lower = path.toLowerCase();
  return [...EDITABLE_TEXT_EXTENSIONS, ...extraExtensions].some((ext) =>
    lower.endsWith(ext),
  );
};
