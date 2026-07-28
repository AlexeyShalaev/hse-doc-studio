// Minimal structural shape these helpers need from a meta-field definition.
// Kept local (and permissive about null/undefined) so shared/ doesn't depend on
// the entity's zod-inferred type while still accepting it verbatim.
export type MetaFieldDefaultSource = {
  type: string;
  default?: unknown;
  auto?: string | null | undefined;
};

// HSE academic year starts on September 1. From September onward the running
// academic year ends (defense happens) in the NEXT calendar year. JS months are
// 0-indexed, so September is month index 8.
const ACADEMIC_YEAR_START_MONTH_INDEX = 8;

/**
 * End year of the HSE academic year containing `today` — the defense year.
 * Sep–Dec → next calendar year; Jan–Aug → current. Mirrors the backend
 * `academic_year_end` so a project gets the same value whichever side fills it.
 */
export const academicYearEnd = (today: Date = new Date()): number =>
  today.getMonth() >= ACADEMIC_YEAR_START_MONTH_INDEX
    ? today.getFullYear() + 1
    : today.getFullYear();

/** Resolve a meta field's computed `auto` value (e.g. "academic_year"). */
export const resolveMetaAuto = (
  auto: string | null | undefined,
  today: Date = new Date(),
): string | undefined => {
  if (auto === "academic_year") return String(academicYearEnd(today));
  return undefined;
};

// Only textual fields are pre-filled from default/auto; bool (nda) and person
// fields have their own editors and must not be seeded as strings.
const isTextualMetaField = (def: MetaFieldDefaultSource): boolean =>
  def.type === "string" || def.type === "select";

/**
 * The value to pre-fill for a field when the user hasn't entered one. The
 * computed `auto` wins over the static `default` when both are declared. Returns
 * undefined for non-textual fields and non-string/number defaults (e.g. the
 * boolean `nda` default), so seeding never writes "false" into a text field.
 */
export const metaFieldDefault = (
  def: MetaFieldDefaultSource,
  today: Date = new Date(),
): string | undefined => {
  if (!isTextualMetaField(def)) return undefined;
  const auto = resolveMetaAuto(def.auto, today);
  if (auto !== undefined) return auto;
  if (typeof def.default === "string") return def.default;
  if (typeof def.default === "number") return String(def.default);
  return undefined;
};

// Structural shape for kind-visibility (permissive about null/undefined).
export type MetaFieldKindSource = { supported_kinds?: string[] | null };

/**
 * Whether a meta field is shown for the given project kind. An empty/absent
 * `supported_kinds` means "shown for every kind". E.g. `manuals` (РП/РО) is
 * `[project]`, so it's hidden in research projects (no software manuals there).
 */
export const metaFieldVisibleForKind = (
  def: MetaFieldKindSource,
  kind: string | null | undefined,
): boolean =>
  !kind ||
  !def.supported_kinds ||
  def.supported_kinds.length === 0 ||
  def.supported_kinds.includes(kind);

/** A meta value counts as "filled" only when it's a non-blank string. */
export const isMetaValueBlank = (value: unknown): boolean =>
  value === null ||
  value === undefined ||
  (typeof value === "string" && value.trim() === "");

/**
 * Build a patch of default/auto values for every field whose current value is
 * still undefined (never touched). Empty strings are left alone so clearing a
 * pre-filled field doesn't immediately re-seed it.
 */
export const seedMetaDefaults = (
  metaFields: Record<string, MetaFieldDefaultSource>,
  current: Record<string, unknown>,
  today: Date = new Date(),
): Record<string, unknown> => {
  const patch: Record<string, unknown> = {};
  for (const [key, def] of Object.entries(metaFields)) {
    if (current[key] !== undefined) continue;
    const value = metaFieldDefault(def, today);
    if (value !== undefined) patch[key] = value;
  }
  return patch;
};
