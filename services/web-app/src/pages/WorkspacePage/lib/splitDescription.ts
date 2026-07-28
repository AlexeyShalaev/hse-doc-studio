/**
 * Описание контрольной точки — это инструкция на 445–1489 символов (замерено по
 * реальным профилям пака): что загрузить, к какому сроку, с чьими подписями.
 * Целиком в подзаголовок она не помещается, а выбросить её нельзя — это самое
 * содержательное, что есть на экране.
 *
 * Поэтому текст режется надвое: ЛИД (первое предложение) работает подзаголовком
 * и виден всегда, ХВОСТ идёт во всю ширину под полосой статуса. Резать по
 * символам нельзя — лид оборвался бы на полуслове, поэтому ищем ближайшую
 * границу предложения.
 */
const LEAD_MAX_CHARS = 220;
const LEAD_MIN_CHARS = 60;

export type SplitDescription = {
  /** Первое предложение; пустое — описания нет вовсе. */
  lead: string;
  /** Остальной текст; пустое — описание уместилось в лид. */
  rest: string;
};

export const splitDescription = (text: string): SplitDescription => {
  const trimmed = text.trim();
  if (trimmed.length <= LEAD_MAX_CHARS) return { lead: trimmed, rest: "" };

  const head = trimmed.slice(0, LEAD_MAX_CHARS);
  const sentenceEnd = Math.max(
    head.lastIndexOf(". "),
    head.lastIndexOf("! "),
    head.lastIndexOf("? "),
    head.lastIndexOf(".\n"),
  );
  // Граница предложения нашлась достаточно далеко — режем по ней. Иначе по
  // последнему пробелу: длинное первое предложение лучше подрезать, чем
  // вывалить в лид 220 символов сплошняком.
  const cut =
    sentenceEnd > LEAD_MIN_CHARS ? sentenceEnd + 1 : head.lastIndexOf(" ");
  if (cut <= 0) return { lead: trimmed, rest: "" };

  return {
    lead: trimmed.slice(0, cut).trim(),
    rest: trimmed.slice(cut).trim(),
  };
};
