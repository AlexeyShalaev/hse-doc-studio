import type {
  CatalogSource,
  CreateGitSourceRequest,
  UpdateSourceRequest,
} from "@entities/pack-catalog";

// Доступ git источника: без доступа, личный доступ админа из «Доступов git» или
// служебный доступ установки (раздел «Студия шаблонов»).

export type AccessChoice =
  | { kind: "none" }
  | { kind: "personal"; credentialId: string | null }
  | { kind: "service"; serviceAccessId: string | null };

/** Выбор задан до конца: у личного и служебного доступа выбран конкретный доступ. */
export const accessComplete = (choice: AccessChoice): boolean =>
  choice.kind === "none" ||
  (choice.kind === "personal"
    ? choice.credentialId !== null
    : choice.serviceAccessId !== null);

/** Поля доступа запроса «Добавить источник». */
export const accessFields = (
  choice: AccessChoice,
): Pick<CreateGitSourceRequest, "credential_id" | "service_access_id"> => {
  if (choice.kind === "personal" && choice.credentialId) {
    return { credential_id: choice.credentialId };
  }
  if (choice.kind === "service" && choice.serviceAccessId) {
    return { service_access_id: choice.serviceAccessId };
  }
  return {};
};

/** Доступ источника сейчас, как выбор в окне. */
export const accessOf = (source: CatalogSource): AccessChoice => {
  if (source.access === "personal") {
    return { kind: "personal", credentialId: source.credential_id };
  }
  if (source.access === "service") {
    return { kind: "service", serviceAccessId: source.service_access_id };
  }
  return { kind: "none" };
};

const sameAccess = (a: AccessChoice, b: AccessChoice): boolean => {
  if (a.kind !== b.kind) return false;
  if (a.kind === "personal" && b.kind === "personal") {
    return a.credentialId === b.credentialId;
  }
  if (a.kind === "service" && b.kind === "service") {
    return a.serviceAccessId === b.serviceAccessId;
  }
  return true;
};

/**
 * Поля доступа запроса «Изменить»: ничего, если доступ не менялся (сервер не проверяет
 * его заново), `clear_access`, если доступ убрали, иначе новый доступ.
 */
export const accessUpdate = (
  source: CatalogSource,
  choice: AccessChoice,
): Pick<
  UpdateSourceRequest,
  "credential_id" | "service_access_id" | "clear_access"
> => {
  if (sameAccess(accessOf(source), choice)) return {};
  if (choice.kind === "none") return { clear_access: true };
  return accessFields(choice);
};

const trimmed = (value: string): string | null => {
  const text = value.trim();
  return text === "" ? null : text;
};

export type GitSourceForm = {
  url: string;
  label: string;
  packsPath: string;
  ref: string;
  access: AccessChoice;
  insecureHttp: boolean;
  replaceBuiltin: boolean;
  track: boolean;
};

/** Тело «Добавить источник» git: пустые поля не отправляются, сервер берёт значения по умолчанию. */
export const gitSourceRequest = (
  form: GitSourceForm,
): CreateGitSourceRequest => {
  const label = trimmed(form.label);
  const packsPath = trimmed(form.packsPath);
  const ref = trimmed(form.ref);
  const url = form.url.trim();
  return {
    url,
    ...(label !== null ? { label } : {}),
    ...(packsPath !== null ? { packs_path: packsPath } : {}),
    ...(ref !== null ? { ref } : {}),
    ...accessFields(form.access),
    ...(form.insecureHttp && url.toLowerCase().startsWith("http://")
      ? { insecure_http: true }
      : {}),
    replace_builtin: form.replaceBuiltin,
    track: form.track,
  };
};

export type EditSourceForm = {
  label: string;
  packsPath: string;
  ref: string;
  access: AccessChoice;
  replaceBuiltin: boolean;
  track: boolean;
};

/**
 * Тело «Изменить»: только изменённые поля. Пустой ref у git это ветка по умолчанию
 * (сервер принимает пустую строку как сброс).
 */
export const updateRequest = (
  source: CatalogSource,
  form: EditSourceForm,
): UpdateSourceRequest => {
  const body: UpdateSourceRequest = {};
  const label = form.label.trim();
  if (label !== "" && label !== source.label) body.label = label;
  const packsPath = form.packsPath.trim();
  if (packsPath !== "" && packsPath !== source.packs_path) {
    body.packs_path = packsPath;
  }
  if (source.kind === "git") {
    const ref = form.ref.trim();
    if (ref !== (source.ref ?? "")) body.ref = ref;
    Object.assign(body, accessUpdate(source, form.access));
    if (form.track !== source.track) body.track = form.track;
  }
  if (form.replaceBuiltin !== source.replace_builtin) {
    body.replace_builtin = form.replaceBuiltin;
  }
  return body;
};
