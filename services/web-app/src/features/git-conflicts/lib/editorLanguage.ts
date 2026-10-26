import type { EditorLanguage } from "@shared/ui";

const BY_EXTENSION: [string[], EditorLanguage][] = [
  [[".tex", ".cls", ".sty", ".ltx", ".dtx", ".def"], "latex"],
  [[".json"], "json"],
  [[".yml", ".yaml"], "yaml"],
  [[".html", ".htm"], "html"],
  [[".md", ".markdown"], "markdown"],
];

/** Грамматика редактора по расширению файла; незнакомые файлы: простой текст. */
export const editorLanguageFor = (path: string): EditorLanguage => {
  const lower = path.toLowerCase();
  for (const [extensions, language] of BY_EXTENSION) {
    if (extensions.some((ext) => lower.endsWith(ext))) return language;
  }
  return "plain";
};
