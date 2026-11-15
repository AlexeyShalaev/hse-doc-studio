// Закрытый список кодов ошибок «Каталогов паков». Источник правды:
// contracts/pack-catalog/error_codes.json; контрактный тест сверяет этот список с JSON
// и с ключами errors:code.* в ru и en. Сбои git источника идут кодами
// git-синхронизации (contracts/git-sync/error_codes.json), их тексты там же.
export const PACK_CATALOG_ERROR_CODES = [
  "source_not_found",
  "source_busy",
  "source_kind_not_allowed",
  "source_exists",
  "source_disabled",
  "ref_not_found",
  "packs_path_missing",
  "archive_missing",
  "archive_too_large",
  "archive_invalid",
  "archive_unsafe",
  "tree_too_large",
  "tree_unsafe",
  "inspection_failed",
  "not_checked",
  "revision_moved",
  "plan_blocked",
  "catalog_busy",
  "folder_unavailable",
  "label_invalid",
] as const;

export type PackCatalogErrorCode = (typeof PACK_CATALOG_ERROR_CODES)[number];

export const isPackCatalogErrorCode = (
  value: unknown,
): value is PackCatalogErrorCode =>
  typeof value === "string" &&
  (PACK_CATALOG_ERROR_CODES as readonly string[]).includes(value);
