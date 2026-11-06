/** Мегабайты в «12 ГБ» / «12 GB»: единица приходит из словаря, здесь только число. */
export const gbOf = (mb: number | null): string | null =>
  mb === null ? null : String(Math.max(1, Math.round(mb / 1024)));
