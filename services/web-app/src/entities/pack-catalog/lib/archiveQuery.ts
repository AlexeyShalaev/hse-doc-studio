// Поля загрузки архива идут строкой запроса, тело это сам файл
// (contracts/pack-catalog/README.md). Пустые поля не отправляются: сервер берёт значения
// по умолчанию (название из имени файла, папка паков в корне архива).

export type ArchiveUploadFields = {
  /** Имя файла архива: по нему сервер узнаёт формат (.zip или .tar.gz). */
  name: string;
  label?: string | null | undefined;
  packsPath?: string | null | undefined;
  replaceBuiltin?: boolean | undefined;
};

const filled = (value: string | null | undefined): string | null => {
  const text = (value ?? "").trim();
  return text === "" ? null : text;
};

/** Параметры строки запроса загрузки архива: только заданные поля. */
export const archiveQuery = (
  fields: ArchiveUploadFields,
): Record<string, string> => {
  const params: Record<string, string> = { name: fields.name };
  const label = filled(fields.label);
  if (label !== null) params.label = label;
  const packsPath = filled(fields.packsPath);
  if (packsPath !== null) params.packs_path = packsPath;
  if (fields.replaceBuiltin) params.replace_builtin = "true";
  return params;
};

const ARCHIVE_SUFFIXES = [".zip", ".tar.gz", ".tgz"] as const;

/** Похоже ли имя файла на архив, который принимает сервер. */
export const isArchiveName = (name: string): boolean => {
  const lower = name.toLowerCase();
  return ARCHIVE_SUFFIXES.some((suffix) => lower.endsWith(suffix));
};

export const ARCHIVE_ACCEPT = ".zip,.tar.gz,.tgz";
