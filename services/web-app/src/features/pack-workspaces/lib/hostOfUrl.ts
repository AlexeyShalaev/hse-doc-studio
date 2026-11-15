/**
 * Хост адреса репозитория в нижнем регистре: по нему список доступов git
 * сужается до подходящих. ssh вида git@host:owner/repo тоже понимается; не адрес: null.
 */
export const hostOfUrl = (raw: string): string | null => {
  const text = raw.trim();
  if (text === "") return null;
  const scp = /^[\w.-]+@([\w.-]+):/.exec(text);
  if (scp?.[1]) return scp[1].toLowerCase();
  try {
    const host = new URL(text).hostname;
    return host === "" ? null : host.toLowerCase();
  } catch {
    return null;
  }
};
