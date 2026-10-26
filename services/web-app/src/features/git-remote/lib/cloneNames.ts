// Названия при клонировании: из адреса, файла и ответа сервера.

const BUNDLE_EXTENSIONS = [".bundle.hseenc", ".hseenc", ".bundle"];

/** Файл защищён паролем: у таких имя заканчивается на .hseenc. */
export const isEncryptedBundleName = (fileName: string): boolean => {
  return fileName.toLowerCase().endsWith(".hseenc");
};

/** Имя файла без расширения и без метки времени, которую добавляет выгрузка. */
export const bundleStem = (fileName: string): string => {
  const lower = fileName.toLowerCase();
  const extension = BUNDLE_EXTENSIONS.find((ext) => lower.endsWith(ext));
  const stem = extension
    ? fileName.slice(0, fileName.length - extension.length)
    : fileName;
  return stem.replace(/-\d{8}-\d{4}$/, "");
};

/** Название проекта для подсказки: из проекта в репозитории, иначе из адреса. */
export const suggestedProjectName = (source: {
  projectName: string | null;
  repo: string | null;
  fileName: string | null;
}): string => {
  if (source.projectName) return source.projectName.trim();
  if (source.fileName) return bundleStem(source.fileName);
  return (source.repo ?? "").replace(/\.git$/, "");
};
