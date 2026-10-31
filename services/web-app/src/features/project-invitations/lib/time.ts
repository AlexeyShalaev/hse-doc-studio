const DAY_MS = 86_400_000;

/** Сколько полных дней осталось до срока (0, если меньше суток); отрицательное значит просрочено. */
export const daysLeft = (iso: string, now: number = Date.now()): number => {
  const diff = new Date(iso).getTime() - now;
  return diff < 0 ? -1 : Math.floor(diff / DAY_MS);
};

export const formatDate = (iso: string, lang: string): string =>
  new Date(iso).toLocaleDateString(lang === "en" ? "en-GB" : "ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
