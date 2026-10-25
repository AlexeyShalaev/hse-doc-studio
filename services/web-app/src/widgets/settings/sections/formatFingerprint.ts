// Читаемый отпечаток: группы по 4 символа.
export const formatFingerprint = (fpr: string): string =>
  fpr.replace(/(.{4})/g, "$1 ").trim();
