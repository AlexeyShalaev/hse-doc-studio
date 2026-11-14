// «Скопировать как пресет шаблона» (docs/design/template-studio.md, 13): места подписей и метки даты
// документа проекта переводятся в фрагмент `version.yaml` пака (`placements` и `default_dates` слотов,
// signing-route.md, 15.3). Модуль чистый: состояние подписей, документы проекта и каталог версии ему
// передают, на сервер он не ходит.
//
// Якоря (signing-route.md, 15.17.12): место «из шаблона» на якоре выводится записью пака как есть;
// ручное место на документе, у сборки которого есть якорь с id слота на той же странице, выводится
// относительно него (комментарий с мм этой сборки), метка даты так же по якорю `<слот>.<формат>`;
// без якорей место и метка в мм с комментарием «якоря нет».

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
  /** `anchor`: место как в шаблоне стоит на строке шаблона, выводится записью пака (15.17.12). */
  source?: "anchor" | "mm" | null | undefined;
};

/** Запасное место записи на якоре в мм. */
type PresetMmPlace = {
  page: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
};

/** Место подписи на якоре в записи пака (15.17.7): поля по умолчанию в YAML не пишутся. */
export type PresetAnchorPlace = {
  anchor: string;
  align: string;
  dx_mm: number;
  dy_mm: number;
  /** null: ширина линии. */
  width_mm: number | null;
  fallback: PresetMmPlace | null;
};

/** Метка даты на якоре в записи пака (15.17.7). */
export type PresetAnchorDate = {
  anchor: string;
  format: string;
  align: string;
  height_mm: number;
  width_mm: number | null;
  dx_mm: number;
  /** null: минус высота, метка стоит на линии. */
  dy_mm: number | null;
  fallback: (PresetMmPlace & { height_mm: number }) | null;
};

/** Записи пака по документам у рантайм-слота (`RuntimeSlotResponse`): место на якоре выводится как есть. */
export type PresetRuntimeSlot = {
  id: string;
  default_placements?:
    | Readonly<
        Record<
          string,
          | ({ source: "anchor" } & PresetAnchorPlace)
          | ({ source: "mm" } & PresetMmPlace)
        >
      >
    | undefined;
  default_dates?:
    | Readonly<
        Record<
          string,
          readonly (
            | ({ source: "anchor" } & PresetAnchorDate)
            | ({ source: "mm" } & PresetDateMark)
          )[]
        >
      >
    | undefined;
};

/** Якорь сборки (`SignaturesStateResponse.anchors`): мм от левого верхнего угла, `y_mm` базовая линия. */
export type PresetBuildAnchor = {
  id: string;
  kind: "sign" | "date";
  page: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
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
  /** Рантайм-слоты проекта: записи пака на якоре для мест «из шаблона» (15.17.12). */
  runtimeSlots?: readonly PresetRuntimeSlot[];
  /**
   * Якоря сборки по документам проекта (`SignaturesStateResponse.anchors`, null неизвестны). Без поля
   * вывод без якорей, как до них: места в мм без комментария.
   */
  anchors?: Readonly<
    Record<string, { items: readonly PresetBuildAnchor[] } | null>
  >;
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
  /** Строка шапки, если во фрагменте есть места на якорях: по какой сборке и почему они не зависят от данных. */
  anchorsHeader?: string;
  /** Комментарий у места относительно якоря: «по сборке», дальше мм этой сборки. */
  byBuild?: string;
  /** Комментарий у места в мм, когда якоря неизвестны или нужного нет. */
  noAnchor?: string;
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

/** Метка даты в выводе: на якоре (с мм этой сборки или как в паке) или в мм с комментарием. */
export type PresetDateOut = {
  /** Метка этой сборки в мм; у метки пака на якоре без запасного места null. */
  mark: PresetDateMark | null;
  anchor: PresetAnchorDate | null;
  note: "as_in_pack" | "by_build" | "no_anchor" | null;
};

export type PackPresetEntry = {
  slot: string;
  doc: string;
  place: { page: number; x_mm: number; y_mm: number; width_mm: number };
  dates: PresetDateMark[];
  asInPack: boolean;
  /** Место на якоре: запись пака как есть или относительно якоря сборки (15.17.12). */
  anchorPlace?: PresetAnchorPlace;
  /** `by_build`: место относительно якоря, в комментарии мм этой сборки; `no_anchor`: мм без якоря. */
  note?: "by_build" | "no_anchor";
  /** Метки даты в выводе с якорями; без поля метки идут из `dates` в мм. */
  dateOut?: PresetDateOut[];
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
  JSON.stringify([a.place, a.dates, a.anchorPlace, a.dateOut]) ===
  JSON.stringify([b.place, b.dates, b.anchorPlace, b.dateOut]);

/** До 0,1 мм, как отпечаток места (15.4). */
const tenth = (value: number): number => Math.round(value * 10) / 10 + 0;

/** Верх рамки подписи на якоре по умолчанию и высота метки даты (лоадер пака, 15.17.7). */
const ANCHOR_DEFAULT_DY_MM = -10;
const ANCHOR_DATE_HEIGHT_MM = 5;

/** Левый край рамки ширины `width` на линии при выравнивании `align` (15.17.8), до `dx_mm`. */
const alignedX = (
  line: PresetBuildAnchor,
  align: string,
  width: number,
): number =>
  align === "right"
    ? line.x_mm + line.width_mm - width
    : align === "center"
      ? line.x_mm + (line.width_mm - width) / 2
      : line.x_mm;

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

/** Запись места на якоре: `anchor` и только поля, отличные от значений лоадера по умолчанию. */
const flowAnchorPlace = (a: PresetAnchorPlace): string => {
  const parts = [`anchor: ${key(a.anchor)}`];
  if (a.align !== "center") parts.push(`align: ${key(a.align)}`);
  if (a.dx_mm !== 0) parts.push(`dx_mm: ${num(a.dx_mm)}`);
  if (a.dy_mm !== ANCHOR_DEFAULT_DY_MM) parts.push(`dy_mm: ${num(a.dy_mm)}`);
  const width = a.width_mm ?? a.fallback?.width_mm ?? null;
  if (width !== null) parts.push(`width_mm: ${num(width)}`);
  if (a.fallback !== null)
    parts.push(
      `page: ${num(a.fallback.page)}`,
      `x_mm: ${num(a.fallback.x_mm)}`,
      `y_mm: ${num(a.fallback.y_mm)}`,
    );
  return `{ ${parts.join(", ")} }`;
};

/** Запись метки даты на якоре; `format` только если он не часть якоря. */
const flowAnchorDate = (d: PresetAnchorDate): string => {
  const parts = [`anchor: ${key(d.anchor)}`];
  if (d.anchor.slice(d.anchor.indexOf(".") + 1) !== d.format)
    parts.push(`format: ${key(d.format)}`);
  if (d.align !== "center") parts.push(`align: ${key(d.align)}`);
  if (d.height_mm !== ANCHOR_DATE_HEIGHT_MM)
    parts.push(`height_mm: ${num(d.height_mm)}`);
  const width = d.width_mm ?? d.fallback?.width_mm ?? null;
  if (width !== null) parts.push(`width_mm: ${num(width)}`);
  if (d.dx_mm !== 0) parts.push(`dx_mm: ${num(d.dx_mm)}`);
  if (d.dy_mm !== null) parts.push(`dy_mm: ${num(d.dy_mm)}`);
  if (d.fallback !== null)
    parts.push(
      `page: ${num(d.fallback.page)}`,
      `x_mm: ${num(d.fallback.x_mm)}`,
      `y_mm: ${num(d.fallback.y_mm)}`,
    );
  return `{ ${parts.join(", ")} }`;
};

/** Мм этой сборки в комментарии: «1, 168, 177, 28». */
const mmList = (values: readonly number[]): string =>
  values.map(num).join(", ");

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
  const onAnchors = entries.some(
    (e) =>
      e.anchorPlace !== undefined ||
      (e.dateOut ?? []).some((d) => d.anchor !== null),
  );
  const lines = [
    comment(texts.header),
    comment(texts.hint),
    ...(onAnchors && texts.anchorsHeader !== undefined
      ? [comment(texts.anchorsHeader)]
      : []),
    "signatures:",
    "  slots:",
  ];
  const tail = (text: string | undefined): string =>
    text === undefined ? "" : `  # ${text}`;
  const byBuild = (values: readonly number[]): string =>
    tail(
      texts.byBuild === undefined
        ? undefined
        : `${texts.byBuild}: ${mmList(values)}`,
    );
  for (const slot of slotOrder) {
    const own = entries.filter((e) => e.slot === slot);
    if (own.length === 0) continue;
    lines.push(`    - id: ${key(slot)}`, "      placements:");
    for (const e of own) {
      const p = e.place;
      const note = e.asInPack
        ? tail(texts.asInPack)
        : e.note === "by_build"
          ? byBuild([p.page, p.x_mm, p.y_mm, p.width_mm])
          : e.note === "no_anchor"
            ? tail(texts.noAnchor)
            : "";
      const flow =
        e.anchorPlace === undefined
          ? flowPlace(e.place)
          : flowAnchorPlace(e.anchorPlace);
      lines.push(`        ${key(e.doc)}: ${flow}${note}`);
    }
    const dated = own.filter((e) => (e.dateOut ?? e.dates).length > 0);
    if (dated.length > 0) {
      lines.push("      default_dates:");
      for (const e of dated) {
        lines.push(`        ${key(e.doc)}:`);
        if (e.dateOut === undefined) {
          for (const d of e.dates) lines.push(`          - ${flowDate(d)}`);
          continue;
        }
        for (const d of e.dateOut) {
          const flow =
            d.anchor !== null
              ? flowAnchorDate(d.anchor)
              : d.mark !== null
                ? flowDate(d.mark)
                : null;
          if (flow === null) continue;
          const m = d.mark;
          const note =
            d.note === "as_in_pack"
              ? tail(texts.asInPack)
              : d.note === "by_build" && m !== null
                ? byBuild([m.page, m.x_mm, m.y_mm, m.width_mm, m.height_mm])
                : d.note === "no_anchor"
                  ? tail(texts.noAnchor)
                  : "";
          lines.push(`          - ${flow}${note}`);
        }
      }
    }
  }
  return `${lines.join("\n")}\n`;
};

/** Линия якоря `id` вида `kind` на странице `page` в сборке документа; null, если её нет. */
const lineOf = (
  anchors: { items: readonly PresetBuildAnchor[] } | null | undefined,
  kind: "sign" | "date",
  id: string,
  page: number,
): PresetBuildAnchor | null =>
  anchors?.items.find(
    (a) => a.kind === kind && a.id === id && a.page === page,
  ) ?? null;

/** Ручное место относительно линии якоря: выравнивание по левому краю, смещения до 0,1 мм. */
const relativePlace = (
  slot: string,
  place: PackPresetEntry["place"],
  line: PresetBuildAnchor,
): PresetAnchorPlace => ({
  anchor: slot,
  align: "left",
  dx_mm: tenth(place.x_mm - line.x_mm),
  dy_mm: tenth(place.y_mm - line.y_mm),
  width_mm: place.width_mm,
  fallback: null,
});

/** Метка даты относительно линии якоря; выравнивание метки остаётся (оно же выравнивание текста). */
const relativeDate = (
  anchor: string,
  mark: PresetDateMark,
  line: PresetBuildAnchor,
): PresetAnchorDate => {
  const width = tenth(mark.width_mm);
  const height = tenth(mark.height_mm);
  const dy = tenth(mark.y_mm - line.y_mm);
  return {
    anchor,
    format: mark.format,
    align: mark.align,
    height_mm: height,
    width_mm: width,
    dx_mm: tenth(mark.x_mm - alignedX(line, mark.align, width)),
    // Метка стоит на линии: верх на её высоту выше, как по умолчанию у лоадера.
    dy_mm: Math.abs(dy + height) < 0.05 ? null : dy,
    fallback: null,
  };
};

/** Запись пака на якоре без дискриминатора, как её пишет YAML. */
const packAnchorPlace = (
  entry: { source: "anchor" } & PresetAnchorPlace,
): PresetAnchorPlace => ({
  anchor: entry.anchor,
  align: entry.align,
  dx_mm: entry.dx_mm,
  dy_mm: entry.dy_mm,
  width_mm: entry.width_mm,
  fallback: entry.fallback,
});

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

      // Место «из шаблона» на якоре: запись пака как есть (15.17.12).
      const runtime = input.runtimeSlots?.find((r) => r.id === runtimeSlot);
      const packEntry = runtime?.default_placements?.[docKey];
      const packOnAnchor =
        placement.origin === "pack" &&
        placement.source === "anchor" &&
        packEntry?.source === "anchor"
          ? packEntry
          : null;
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
      // Метки до округления: смещение от якоря считается до 0,1 мм.
      const exactDates: PresetDateMark[] = [];
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
        exactDates.push(mark);
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
      if (packOnAnchor !== null) {
        entry.anchorPlace = packAnchorPlace(packOnAnchor);
        entry.dateOut = (runtime?.default_dates?.[docKey] ?? []).map(
          (mark): PresetDateOut =>
            mark.source === "anchor"
              ? {
                  mark: null,
                  anchor: {
                    anchor: mark.anchor,
                    format: mark.format,
                    align: mark.align,
                    height_mm: mark.height_mm,
                    width_mm: mark.width_mm,
                    dx_mm: mark.dx_mm,
                    dy_mm: mark.dy_mm,
                    fallback: mark.fallback,
                  },
                  note: null,
                }
              : {
                  mark: {
                    page: mark.page,
                    x_mm: mark.x_mm,
                    y_mm: mark.y_mm,
                    width_mm: mark.width_mm,
                    height_mm: mark.height_mm,
                    format: mark.format,
                    align: mark.align,
                  },
                  anchor: null,
                  note: null,
                },
        );
      } else if (input.anchors !== undefined && !asInPack) {
        // Ручное место: относительно якоря сборки с id слота на той же странице, иначе мм с пометкой.
        const anchors = input.anchors[docKey];
        const line = lineOf(anchors, "sign", slot, place.page);
        if (line === null) entry.note = "no_anchor";
        else {
          entry.anchorPlace = relativePlace(
            slot,
            { ...place, x_mm: placement.x_mm, y_mm: placement.y_mm },
            line,
          );
          entry.note = "by_build";
        }
        if (dates.length > 0)
          entry.dateOut = dates.map((mark, index): PresetDateOut => {
            const id = `${slot}.${mark.format}`;
            const dateLine = lineOf(anchors, "date", id, mark.page);
            return dateLine === null
              ? { mark, anchor: null, note: "no_anchor" }
              : {
                  mark,
                  anchor: relativeDate(id, exactDates[index] ?? mark, dateLine),
                  note: "by_build",
                };
          });
      }
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
