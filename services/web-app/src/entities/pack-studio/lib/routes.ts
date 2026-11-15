/** Адрес Студии шаблонов: список рабочих пространств. */
export const PACK_STUDIO_PATH = "/pack-studio";

/** Рабочее пространство, по желанию с открытым файлом (`?file=` от папки паков). */
export const packWorkspacePath = (id: string, file?: string | null): string => {
  const base = `${PACK_STUDIO_PATH}/w/${encodeURIComponent(id)}`;
  return file ? `${base}?file=${encodeURIComponent(file)}` : base;
};
