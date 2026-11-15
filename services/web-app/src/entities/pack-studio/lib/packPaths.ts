import type { EditorLanguage } from "@shared/ui";
import type { PackTree, PackTreeVersion } from "../api/schemas";

// Раскладка пака (docs/ru/reference/pack.md): <пак>/templates/<шаблон>/versions/<версия>/...
// Части раскладки сравниваются без учёта регистра, как на бэкенде (core/pack_studio/paths.py).

const TEMPLATES_DIR = "templates";
const VERSIONS_DIR = "versions";
const VERSION_DEPTH = 5;

const same = (a: string | undefined, b: string): boolean =>
  a?.toLowerCase() === b;

/** Каталог версии, в которой лежит путь (или сам каталог версии); null для прочих путей. */
export const versionDirOf = (path: string): string | null => {
  const parts = path.split("/");
  if (
    parts.length < VERSION_DEPTH ||
    !same(parts[1], TEMPLATES_DIR) ||
    !same(parts[3], VERSIONS_DIR)
  ) {
    return null;
  }
  return parts.slice(0, VERSION_DEPTH).join("/");
};

/** Манифест вне версии, который проверяется схемой: pack.yaml, template.yaml, releases.yaml. */
export const isPackManifest = (path: string): boolean => {
  const parts = path.split("/");
  const name = parts[parts.length - 1]?.toLowerCase();
  if (parts.length === 2) return name === "pack.yaml";
  return (
    parts.length === 4 &&
    same(parts[1], TEMPLATES_DIR) &&
    (name === "template.yaml" || name === "releases.yaml")
  );
};

/** Что проверяет сервер для файла: каталог его версии, сам манифест или ничего. */
export const lintTargetOf = (path: string): string | null =>
  versionDirOf(path) ?? (isPackManifest(path) ? path : null);

const LANGUAGE_BY_EXT: Record<string, EditorLanguage> = {
  tex: "latex",
  cls: "latex",
  sty: "latex",
  bib: "latex",
  yaml: "yaml",
  yml: "yaml",
  json: "json",
  md: "markdown",
  html: "html",
};

const extOf = (path: string): string => {
  const name = path.split("/").pop() ?? "";
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
};

/** Шаблон Jinja пака: `.j2` (`common/meta.tex.j2`). */
export const isJinjaPath = (path: string): boolean => extOf(path) === "j2";

/** Грамматика редактора: `.j2` берёт её по расширению под ним (`meta.tex.j2` это LaTeX). */
export const languageForPackPath = (path: string): EditorLanguage => {
  const base = isJinjaPath(path) ? path.slice(0, -".j2".length) : path;
  return LANGUAGE_BY_EXT[extOf(base)] ?? "plain";
};

const TEXT_EXTS = new Set([
  "tex",
  "cls",
  "sty",
  "bib",
  "yaml",
  "yml",
  "json",
  "md",
  "txt",
  "html",
  "j2",
  "csv",
  "xml",
  "svg",
  "toml",
  "ini",
  "cfg",
]);

/** Файл открывается в редакторе кода; картинки, шрифты и офисные файлы нет. */
export const isTextPath = (path: string): boolean => {
  const ext = extOf(path);
  return ext === "" || TEXT_EXTS.has(ext);
};

export type VersionLocation = {
  packId: string;
  templateId: string;
  version: PackTreeVersion;
};

/** Версия из дерева по пути внутри неё: статус, выпущенность, правка мимо Студии. */
export const findVersion = (
  tree: PackTree | undefined,
  path: string,
): VersionLocation | null => {
  const dir = versionDirOf(path)?.toLowerCase();
  if (!tree || !dir) return null;
  for (const pack of tree.packs) {
    for (const template of pack.templates) {
      const version = template.versions.find(
        (v) => v.path.toLowerCase() === dir,
      );
      if (version) {
        return { packId: pack.id, templateId: template.id, version };
      }
    }
  }
  return null;
};

export type PackTreeNode = {
  name: string;
  path: string;
  isDir: boolean;
  size: number;
  readOnly: PackTree["files"][number]["read_only"];
  children: PackTreeNode[];
};

/**
 * Плоский список файлов дерева в иерархию. Папки, которых сервер не прислал
 * отдельной строкой, появляются по путям файлов; внутри папки сначала папки,
 * потом файлы, по имени. Версии сортируются по номеру сверху вниз от новой.
 */
export const buildFileTree = (files: PackTree["files"]): PackTreeNode[] => {
  const root: PackTreeNode = {
    name: "",
    path: "",
    isDir: true,
    size: 0,
    readOnly: null,
    children: [],
  };
  const dirs = new Map<string, PackTreeNode>([["", root]]);
  const ensureDir = (path: string): PackTreeNode => {
    const known = dirs.get(path);
    if (known) return known;
    const slash = path.lastIndexOf("/");
    const parent = ensureDir(slash < 0 ? "" : path.slice(0, slash));
    const node: PackTreeNode = {
      name: path.slice(slash + 1),
      path,
      isDir: true,
      size: 0,
      readOnly: null,
      children: [],
    };
    parent.children.push(node);
    dirs.set(path, node);
    return node;
  };
  for (const file of files) {
    if (file.is_dir) {
      ensureDir(file.path).readOnly = file.read_only;
      continue;
    }
    const slash = file.path.lastIndexOf("/");
    const parent = ensureDir(slash < 0 ? "" : file.path.slice(0, slash));
    parent.children.push({
      name: file.path.slice(slash + 1),
      path: file.path,
      isDir: false,
      size: file.size,
      readOnly: file.read_only,
      children: [],
    });
  }
  const sort = (node: PackTreeNode) => {
    const inVersions = same(node.name, VERSIONS_DIR);
    node.children.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
      if (inVersions) {
        return b.name.localeCompare(a.name, undefined, { numeric: true });
      }
      return a.name.localeCompare(b.name, undefined, { numeric: true });
    });
    node.children.forEach(sort);
  };
  sort(root);
  return root.children;
};

/** Папки по пути к файлу: их раскрывает дерево, когда файл открыт по ссылке. */
export const ancestorsOf = (path: string): string[] => {
  const parts = path.split("/");
  return parts.slice(0, -1).map((_, i) => parts.slice(0, i + 1).join("/"));
};

/** Версия шаблона в адресе предпросмотра (`{pack}/{template}/{version}`) по каталогу версии. */
export const versionRefOf = (
  path: string,
): { pack: string; template: string; version: string } | null => {
  const dir = versionDirOf(path);
  if (dir === null) return null;
  const [pack = "", , template = "", , version = ""] = dir.split("/");
  return { pack, template, version };
};

const FILE_LINE = /^(?<rel>[^\s:[\]]+\.[A-Za-z0-9]+):(?<line>\d+):/;

/**
 * Куда вести находку проверки перед отправкой (pack check): у неё путь файла или
 * каталога и нет строки. Каталог версии с «файл:строка:» в начале сообщения ведёт
 * в этот файл и строку (как в линтере редактора), иначе в манифест версии;
 * каталог шаблона или пака в его манифест; null, если вести некуда.
 */
export const findingTarget = (
  path: string,
  message: string,
): { path: string; line: number | null } | null => {
  const clean = path.replace(/\/+$/, "");
  // «.»: сбой всей проверки (база не прочиталась), вести некуда.
  if (clean === "" || clean === ".") return null;
  if (versionDirOf(clean) === clean) {
    const match = FILE_LINE.exec(message);
    const rel = match?.groups?.rel;
    if (rel) {
      const inVersion = rel === "version.yaml" || rel.startsWith("checks/");
      return {
        path: `${clean}/${inVersion ? rel : `files/${rel}`}`,
        line: Number(match.groups?.line ?? 0) || null,
      };
    }
    return { path: `${clean}/version.yaml`, line: null };
  }
  const last = clean.split("/").pop() ?? "";
  if (/\.[A-Za-z0-9]+$/.test(last)) return { path: clean, line: null };
  const parts = clean.split("/");
  if (parts.length === 1) return { path: `${clean}/pack.yaml`, line: null };
  if (parts.length === 3 && same(parts[1], TEMPLATES_DIR)) {
    return { path: `${clean}/template.yaml`, line: null };
  }
  return { path: clean, line: null };
};

/** Какая форма поверх YAML есть у файла (template-studio.md, 5.0): манифест версии или документа. */
export type PackFormKind = "version" | "doc";

export const packFormKind = (path: string): PackFormKind | null => {
  const dir = versionDirOf(path);
  if (dir === null) return null;
  const rest = path.slice(dir.length + 1);
  if (rest === "version.yaml") return "version";
  return /^files\/[^/]+\/doc\.yaml$/.test(rest) ? "doc" : null;
};
