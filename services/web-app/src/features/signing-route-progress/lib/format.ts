import { localeTag } from "@shared/lib";

/** Короткая дата: 10.11 или 11/10 по языку интерфейса. */
export const formatDay = (iso: string): string =>
  new Date(iso).toLocaleDateString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
  });

/** Момент в течение ближайших суток: 10.11, 21:30. */
export const formatMoment = (ms: number): string =>
  new Date(ms).toLocaleString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

/** Абсолютная ссылка на адрес Студии: её отправляют человеку, которому нужно открыть страницу. */
export const absoluteUrl = (path: string): string =>
  new URL(path, window.location.origin).toString();

/** Скопировать в буфер; false, если браузер не дал (небезопасный адрес, запрет). */
export const copyText = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
};
