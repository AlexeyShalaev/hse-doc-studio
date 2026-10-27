import { localeTag } from "./i18n";

// Для размеров файлов (bundle, вложения); размеры Docker считает formatBytes.
// Размер файла для людей: Б, КБ, МБ, ГБ на языке интерфейса (степени 1024).
const UNITS = ["byte", "kilobyte", "megabyte", "gigabyte"] as const;

export const formatFileSize = (bytes: number): string => {
  let unitIndex = 0;
  let scaled = Math.max(0, bytes);
  while (scaled >= 1024 && unitIndex < UNITS.length - 1) {
    scaled /= 1024;
    unitIndex += 1;
  }
  return new Intl.NumberFormat(localeTag(), {
    style: "unit",
    unit: UNITS[unitIndex] ?? "byte",
    unitDisplay: "short",
    maximumFractionDigits: unitIndex === 0 ? 0 : scaled < 10 ? 1 : 0,
  }).format(scaled);
};
