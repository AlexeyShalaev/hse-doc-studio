import {
  versionDirOf,
  versionRefOf,
  type PackFileChange,
  type PackVersionRef,
} from "@entities/pack-studio";

// «Что изменено» человеческими словами (pack-studio-ux.md, 5.6): список файлов git превращается
// в группы по версиям и в строки «Документ: условия», «Описание версии». Чистая функция; слова
// подбирает панель по `kind`, документ называет по `doc`.

export type ChangeKind =
  | "version"
  | "docConditions"
  | "docText"
  | "docFiles"
  | "common"
  | "assets"
  | "checks"
  | "packInfo"
  | "templateInfo"
  | "releases"
  | "other";

/** Одна строка списка: несколько файлов одного смысла сливаются (текст документа на двух языках). */
export type ChangeItem = {
  key: string;
  kind: ChangeKind;
  /** Идентификатор документа (папка в `files/`), для строк про документ. */
  doc: string | null;
  /** Файл, который откроет строка (первый по алфавиту, не удалённый). */
  path: string | null;
  files: number;
  status: "added" | "modified" | "deleted";
};

export type ChangeGroup = {
  key: string;
  /** Версия группы; `null`: файлы пака и шаблона вне версий. */
  version: PackVersionRef | null;
  /** Пак группы вне версий (для заголовка). */
  pack: string | null;
  items: ChangeItem[];
  files: number;
  /** Группа это копия версии: подпись «Новая версия X и мои правки». */
  copy: boolean;
};

const ORDER: ChangeKind[] = [
  "version",
  "docConditions",
  "docText",
  "docFiles",
  "common",
  "assets",
  "checks",
  "packInfo",
  "templateInfo",
  "releases",
  "other",
];

const TEXT_EXT = new Set([
  "tex",
  "md",
  "j2",
  "txt",
  "html",
  "bib",
  "cls",
  "sty",
]);

const extOf = (path: string): string => {
  const name = path.split("/").pop() ?? "";
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
};

/** Смысл файла внутри версии: `rest` это путь от каталога версии. */
const kindInVersion = (
  rest: string,
): { kind: ChangeKind; doc: string | null } => {
  if (rest === "version.yaml") return { kind: "version", doc: null };
  if (rest.startsWith("checks/")) return { kind: "checks", doc: null };
  const parts = rest.split("/");
  if (parts[0] === "files" && parts.length >= 3) {
    const folder = parts[1] ?? "";
    if (folder === "common") return { kind: "common", doc: null };
    if (folder === "assets") return { kind: "assets", doc: null };
    if (parts.length === 3 && parts[2] === "doc.yaml") {
      return { kind: "docConditions", doc: folder };
    }
    return {
      kind: TEXT_EXT.has(extOf(rest)) ? "docText" : "docFiles",
      doc: folder,
    };
  }
  return { kind: "other", doc: null };
};

/** Смысл файла вне версий: манифесты пака, шаблона и реестр выпусков. */
const kindOutside = (path: string): ChangeKind => {
  const name = path.split("/").pop()?.toLowerCase();
  if (name === "pack.yaml") return "packInfo";
  if (name === "template.yaml") return "templateInfo";
  if (name === "releases.yaml") return "releases";
  return "other";
};

/** Смысл одного файла (для находок проверки): версия, вид и документ. */
export const describePath = (
  path: string,
): { version: PackVersionRef | null; kind: ChangeKind; doc: string | null } => {
  const dir = versionDirOf(path);
  const version = versionRefOf(path);
  return dir !== null
    ? { version, ...kindInVersion(path.slice(dir.length + 1)) }
    : { version, kind: kindOutside(path), doc: null };
};

const keyOfRef = (ref: PackVersionRef): string =>
  `${ref.pack}/${ref.template}/${ref.version}`;

/**
 * Группы по версиям: открытая версия первой, остальные по номеру (новые выше), файлы вне версий
 * последними. Внутри группы строки в порядке `ORDER`, документы по алфавиту.
 */
export const describeChanges = (
  changed: readonly PackFileChange[],
  open: PackVersionRef,
  copyDir: string | null = null,
): ChangeGroup[] => {
  type Draft = {
    group: ChangeGroup;
    items: Map<string, { item: ChangeItem; all: Set<ChangeItem["status"]> }>;
  };
  const drafts = new Map<string, Draft>();
  const sorted = [...changed].sort((a, b) => a.path.localeCompare(b.path));
  for (const change of sorted) {
    const dir = versionDirOf(change.path);
    const ref = versionRefOf(change.path);
    const groupKey = ref
      ? keyOfRef(ref)
      : `outside:${change.path.split("/")[0] ?? ""}`;
    let draft = drafts.get(groupKey);
    if (!draft) {
      draft = {
        group: {
          key: groupKey,
          version: ref,
          pack: ref ? null : (change.path.split("/")[0] ?? null),
          items: [],
          files: 0,
          copy: dir !== null && dir === copyDir,
        },
        items: new Map(),
      };
      drafts.set(groupKey, draft);
    }
    const { kind, doc } =
      dir !== null
        ? kindInVersion(change.path.slice(dir.length + 1))
        : { kind: kindOutside(change.path), doc: null };
    const itemKey = `${kind}:${doc ?? ""}`;
    let entry = draft.items.get(itemKey);
    if (!entry) {
      entry = {
        item: {
          key: `${groupKey}|${itemKey}`,
          kind,
          doc,
          path: null,
          files: 0,
          status: change.status,
        },
        all: new Set(),
      };
      draft.items.set(itemKey, entry);
    }
    entry.item.files += 1;
    entry.all.add(change.status);
    if (entry.item.path === null && change.status !== "deleted") {
      entry.item.path = change.path;
    }
    draft.group.files += 1;
  }

  const groups = [...drafts.values()].map(({ group, items }) => {
    group.items = [...items.values()]
      .map(({ item, all }) => {
        // Все файлы строки новые или все удалены: так и пишем; смесь это просто «изменено».
        item.status = all.size === 1 ? ([...all][0] ?? "modified") : "modified";
        return item;
      })
      .sort(
        (a, b) =>
          ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind) ||
          (a.doc ?? "").localeCompare(b.doc ?? ""),
      );
    return group;
  });
  const openKey = keyOfRef(open);
  const rank = (group: ChangeGroup) =>
    group.key === openKey ? 0 : group.version ? 1 : 2;
  return groups.sort(
    (a, b) =>
      rank(a) - rank(b) || b.key.localeCompare(a.key, "en", { numeric: true }),
  );
};
