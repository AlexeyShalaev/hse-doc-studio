import type { EditorLanguage } from "@shared/ui";

const LATEX_EXTENSIONS = [".tex", ".cls", ".sty", ".ltx", ".dtx", ".def"];
const JSON_EXTENSIONS = [".json"];
const YAML_EXTENSIONS = [".yml", ".yaml"];
const HTML_EXTENSIONS = [".html", ".htm"];
const MARKDOWN_EXTENSIONS = [".md", ".markdown"];

/** Picks the editor grammar from a file extension; unknown files get plain. */
export const languageForPath = (path: string): EditorLanguage => {
  const lower = path.toLowerCase();
  const has = (extensions: string[]) =>
    extensions.some((ext) => lower.endsWith(ext));
  if (has(LATEX_EXTENSIONS)) return "latex";
  if (has(JSON_EXTENSIONS)) return "json";
  if (has(YAML_EXTENSIONS)) return "yaml";
  if (has(HTML_EXTENSIONS)) return "html";
  if (has(MARKDOWN_EXTENSIONS)) return "markdown";
  return "plain";
};
