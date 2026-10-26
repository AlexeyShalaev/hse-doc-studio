// Инициалы для кружка автора: первая буква имени и первая буква последнего слова.
// Для пустого имени возвращает «?».
export const initialsOf = (name: string): string => {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0] ? (Array.from(parts[0])[0] ?? "?") : "?";
  const lastPart = parts.length > 1 ? parts[parts.length - 1] : undefined;
  const second = lastPart ? (Array.from(lastPart)[0] ?? "") : "";
  return `${first}${second}`.toUpperCase();
};
