// «Скопировать как пресет шаблона» (docs/design/template-studio.md, 13): места подписей и метки даты
// документа проекта переводятся в фрагмент `version.yaml` пака (`placements` и `default_dates` слотов,
// signing-route.md, 15.3). Модуль чистый: состояние подписей, документы проекта и каталог версии ему
// передают, на сервер он не ходит.

/** Лист A4 и рамка места подписи из пака: те же границы, что у `parse_slot_placement` на сервере. */
const SHEET_WIDTH_MM = 210;
const SHEET_HEIGHT_MM = 297;
const PLACE_MIN_WIDTH_MM = 10;
const PLACE_MAX_WIDTH_MM = 200;
const PLACE_MAX_Y_MM = 287;
/** Допуск края листа, как `+ 0.01` в проверках сервера. */
const EDGE_TOLERANCE_MM = 0.01;
/** Не больше восьми меток даты у слота документа (`MAX_DATE_MARKS`). */
export const PRESET_MAX_DATE_MARKS = 8;

/** Разделитель экземпляра «{def_id}--{slug}» у документов и слотов команды (`OWNER_SEPARATOR`). */
const OWNER_SEPARATOR = "--";

export type PresetDateMark = {
  page: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
  format: string;
  align: string;
};

export type PresetPlacement = {
  enabled: boolean;
  page: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  dates?: readonly PresetDateMark[];
  /** `pack`: место как в шаблоне, выводится без округления с пометкой. */
  origin?: "pack" | "seed" | "manual" | undefined;
};

export type PresetSlotDef = {
  id: string;
  /** Id определений документов пака. */
  applies_to: readonly string[];
  per_author?: boolean | undefined;
};

export type PresetDocDef = {
  id: string;
  /** `shared` или `author` (личный документ в команде). */
  scope?: string | undefined;
};

export type PresetProjectDoc = {
  /** Id экземпляра: `report` или `report--ivanov`. */
  id: string;
  def_id?: string | null | undefined;
};

export type PackPresetInput = {
  /** `SignaturesStateResponse.placements`: документ → слот → место. */
  placements: Readonly<
    Record<string, Readonly<Record<string, PresetPlacement>>>
  >;
  /** Документы проекта в порядке проекта: первый автор раньше второго. */
  documents: readonly PresetProjectDoc[];
  pack: {
    packId: string;
    templateId: string;
    version: string;
    slots: readonly PresetSlotDef[];
    documents: readonly PresetDocDef[];
    supportedStaffing: readonly string[];
  };
  /** Какие документы проекта брать (id экземпляров); null или без поля все. */
  docIds?: readonly string[] | null;
  /** Брать и выключенные места (затравки). */
  includeDisabled?: boolean;
  /** Строки комментариев: язык выбирает вызывающий. */
  texts: PackPresetTexts;
};

export type PackPresetTexts = {
  /** Первая строка шапки: пак, шаблон, версия. */
  header: string;
  /** Вторая строка шапки: куда переносить. */
  hint: string;
  /** Комментарий у места, которое как в шаблоне. */
  asInPack: string;
};

export type PlaceProblem = "page" | "width" | "edge" | "top";
export type DateProblem = "page" | "size" | "edge";

export type PackPresetWarning =
  | { code: "custom_slot"; slot: string }
  | { code: "not_applicable"; slot: string; doc: string }
  | { code: "per_author_shared"; slot: string; doc: string }
  | {
      code: "duplicate";
      slot: string;
      doc: string;
      kept: string;
      skipped: string[];
    }
  | { code: "invalid_place"; slot: string; doc: string; problem: PlaceProblem }
  | {
      code: "invalid_date";
      slot: string;
      doc: string;
      index: number;
      problem: DateProblem;
    }
  | { code: "too_many_dates"; slot: string; doc: string; dropped: number }
  | { code: "disabled"; count: number };

export type PackPresetEntry = {
  slot: string;
  doc: string;
  place: { page: number; x_mm: number; y_mm: number; width_mm: number };
  dates: PresetDateMark[];
  asInPack: boolean;
};

export type PackPreset = {
  /** YAML-фрагмент; пустая строка, если переносить нечего. */
  yaml: string;
  entries: PackPresetEntry[];
  warnings: PackPresetWarning[];
};

/** «report--ivanov» → «report»; id без разделителя остаётся как есть. */
const baseId = (id: string): string => {
  const at = id.lastIndexOf(OWNER_SEPARATOR);
  return at > 0 ? id.slice(0, at) : id;
};

const mm = (value: number): number => Math.round(value) + 0;

/** Место до 1 мм; ширина не меньше 10 мм; рамку, которую округление вытолкнуло за край, сужает. */
const roundPlace = (p: PresetPlacement): PackPresetEntry["place"] => {
  const x = mm(p.x_mm);
  let width = Math.max(PLACE_MIN_WIDTH_MM, mm(p.width_mm));
  if (
    x + width > SHEET_WIDTH_MM &&
    p.x_mm + p.width_mm <= SHEET_WIDTH_MM + EDGE_TOLERANCE_MM
  ) {
    width = Math.max(PLACE_MIN_WIDTH_MM, SHEET_WIDTH_MM - x);
  }
  return { page: p.page, x_mm: x, y_mm: mm(p.y_mm), width_mm: width };
};

const roundDate = (d: PresetDateMark): PresetDateMark => {
  const x = mm(d.x_mm);
  const y = mm(d.y_mm);
  let width = Math.max(1, mm(d.width_mm));
  let height = Math.max(1, mm(d.height_mm));
  if (
    x + width > SHEET_WIDTH_MM &&
    d.x_mm + d.width_mm <= SHEET_WIDTH_MM + EDGE_TOLERANCE_MM
  ) {
    width = Math.max(1, SHEET_WIDTH_MM - x);
  }
  if (
    y + height > SHEET_HEIGHT_MM &&
    d.y_mm + d.height_mm <= SHEET_HEIGHT_MM + EDGE_TOLERANCE_MM
  ) {
    height = Math.max(1, SHEET_HEIGHT_MM - y);
  }
  return { ...d, x_mm: x, y_mm: y, width_mm: width, height_mm: height };
};

/** Проверка места как `parse_slot_placement`: null, если лоадер пака его примет. */
export const placeProblem = (
  p: PackPresetEntry["place"],
): PlaceProblem | null => {
  if (p.page < 1) return "page";
  if (p.width_mm < PLACE_MIN_WIDTH_MM || p.width_mm > PLACE_MAX_WIDTH_MM)
    return "width";
  if (p.x_mm < 0 || p.x_mm + p.width_mm > SHEET_WIDTH_MM + EDGE_TOLERANCE_MM)
    return "edge";
  if (p.y_mm < 0 || p.y_mm > PLACE_MAX_Y_MM) return "top";
  return null;
};

/** Проверка метки даты как `frame_problem` с листом A4 (разбор `default_dates`). */
export const dateProblem = (d: PresetDateMark): DateProblem | null => {
  if (d.page < 1) return "page";
  if (d.width_mm <= 0 || d.height_mm <= 0) return "size";
  if (
    d.x_mm < 0 ||
    d.y_mm < 0 ||
    d.x_mm + d.width_mm > SHEET_WIDTH_MM + EDGE_TOLERANCE_MM ||
    d.y_mm + d.height_mm > SHEET_HEIGHT_MM + EDGE_TOLERANCE_MM
  )
    return "edge";
  return null;
};

const sameEntry = (a: PackPresetEntry, b: PackPresetEntry): boolean =>
  JSON.stringify([a.place, a.dates]) === JSON.stringify([b.place, b.dates]);

// Ключ YAML без кавычек, если он не похож на число, булево или null.
const YAML_PLAIN = /^[A-Za-z_][A-Za-z0-9_.-]*$/;
const YAML_RESERVED = /^(y|n|yes|no|on|off|true|false|null|~)$/i;
const key = (value: string): string =>
  YAML_PLAIN.test(value) && !YAML_RESERVED.test(value)
    ? value
    : JSON.stringify(value);

const num = (value: number): string => String(Math.round(value * 100) / 100);

const flowPlace = (p: PackPresetEntry["place"]): string =>
  `{ page: ${num(p.page)}, x_mm: ${num(p.x_mm)}, y_mm: ${num(p.y_mm)}, width_mm: ${num(p.width_mm)} }`;

// Порядок ключей как в справке пака; `align` только если не `center` (значение лоадера по умолчанию).
const flowDate = (d: PresetDateMark): string =>
  `{ page: ${num(d.page)}, x_mm: ${num(d.x_mm)}, y_mm: ${num(d.y_mm)}, width_mm: ${num(d.width_mm)}, height_mm: ${num(d.height_mm)}, format: ${key(d.format)}${
    d.align === "center" ? "" : `, align: ${key(d.align)}`
  } }`;

const comment = (text: string): string =>
  text
    .split("\n")
    .map((line) => `# ${line}`.trimEnd())
    .join("\n");

const render = (
  entries: readonly PackPresetEntry[],
  slotOrder: readonly string[],
  texts: PackPresetTexts,
): string => {
  if (entries.length === 0) return "";
  const lines = [
    comment(texts.header),
    comment(texts.hint),
    "signatures:",
    "  slots:",
  ];
  for (const slot of slotOrder) {
    const own = entries.filter((e) => e.slot === slot);
    if (own.length === 0) continue;
    lines.push(`    - id: ${key(slot)}`, "      placements:");
    for (const e of own) {
      const note = e.asInPack ? `  # ${texts.asInPack}` : "";
      lines.push(`        ${key(e.doc)}: ${flowPlace(e.place)}${note}`);
    }
    const dated = own.filter((e) => e.dates.length > 0);
    if (dated.length > 0) {
      lines.push("      default_dates:");
      for (const e of dated) {
        lines.push(`        ${key(e.doc)}:`);
        for (const d of e.dates) lines.push(`          - ${flowDate(d)}`);
      }
    }
  }
  return `${lines.join("\n")}\n`;
};

/**
 * Пресет мест подписей пака по состоянию подписей проекта (template-studio.md, 13).
 *
 * Экземпляры документов и слотов команды приводятся к id пака (`report--ivanov` → `report`,
 * `author--ivanov` → `author`); при двух разных местах одной пары берётся первое по порядку документов
 * проекта. Свои слоты проекта, неприменимые к документу слоты, место `per_author` на общем документе
 * командного шаблона и выключенные места пропускаются. Координаты округляются до 1 мм, кроме мест как в
 * шаблоне; что лоадер пака не примет, пропускается с предупреждением. Имён людей и проекта в YAML нет.
 */
export const buildPackPresetYaml = (input: PackPresetInput): PackPreset => {
  const { pack, texts } = input;
  const warnings: PackPresetWarning[] = [];
  const slotById = new Map(pack.slots.map((s) => [s.id, s]));
  const docDefById = new Map(pack.documents.map((d) => [d.id, d]));
  const teamCapable = pack.supportedStaffing.includes("team");
  const defOf = new Map(
    input.documents.map((d) => [d.id, d.def_id ?? baseId(d.id)]),
  );

  // Порядок документов: как в проекте, затем те, что есть только в состоянии подписей.
  const projectOrder = input.documents.map((d) => d.id);
  const docKeys = [
    ...projectOrder.filter((id) => id in input.placements),
    ...Object.keys(input.placements).filter((id) => !defOf.has(id)),
  ].filter((id) => input.docIds == null || input.docIds.includes(id));

  const kept = new Map<string, { entry: PackPresetEntry; from: string }>();
  const duplicates = new Map<string, string[]>();
  const customSlots = new Set<string>();
  let disabled = 0;

  for (const docKey of docKeys) {
    const defId = defOf.get(docKey) ?? baseId(docKey);
    const bySlot = input.placements[docKey] ?? {};
    for (const [runtimeSlot, placement] of Object.entries(bySlot)) {
      const slotDef =
        slotById.get(runtimeSlot) ??
        (slotById.get(baseId(runtimeSlot))?.per_author === true
          ? slotById.get(baseId(runtimeSlot))
          : undefined);
      if (slotDef === undefined) {
        customSlots.add(runtimeSlot);
        continue;
      }
      if (!placement.enabled && input.includeDisabled !== true) {
        disabled += 1;
        continue;
      }
      const slot = slotDef.id;
      if (!slotDef.applies_to.includes(defId)) {
        warnings.push({ code: "not_applicable", slot, doc: defId });
        continue;
      }
      if (
        slotDef.per_author === true &&
        teamCapable &&
        (docDefById.get(defId)?.scope ?? "shared") === "shared"
      ) {
        warnings.push({ code: "per_author_shared", slot, doc: defId });
        continue;
      }

      const asInPack = placement.origin === "pack";
      const place = asInPack
        ? {
            page: placement.page,
            x_mm: placement.x_mm,
            y_mm: placement.y_mm,
            width_mm: placement.width_mm,
          }
        : roundPlace(placement);
      const problem = placeProblem(place);
      if (problem !== null) {
        warnings.push({ code: "invalid_place", slot, doc: defId, problem });
        continue;
      }

      const rawDates = placement.dates ?? [];
      const dates: PresetDateMark[] = [];
      rawDates.slice(0, PRESET_MAX_DATE_MARKS).forEach((raw, index) => {
        const mark: PresetDateMark = {
          page: raw.page,
          x_mm: raw.x_mm,
          y_mm: raw.y_mm,
          width_mm: raw.width_mm,
          height_mm: raw.height_mm,
          format: raw.format,
          align: raw.align,
        };
        const date = asInPack ? mark : roundDate(mark);
        const dp = dateProblem(date);
        if (dp !== null) {
          warnings.push({
            code: "invalid_date",
            slot,
            doc: defId,
            index: index + 1,
            problem: dp,
          });
          return;
        }
        dates.push(date);
      });
      if (rawDates.length > PRESET_MAX_DATE_MARKS) {
        warnings.push({
          code: "too_many_dates",
          slot,
          doc: defId,
          dropped: rawDates.length - PRESET_MAX_DATE_MARKS,
        });
      }

      const entry: PackPresetEntry = {
        slot,
        doc: defId,
        place,
        dates,
        asInPack,
      };
      const pair = `${slot}\u0000${defId}`;
      const first = kept.get(pair);
      if (first === undefined) {
        kept.set(pair, { entry, from: docKey });
      } else if (!sameEntry(first.entry, entry)) {
        duplicates.set(pair, [...(duplicates.get(pair) ?? []), docKey]);
      }
    }
  }

  for (const [pair, skipped] of duplicates) {
    const first = kept.get(pair);
    if (first === undefined) continue;
    warnings.push({
      code: "duplicate",
      slot: first.entry.slot,
      doc: first.entry.doc,
      kept: first.from,
      skipped,
    });
  }
  warnings.unshift(
    ...[...customSlots].map((slot): PackPresetWarning => ({
      code: "custom_slot",
      slot,
    })),
  );
  if (disabled > 0) warnings.push({ code: "disabled", count: disabled });
  // Два экземпляра одного документа дают одно и то же предупреждение: показываем его раз.
  const seen = new Set<string>();
  const unique = warnings.filter((w) => {
    const id = JSON.stringify(w);
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });

  // Слоты в порядке каталога, документы в порядке версии пака.
  const docRank = new Map(pack.documents.map((d, i) => [d.id, i]));
  const rank = (doc: string): number =>
    docRank.get(doc) ?? pack.documents.length;
  const entries = [...kept.values()]
    .map((k) => k.entry)
    .sort((a, b) => rank(a.doc) - rank(b.doc));
  const slotOrder = pack.slots.map((s) => s.id);
  const ordered = slotOrder.flatMap((slot) =>
    entries.filter((e) => e.slot === slot),
  );
  return {
    yaml: render(ordered, slotOrder, texts),
    entries: ordered,
    warnings: unique,
  };
};
