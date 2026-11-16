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
