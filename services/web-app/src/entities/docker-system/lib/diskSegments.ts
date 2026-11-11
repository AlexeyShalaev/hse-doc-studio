import type { DockerUsage } from "../api/dockerSystemApi";

/**
 * Categories of the «Диск» bar in their fixed order (never reordered by size):
 * the service categories map to the theme's --chart-N tokens (see index.css);
 * "cache" and "runtime" are clutter, not a service identity, so they get a
 * neutral ink step instead of a hue. The same keys come in a runner's disk
 * report (`docker.categories`), so the local «Диск» and «Диск раннера» paint
 * one picture.
 */
export const DISK_CATEGORIES = [
  { key: "compile", color: "var(--chart-1)" },
  { key: "languagetool", color: "var(--chart-2)" },
  { key: "office", color: "var(--chart-3)" },
  { key: "ai", color: "var(--chart-4)" },
  { key: "app", color: "var(--chart-5)" },
  { key: "cache", color: "var(--fg-3)" },
  { key: "runtime", color: "var(--fg-2)" },
] as const;

export type DiskCategoryKey = (typeof DISK_CATEGORIES)[number]["key"];

/** The image categories that name a Studio service (no cache/runtime). */
export const DISK_SERVICE_CATEGORIES: readonly DiskCategoryKey[] = [
  "compile",
  "languagetool",
  "office",
  "ai",
  "app",
];

const COLOR_BY_KEY = new Map<string, string>(
  DISK_CATEGORIES.map((c) => [c.key, c.color]),
);
const ORDER_BY_KEY = new Map<string, number>(
  DISK_CATEGORIES.map((c, i) => [c.key, i]),
);

/** Colour of a category; anything unknown (dangling, other) is neutral ink. */
export const diskCategoryColor = (category: string): string =>
  COLOR_BY_KEY.get(category) ?? "var(--fg-3)";

export type DiskCategoryBytes = { key: string; bytes: number };

export type DiskSegment = {
  key: string;
  /** Already translated: each screen brings its own dictionary. */
  label: string;
  color: string;
  bytes: number;
};

/**
 * Bytes per bar category of the local Docker usage, the same shape as a
 * runner report's `docker.categories`.
 */
export const dockerUsageCategories = (
  usage: DockerUsage,
): DiskCategoryBytes[] => {
  const byCategory = new Map<string, number>();
  for (const image of usage.images) {
    byCategory.set(
      image.category,
      (byCategory.get(image.category) ?? 0) + image.size_bytes,
    );
  }
  return [
    ...DISK_SERVICE_CATEGORIES.map((key) => ({
      key,
      bytes: byCategory.get(key) ?? 0,
    })),
    { key: "cache", bytes: usage.build_cache_bytes },
    // The backend already filters the usage to the app's own entities, so
    // what's left outside the service categories is: dangling leftovers, plus
    // the writable layers of managed containers and the managed volumes:
    // docker doesn't attribute those to a single image.
    {
      key: "runtime",
      bytes:
        (byCategory.get("dangling") ?? 0) +
        usage.containers_total_bytes +
        usage.volumes_total_bytes,
    },
  ];
};

/**
 * Bar segments: known categories in the fixed order, then unknown keys in the
 * order given (a screen may add its own, e.g. a runner's cache, with `color`);
 * empty categories are dropped.
 */
export const buildDiskSegments = (
  categories: readonly (DiskCategoryBytes & { color?: string })[],
  label: (key: string) => string,
): DiskSegment[] =>
  categories
    .map((c, index) => ({ c, index }))
    .filter(({ c }) => c.bytes > 0)
    .sort(
      (a, b) =>
        (ORDER_BY_KEY.get(a.c.key) ?? DISK_CATEGORIES.length + a.index) -
        (ORDER_BY_KEY.get(b.c.key) ?? DISK_CATEGORIES.length + b.index),
    )
    .map(({ c }) => ({
      key: c.key,
      label: label(c.key),
      color: c.color ?? diskCategoryColor(c.key),
      bytes: c.bytes,
    }));

export const diskSegmentsTotal = (segments: readonly DiskSegment[]): number =>
  segments.reduce((sum, s) => sum + s.bytes, 0);
