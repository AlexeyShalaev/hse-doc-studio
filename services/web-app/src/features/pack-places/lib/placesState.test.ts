import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { DateMarkInput } from "@entities/signature";
import {
  PackSignaturesSchema,
  type PackSignatures,
  type PackSignatureSlot,
} from "@entities/pack-studio";
import {
  bindingOf,
  dateMoveOpFrom,
  dateOpFrom,
  freeDateAnchors,
  marksBefore,
  placeOpFrom,
  stamperStateOf,
} from "./placesState";

// Эталон контракта: сборка заявления, у автора место на строке, у руководителя место по умолчанию,
// у консультанта строки в сборке нет.
const REPO = join(import.meta.dirname, "..", "..", "..", "..", "..", "..");
const FIXTURE = join(
  REPO,
  "contracts",
  "pack-studio",
  "fixtures",
  "PackSignatures",
  "with_build.json",
);
const DATA: PackSignatures = PackSignaturesSchema.parse(
  JSON.parse(readFileSync(FIXTURE, "utf8")),
);

const slot = (id: string): PackSignatureSlot => {
  const found = DATA.slots.find((s) => s.id === id);
  if (!found) throw new Error(id);
  return found;
};

/** Слот отчёта с метками даты: одна в мм, вторая на строке без рамки в этой сборке. */
const withDates: PackSignatureSlot = {
  ...slot("author"),
  document: {
    kind: "default",
    entry: slot("author").default_place,
    box: { page: 1, x_mm: 160, y_mm: 208, width_mm: 30 },
    anchor: null,
    dates: [
      {
        index: 0,
        entry: {
          source: "mm",
          page: 1,
          x_mm: 81,
          y_mm: 156,
          width_mm: 7,
          height_mm: 5,
          format: "day",
          align: "center",
        },
        box: {
          page: 1,
          x_mm: 81,
          y_mm: 156,
          width_mm: 7,
          height_mm: 5,
          format: "day",
          align: "center",
        },
        anchor: null,
      },
      {
        index: 1,
        entry: {
          source: "anchor",
          anchor: "author.month_word",
          format: "month_word",
          align: "center",
          height_mm: 5,
          width_mm: null,
          dx_mm: 0,
          dy_mm: null,
          fallback: null,
        },
        box: null,
        anchor: { id: "author.month_word", state: "missing" },
      },
      {
        index: 2,
        entry: {
          source: "mm",
          page: 1,
          x_mm: 100,
          y_mm: 156,
          width_mm: 10,
          height_mm: 5,
          format: "year",
          align: "left",
        },
        box: {
          page: 1,
          x_mm: 100,
          y_mm: 156,
          width_mm: 10,
          height_mm: 5,
          format: "year",
          align: "left",
        },
        anchor: null,
      },
    ],
  },
};

describe("состояние редактора мест пака", () => {
  it("рамки слотов документа сборки, место по умолчанию бледное, без места рамки нет", () => {
    const state = stamperStateOf(DATA, (s) => s.label);

    expect(state?.document).toBe("application");
    expect(state?.slotDefs.map((d) => d.id)).toEqual([
      "author",
      "supervisor",
      "consultant",
    ]);
    const placements = state?.state.placements.application ?? {};
    expect(placements.author).toMatchObject({
      enabled: true,
      x_mm: 135,
      y_mm: 201,
      width_mm: 30,
    });
    expect(placements.consultant?.enabled).toBe(false);
    // Место по умолчанию (и строка без сборки у консультанта) бледное.
    expect([...(state?.muted ?? [])]).toEqual(["supervisor", "consultant"]);
    expect(state?.state.slots.author?.png_path).toBeNull();
  });

  it("без сборки состояния нет", () => {
    expect(stamperStateOf({ ...DATA, build: null }, (s) => s.label)).toBe(null);
  });

  it("как стоит место: строка, нет строки, мм", () => {
    expect(bindingOf(slot("author"))).toBe("line");
    expect(bindingOf(slot("consultant"))).toBe("missing");
    expect(bindingOf(slot("supervisor"))).toBe("mm");
  });
});

describe("правки мест из жестов", () => {
  it("перетаскивание рамки по умолчанию даёт место документа", () => {
    expect(
      placeOpFrom(slot("supervisor"), "application", { x_mm: 62.4 }),
    ).toEqual({
      op: "set_place",
      slot: "supervisor",
      doc: "application",
      box: { page: 1, x_mm: 62.4, y_mm: 130, width_mm: 40 },
    });
  });

  it("щелчок без сдвига ничего не пишет", () => {
    expect(
      placeOpFrom(slot("supervisor"), "application", { x_mm: 110.2 }),
    ).toBeNull();
  });

  it("у слота без рамки в сборке перетаскивать нечего", () => {
    expect(
      placeOpFrom(slot("consultant"), "application", { x_mm: 10 }),
    ).toBeNull();
  });

  it("метка на странице двигается по индексу YAML, а не по номеру в списке", () => {
    const op = dateMoveOpFrom(withDates, "report", 1, {
      x_mm: 104,
      y_mm: 150,
      width_mm: 10,
      height_mm: 5,
    });

    expect(op).toEqual({
      op: "set_date",
      slot: "author",
      doc: "report",
      index: 2,
      mark: {
        page: 1,
        x_mm: 104,
        y_mm: 150,
        width_mm: 10,
        height_mm: 5,
        format: "year",
        align: "left",
      },
    });
  });
});

describe("правки меток даты из панели", () => {
  const before = marksBefore(withDates);
  const [first, second] = before as [DateMarkInput, DateMarkInput];

  it("в панели только метки этой сборки, id по индексу YAML", () => {
    expect(before.map((m) => m.id)).toEqual(["i0", "i2"]);
  });

  it("новая метка", () => {
    const added = { ...first, id: null, x_mm: 30 };
    expect(
      dateOpFrom("author", "report", before, { dates: [...before, added] }),
    ).toMatchObject({ op: "add_date", mark: { x_mm: 30, format: "day" } });
  });

  it("убранная метка", () => {
    expect(dateOpFrom("author", "report", before, { dates: [first] })).toEqual({
      op: "remove_date",
      slot: "author",
      doc: "report",
      index: 2,
    });
  });

  it("изменённый формат", () => {
    const changed = { ...second, format: "year_short" as const };
    expect(
      dateOpFrom("author", "report", before, {
        dates: [first, changed],
      }),
    ).toMatchObject({
      op: "set_date",
      index: 2,
      mark: { format: "year_short" },
    });
  });

  it("без изменений правки нет", () => {
    expect(dateOpFrom("author", "report", before, { dates: before })).toBe(
      null,
    );
  });
});

describe("строки даты сборки", () => {
  it("свободные строки этого слота", () => {
    expect(
      freeDateAnchors(slot("author"), DATA.build?.date_anchors ?? []),
    ).toEqual(["author.month_word", "author.day"]);
    expect(freeDateAnchors(withDates, ["author.month_word", "x.day"])).toEqual(
      [],
    );
  });
});
