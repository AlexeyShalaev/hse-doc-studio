/** Адрес Студии шаблонов: список рабочих пространств. */
export const PACK_STUDIO_PATH = "/pack-studio";

const workspaceBase = (id: string): string =>
  `${PACK_STUDIO_PATH}/w/${encodeURIComponent(id)}`;

/**
 * Рабочее пространство: без файла это вход в экран «Результат» (он по умолчанию),
 * с файлом (`?file=` от папки паков) режим «Файлы» с деревом и редактором.
 */
export const packWorkspacePath = (id: string, file?: string | null): string =>
  file
    ? `${workspaceBase(id)}?file=${encodeURIComponent(file)}`
    : workspaceBase(id);

/** Режим «Файлы» без открытого файла: дерево и подсказка выбрать файл. */
export const packFilesPath = (id: string): string =>
  `${workspaceBase(id)}?view=files`;

/** Экран «Результат» версии; `search` это состояние экрана (адрес хранит его целиком). */
export const packOutcomePath = (
  id: string,
  ref?: { pack: string; template: string; version: string } | null,
  search = "",
): string => {
  const base = `${workspaceBase(id)}/result`;
  const path = ref
    ? `${base}/${[ref.pack, ref.template, ref.version].map(encodeURIComponent).join("/")}`
    : base;
  return search ? `${path}?${search.replace(/^\?/, "")}` : path;
};

/** Как открыть запись манифеста: форма раздела или исходник на строке. */
export type RulePane = "form" | "source";

/**
 * Переход к правилу из экрана «Результат»: режим «Файлы» на файле с указателем записи
 * (`at`, JSON Pointer), вкладкой (`pane`) и адресом возврата (`from`, путь экрана «Результат»
 * вместе с состоянием). Все три параметра необязательны и обратимы: без них адрес прежний.
 */
export const packRulePath = (
  id: string,
  file: string,
  target: { pointer: string | null; pane: RulePane; from: string },
): string => {
  const params = new URLSearchParams({ file });
  if (target.pointer) params.set("at", target.pointer);
  params.set("pane", target.pane);
  params.set("from", target.from);
  return `${workspaceBase(id)}?${params.toString()}`;
};

/**
 * Адрес возврата из `from`: только экран «Результат» этого же пространства. Всё остальное
 * (чужой хост, другой путь, мусор) отбрасывается, чтобы параметр нельзя было использовать
 * как открытое перенаправление.
 */
export const safeOutcomeBack = (
  id: string,
  from: string | null,
): string | null => {
  if (!from) return null;
  const base = `${workspaceBase(id)}/result`;
  const ok =
    from === base || from.startsWith(`${base}/`) || from.startsWith(`${base}?`);
  return ok && !from.includes("//", base.length) ? from : null;
};
