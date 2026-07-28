import type { DockerUsage } from "@entities/docker-system";

// Fixed categorical order (never reordered by size) — each maps to one of the
// theme's --chart-N tokens (see index.css); "cache"/"other" are clutter, not a
// service identity, so they get a neutral ink step instead of a hue.
export const SERVICE_CATEGORIES = [
  { key: "compile", labelKey: "disk.categoryCompile", color: "var(--chart-1)" },
  {
    key: "languagetool",
    labelKey: "disk.categoryLanguagetool",
    color: "var(--chart-2)",
  },
  { key: "office", labelKey: "disk.categoryOffice", color: "var(--chart-3)" },
  { key: "ai", labelKey: "disk.categoryAi", color: "var(--chart-4)" },
  { key: "app", labelKey: "disk.categoryApp", color: "var(--chart-5)" },
] as const;

const CATEGORY_BY_KEY = new Map<string, (typeof SERVICE_CATEGORIES)[number]>(
  SERVICE_CATEGORIES.map((c) => [c.key, c]),
);

export const categoryColor = (category: string): string =>
  CATEGORY_BY_KEY.get(category)?.color ?? "var(--fg-3)";

export const categoryLabelKey = (category: string): string => {
  const known = CATEGORY_BY_KEY.get(category)?.labelKey;
  if (known) return known;
  return category === "dangling"
    ? "disk.categoryDangling"
    : "disk.categoryOtherShort";
};

export type Segment = {
  key: string;
  labelKey: string;
  color: string;
  bytes: number;
};

export const buildSegments = (usage: DockerUsage): Segment[] => {
  const byCategory = new Map<string, number>();
  for (const image of usage.images) {
    byCategory.set(
      image.category,
      (byCategory.get(image.category) ?? 0) + image.size_bytes,
    );
  }

  const segments: Segment[] = SERVICE_CATEGORIES.map((c) => ({
    key: c.key,
    labelKey: c.labelKey,
    color: c.color,
    bytes: byCategory.get(c.key) ?? 0,
  }));

  segments.push({
    key: "cache",
    labelKey: "disk.categoryCache",
    color: "var(--fg-3)",
    bytes: usage.build_cache_bytes,
  });

  // The backend already filters the usage to the app's own entities, so what's
  // left outside the service categories is: dangling leftovers, plus the
  // writable layers of managed containers and the managed volumes — docker
  // doesn't attribute those to a single image.
  const runtimeBytes =
    (byCategory.get("dangling") ?? 0) +
    usage.containers_total_bytes +
    usage.volumes_total_bytes;
  segments.push({
    key: "runtime",
    labelKey: "disk.categoryRuntime",
    color: "var(--fg-2)",
    bytes: runtimeBytes,
  });

  return segments.filter((s) => s.bytes > 0);
};
