/** Число секунд в часы, минуты и секунды; подписи единиц подставляет вызывающий из локали. */
export const durationParts = (
  seconds: number,
): { h: number; m: number; s: number } => {
  const total = Math.max(0, Math.round(seconds));
  return {
    h: Math.floor(total / 3600),
    m: Math.floor((total % 3600) / 60),
    s: total % 60,
  };
};
