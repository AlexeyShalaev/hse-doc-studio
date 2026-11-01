export type InstanceDraft = {
  name: string;
  public_url: string;
  docs_url: string;
};
export type InstanceIssue = "name_required" | "url_invalid" | "docs_invalid";

const LOCAL = new Set(["localhost", "127.0.0.1", "[::1]"]);

const parse = (value: string): URL | null => {
  try {
    return new URL(value);
  } catch {
    return null;
  }
};

/** Публичный адрес: https, либо http только для localhost; без пути-хвоста запросов и якорей. */
export const isPublicUrl = (value: string): boolean => {
  const url = parse(value.trim());
  if (!url || url.hostname === "") return false;
  if (url.search !== "" || url.hash !== "") return false;
  return (
    url.protocol === "https:" ||
    (url.protocol === "http:" && LOCAL.has(url.hostname))
  );
};

/** Ссылка на документацию: любой http(s) адрес. */
export const isWebUrl = (value: string): boolean => {
  const url = parse(value.trim());
  return (
    url !== null &&
    (url.protocol === "https:" || url.protocol === "http:") &&
    url.hostname !== ""
  );
};

/** Публичный адрес по http: сервер примет его только для localhost, остальное небезопасно. */
export const isInsecureUrl = (value: string): boolean =>
  parse(value.trim())?.protocol === "http:";

export const validateInstance = (
  draft: InstanceDraft,
): Partial<Record<keyof InstanceDraft, InstanceIssue>> => {
  const issues: Partial<Record<keyof InstanceDraft, InstanceIssue>> = {};
  if (draft.name.trim() === "") issues.name = "name_required";
  if (!isPublicUrl(draft.public_url)) issues.public_url = "url_invalid";
  if (draft.docs_url.trim() !== "" && !isWebUrl(draft.docs_url)) {
    issues.docs_url = "docs_invalid";
  }
  return issues;
};

export const TIMEOUT_MIN = 1;
export const TIMEOUT_MAX = 60;
export const RETENTION_MIN = 1;
export const RETENTION_MAX = 365;

/** Целое число в пределах; пустая или дробная строка не подходит. */
export const inRange = (value: string, min: number, max: number): boolean => {
  if (!/^\d+$/.test(value.trim())) return false;
  const n = Number(value);
  return n >= min && n <= max;
};
