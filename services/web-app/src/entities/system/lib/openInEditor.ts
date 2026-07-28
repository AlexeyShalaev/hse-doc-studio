// Each editor registers a URL handler when installed; the browser delegates
// `<scheme>://file/<absolute-path>:<line>` to the OS, which launches the editor.
// Works regardless of whether the backend is on host or containerized — the
// browser is always on host.
export const buildEditorUrl = (
  scheme: string,
  absolutePath: string,
  // null → open a folder/file without a line anchor (`vscode://file/<dir>`
  // opens a directory as a workspace; a trailing `:1` would break that).
  line: number | null = 1,
): string => {
  // Windows paths use backslashes; URL schemes need forward slashes. encodeURI
  // preserves `:` and `/` (needed for the drive letter + separators) and only
  // encodes spaces and unicode.
  const normalized = absolutePath.replaceAll("\\", "/");
  const encoded = encodeURI(normalized);
  const suffix = line == null ? "" : `:${line.toString()}`;
  return `${scheme}://file/${encoded}${suffix}`;
};

export const openInEditor = (
  scheme: string,
  absolutePath: string,
  line: number | null = 1,
): void => {
  const url = buildEditorUrl(scheme, absolutePath, line);
  // Using a temp anchor + click() is more reliable than `window.location.href`
  // for custom URL schemes — modern browsers treat it as an explicit
  // user-initiated action, show the permission dialog, and don't navigate
  // the current page away.
  const a = document.createElement("a");
  a.href = url;
  a.click();
};
