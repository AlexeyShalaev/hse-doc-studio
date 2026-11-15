import { isArchiveName } from "@entities/pack-catalog";
import { formatFileSize, i18n } from "@shared/lib";

/** Почему файл не подойдёт: не архив или больше предела установки; иначе null. */
export const archiveProblem = (file: File, maxBytes: number): string | null => {
  if (!isArchiveName(file.name)) {
    return i18n.t("adminPackCatalog:add.fileWrongType");
  }
  if (file.size > maxBytes) {
    return i18n.t("adminPackCatalog:add.fileTooLarge", {
      size: formatFileSize(maxBytes),
    });
  }
  return null;
};
