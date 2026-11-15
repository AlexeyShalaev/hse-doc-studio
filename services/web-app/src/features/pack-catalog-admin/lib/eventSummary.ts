import type { CatalogEvent } from "@entities/pack-catalog";
import { sourceErrorText } from "@entities/pack-catalog";
import { i18n } from "@shared/lib";

// Сводка события истории источника словами: что добавлено, что нашла проверка, почему
// отказ. Поля `summary` пишет сервер (use_cases/pack_catalog/service.py), незнакомые
// показываются как «ключ: значение».

const NS = "adminPackCatalog";
const SHOWN = new Set([
  "added",
  "catalog_revision",
  "new",
  "blockers",
  "packs",
  "error",
]);

const strings = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];

const plain = (value: unknown): string | null => {
  if (typeof value === "string") return value === "" ? null : value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
};

export const eventSummary = (event: CatalogEvent): string[] => {
  const summary = event.summary;
  const parts: string[] = [];
  const error = plain(summary.error);
  if (error !== null)
    parts.push(sourceErrorText({ code: error, detail: error }));
  if ("added" in summary) {
    const added = strings(summary.added);
    parts.push(
      added.length > 0
        ? i18n.t(`${NS}:history.summary.added`, {
            count: added.length,
            list: added.join(", "),
          })
        : i18n.t(`${NS}:history.summary.nothingAdded`),
    );
  }
  if (typeof summary.new === "number") {
    parts.push(i18n.t(`${NS}:history.summary.new`, { count: summary.new }));
  }
  for (const blocker of strings(summary.blockers)) {
    const key = `packCatalog:blocker.${blocker}`;
    parts.push(i18n.exists(key) ? i18n.t(key) : blocker);
  }
  const packs = strings(summary.packs);
  if (packs.length > 0) {
    parts.push(
      i18n.t(`${NS}:history.summary.packs`, { list: packs.join(", ") }),
    );
  }
  for (const [key, value] of Object.entries(summary)) {
    if (SHOWN.has(key)) continue;
    const text = plain(value);
    if (text !== null) parts.push(`${key}: ${text}`);
  }
  return parts;
};
