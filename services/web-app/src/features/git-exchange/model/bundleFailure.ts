// Куда в окне импорта ложится отказ: у каждого кода свой адресат. Пароль
// подсвечивает поле пароля, проблему файла видно под файлом, а состояние
// проекта (идёт синхронизация, нет профиля) не лечится другим файлом.

export type BundleFailureTarget =
  "password" | "file" | "profile" | "state" | "other";

// Ошибка, которой нет в списке кодов сервера: правки в редакторе не сохранились.
export const SAVE_FAILED_CODE = "save_failed";

// Запрос не дошёл до сервера (нет сети, обрыв): кода у такой ошибки нет.
export const NETWORK_FAILED_CODE = "network_error";

const PASSWORD_CODES = new Set([
  "bundle_password_required",
  "bundle_password_wrong",
]);

const FILE_CODES = new Set([
  "bundle_invalid",
  "bundle_prerequisites_missing",
  "unrelated_histories",
  "not_a_studio_project",
  "remote_schema_newer",
]);

const STATE_CODES = new Set([
  "sync_busy",
  "sync_busy_build",
  "off_branch",
  "store_untrusted",
  "sync_incomplete",
  SAVE_FAILED_CODE,
]);

export const bundleFailureTarget = (code: string): BundleFailureTarget => {
  if (PASSWORD_CODES.has(code)) return "password";
  if (FILE_CODES.has(code)) return "file";
  if (code === "profile_required") return "profile";
  if (STATE_CODES.has(code)) return "state";
  return "other";
};

// Коды, для которых у окна есть своя формулировка: «история репозитория не
// связана» для файла звучит как «файл от другого проекта».
export const HAS_OWN_COPY = new Set([
  "bundle_invalid",
  "bundle_prerequisites_missing",
  "unrelated_histories",
  "not_a_studio_project",
  SAVE_FAILED_CODE,
  NETWORK_FAILED_CODE,
]);

export type BundleFailure = {
  code: string;
  detail: string;
  /** Дополнительные поля ответа (required_studio и другие): подставляются в текст. */
  params?: Record<string, unknown>;
};
