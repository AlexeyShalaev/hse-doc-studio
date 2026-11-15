import type {
  CatalogCheck,
  CatalogSource,
  PlannedVersion,
  Verdict,
} from "../api/schemas";

// Чистые помощники отчёта проверки и карточки источника: что подсветить, как сократить.

export type VerdictTone =
  "success" | "default" | "warning" | "error" | "subtle";

/** Цвет метки вердикта: появится, уже есть, не для этой Студии, отказ, не выпущена. */
export const VERDICT_TONE: Record<Verdict, VerdictTone> = {
  new: "success",
  present: "default",
  changed: "error",
  incompatible: "warning",
  invalid: "error",
  unreleased: "subtle",
};

/** Порядок версий в отчёте: сначала то, что мешает, затем то, что появится. */
const VERDICT_ORDER: Record<Verdict, number> = {
  changed: 0,
  invalid: 1,
  new: 2,
  incompatible: 3,
  present: 4,
  unreleased: 5,
};

export const sortVersions = (
  versions: readonly PlannedVersion[],
): PlannedVersion[] =>
  [...versions].sort(
    (a, b) =>
      VERDICT_ORDER[a.verdict] - VERDICT_ORDER[b.verdict] ||
      a.template.localeCompare(b.template) ||
      a.version.localeCompare(b.version),
  );

/** Сколько версий каждого вердикта в отчёте. */
export const verdictCounts = (
  check: Pick<CatalogCheck, "packs">,
): Partial<Record<Verdict, number>> => {
  const counts: Partial<Record<Verdict, number>> = {};
  for (const pack of check.packs) {
    for (const version of pack.versions) {
      counts[version.verdict] = (counts[version.verdict] ?? 0) + 1;
    }
  }
  return counts;
};

/** Отчёт нашёл пак с id вшитого: к нему относится галочка «Заменить встроенный». */
export const hasBuiltinConflict = (check: Pick<CatalogCheck, "packs">) =>
  check.packs.some((pack) => pack.conflict === "builtin");

/** Короткая ревизия: sha коммита или дайджест архива и папки. */
export const shortRevision = (revision: string): string =>
  revision.length > 12 ? revision.slice(0, 8) : revision;

/** Откуда источник: адрес и ref у git, имя архива, путь папки. */
export const sourceLocation = (source: CatalogSource): string => {
  if (source.kind === "git") {
    return [source.url ?? "", source.ref ?? ""].filter(Boolean).join(" @ ");
  }
  if (source.kind === "archive") return source.archive_name ?? "";
  return source.folder ?? "";
};

/** Ключ версии, как его пишет сервер в `added`: пак/шаблон@версия. */
export const versionKey = (pack: string, template: string, version: string) =>
  `${pack}/${template}@${version}`;
