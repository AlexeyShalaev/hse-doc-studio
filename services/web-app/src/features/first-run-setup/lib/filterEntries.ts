import type { ProbeEntry } from "@entities/setup";

/**
 * Отбор по подстроке внутри УЖЕ показанной папки.
 *
 * Именно отбор, а не поиск вглубь: каждый спуск на уровень стоит запуска
 * контейнера, и рекурсивный обход десятка каталогов занял бы полминуты. А
 * решаемая задача другая — в домашней папке сотня подпапок, и мотать её мышкой
 * долго. Отбор по уже полученному списку мгновенен и покрывает этот случай
 * целиком.
 *
 * Совпадения с НАЧАЛА имени идут первыми: набирая «doc», человек ищет
 * «documents», а не «hse-doc-studio», хотя формально подходят обе.
 */
export const filterEntries = (
  entries: readonly ProbeEntry[],
  query: string,
): ProbeEntry[] => {
  const needle = query.trim().toLocaleLowerCase();
  if (needle === "") return [...entries];

  const starts: ProbeEntry[] = [];
  const contains: ProbeEntry[] = [];
  for (const entry of entries) {
    const name = entry.name.toLocaleLowerCase();
    if (name.startsWith(needle)) {
      starts.push(entry);
    } else if (name.includes(needle)) {
      contains.push(entry);
    }
  }
  return [...starts, ...contains];
};
