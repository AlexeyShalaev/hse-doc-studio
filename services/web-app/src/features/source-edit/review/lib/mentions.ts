/** Упоминание, выбранное из подсказки: id для сервера и имя, которое вставлено в текст. */
export type PickedMention = { userId: string; name: string };

const TRIGGER = /(^|\s)@([\p{L}\p{N}._-]*)$/u;

/** Слово после `@` перед кареткой; null, если каретка не в упоминании. */
export const mentionQueryAt = (
  text: string,
  caret: number,
): { query: string; start: number } | null => {
  const match = TRIGGER.exec(text.slice(0, caret));
  if (!match) return null;
  const query = match[2] ?? "";
  return { query, start: caret - query.length - 1 };
};

/** Подставляет `@Имя ` вместо набранного `@запроса`. */
export const insertMention = (
  text: string,
  at: { start: number; query: string },
  name: string,
): { text: string; caret: number } => {
  const end = at.start + 1 + at.query.length;
  const inserted = `@${name} `;
  return {
    text: text.slice(0, at.start) + inserted + text.slice(end),
    caret: at.start + inserted.length,
  };
};

/** Только те выбранные упоминания, чьё `@Имя` осталось в тексте. */
export const mentionsInText = (
  text: string,
  picked: PickedMention[],
): string[] => [
  ...new Set(
    picked.filter((p) => text.includes(`@${p.name}`)).map((p) => p.userId),
  ),
];

/** Разбивает текст на обычные куски и `@упоминания` для подсветки. */
export const splitMentions = (
  text: string,
): { text: string; mention: boolean }[] => {
  const parts: { text: string; mention: boolean }[] = [];
  const re = /(^|\s)(@[\p{L}\p{N}._-]+)/gu;
  let last = 0;
  for (let m = re.exec(text); m !== null; m = re.exec(text)) {
    const start = m.index + (m[1]?.length ?? 0);
    if (start > last)
      parts.push({ text: text.slice(last, start), mention: false });
    parts.push({ text: m[2] ?? "", mention: true });
    last = start + (m[2]?.length ?? 0);
  }
  if (last < text.length)
    parts.push({ text: text.slice(last), mention: false });
  return parts;
};
