import type { PackVersionRef } from "../api/packStudioApi";
import { versionRefOf } from "./packPaths";
import { PACK_STUDIO_PATH } from "./routes";

// Адреса нового интерфейса Студии шаблонов (docs/design/pack-studio-ux.md, раздел 4.2):
//   /pack-studio/w/:ws/t/:pack/:template/:version/(result|content|check)?<query>
// Здесь же таблица перенаправлений со старых адресов. Старые `packOutcomePath`, `packFilesPath`
// и `packRulePath` (routes.ts) остаются для старого интерфейса; срезы нового их не вызывают.

export const SPACE_TABS = ["result", "content", "check"] as const;
export type SpaceTab = (typeof SPACE_TABS)[number];

export const isSpaceTab = (value: string | undefined): value is SpaceTab =>
  SPACE_TABS.some((tab) => tab === value);

/** Имена параметров query. Прочие параметры срезы вводят сами, но через `extra` у `useSpaceNav`. */
export const SPACE_QUERY = {
  /** Условия студента: `i.<условие>=<значение>`, формат прежнего экрана «Результат». */
  inputPrefix: "i.",
  /** Готовый случай (бывший сценарий). */
  case: "case",
  /** Выбранный элемент результата: `<раздел>:<id>`, как прежний `selected`. */
  sel: "sel",
  /** `1`: открыта панель «Изменения». */
  changes: "changes",
  /** «Содержимое»: документ, часть, открытый файл (путь от папки паков). */
  doc: "doc",
  part: "part",
  file: "file",
} as const;

const enc = encodeURIComponent;

const spaceBase = (id: string): string => `${PACK_STUDIO_PATH}/w/${enc(id)}`;

/** Адрес вкладки версии; `search` это query целиком (со знаком вопроса или без). */
export const spacePath = (
  id: string,
  ref: PackVersionRef,
  tab: SpaceTab,
  search = "",
): string => {
  const path = `${spaceBase(id)}/t/${[ref.pack, ref.template, ref.version].map(enc).join("/")}/${tab}`;
  const query = search.replace(/^\?/, "");
  return query ? `${path}?${query}` : path;
};

/** Куда ведёт старый адрес. `null` в поле: вход подставляет своё (последнее место, умолчание). */
export type SpaceTarget = {
  ref: PackVersionRef | null;
  /** Шаблон без версии (`?newVersion=пак/шаблон`): вход берёт его версию по умолчанию. */
  template: { pack: string; template: string } | null;
  tab: SpaceTab | null;
  search: string;
};

// Старый параметр -> новый. Переименованное переезжает, снятое с экрана (источник данных,
// режим «Как студент», вкладка телефона) отбрасывается, остальное (`i.*`, `p.*`, `left`, `right`,
// `against`, `example`, `at`, `from`, `pane`) едет как есть.
const RENAMED: Record<string, string> = { selected: "sel", scenario: "case" };
const DROPPED = new Set(["state", "mode", "tab", "view", "file", "newVersion"]);
// Прежний режим центра -> часть вкладки «Проверка».
const VIEW_TO_CHECK: Record<string, [string, string]> = {
  matrix: ["part", "cases"],
  atlas: ["part", "map"],
  compare: ["compare", "1"],
  lint: ["part", "issues"],
};

const carry = (old: URLSearchParams): URLSearchParams => {
  const next = new URLSearchParams();
  old.forEach((value, name) => {
    if (!DROPPED.has(name)) next.append(RENAMED[name] ?? name, value);
  });
  return next;
};

const decode = (parts: string[]): string[] | null => {
  try {
    return parts.map((part) => decodeURIComponent(part));
  } catch {
    return null;
  }
};

/**
 * Старый адрес пространства -> новый. Узнаёт `/w/:ws` (с `?file=`, `?view=files`,
 * `?newVersion=`), `/w/:ws/result` и `/w/:ws/result/:pack/:template/:version` с их query.
 * Всё остальное (в том числе уже новые адреса) даёт `null`.
 */
export const legacyToSpace = (
  id: string,
  pathname: string,
  search: string,
): SpaceTarget | null => {
  const base = spaceBase(id);
  if (pathname !== base && !pathname.startsWith(`${base}/`)) return null;
  const parts = decode(pathname.slice(base.length).split("/").filter(Boolean));
  if (!parts) return null;
  const old = new URLSearchParams(search);
  const next = carry(old);
  if (parts.length === 0) {
    const file = old.get("file");
    if (file) {
      const withFile = new URLSearchParams([["file", file], ...next]);
      return {
        ref: versionRefOf(file),
        template: null,
        tab: "content",
        search: withFile.toString(),
      };
    }
    // Мастер «Новая версия» старого вида: `?view=files&newVersion=пак/шаблон`.
    const hint = (old.get("newVersion") ?? "").split("/");
    if (hint.length === 2 && hint[0] && hint[1]) {
      next.set("copy", "1");
      return {
        ref: null,
        template: { pack: hint[0], template: hint[1] },
        tab: "result",
        search: next.toString(),
      };
    }
    if (old.get("view") === "files") next.set("part", "files");
    return {
      ref: null,
      template: null,
      tab: old.get("view") === "files" ? "content" : null,
      search: next.toString(),
    };
  }
  if (parts[0] !== "result" || (parts.length !== 1 && parts.length !== 4)) {
    return null;
  }
  const [, pack = "", template = "", version = ""] = parts;
  const ref = parts.length === 4 ? { pack, template, version } : null;
  const check = VIEW_TO_CHECK[old.get("view") ?? ""];
  if (check) next.set(check[0], check[1]);
  return {
    ref,
    template: null,
    tab: check ? "check" : "result",
    search: next.toString(),
  };
};
