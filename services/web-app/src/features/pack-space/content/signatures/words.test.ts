import { describe, expect, it } from "vitest";
import { SIGNATURES_BUILT, SIGNATURES_PLAIN, SIGNATURES_DOC } from "./fixtures";
import {
  documentPlacesOf,
  entryKind,
  entryPage,
  mm,
  placeStatusOf,
  slotsForDocument,
} from "./words";

const byId = (id: string) => {
  const found = SIGNATURES_BUILT.slots.find((slot) => slot.id === id);
  if (!found) throw new Error(id);
  return found;
};

describe("места подписей словами", () => {
  it("статус: своё место, общее, места в этом PDF нет, подпись документа не касается", () => {
    expect(placeStatusOf(byId("author"))).toBe("own");
    expect(placeStatusOf(byId("supervisor"))).toBe("shared");
    expect(placeStatusOf(byId("consultant"))).toBe("missing");
    expect(placeStatusOf(byId("customer"))).toBeNull();
  });

  it("подписи документа: те, что к нему относятся", () => {
    expect(
      slotsForDocument(SIGNATURES_PLAIN.slots, SIGNATURES_DOC).map(
        (slot) => slot.id,
      ),
    ).toEqual(["author", "supervisor", "consultant"]);
    expect(
      slotsForDocument(SIGNATURES_PLAIN.slots, "nda").map((slot) => slot.id),
    ).toEqual(["supervisor", "customer"]);
    expect(slotsForDocument(SIGNATURES_PLAIN.slots, "other")).toEqual([]);
  });

  it("запись места: на странице или по тексту; страница запасного места", () => {
    const author = byId("author");
    expect(entryKind(author.default_place)).toBe("page");
    expect(entryPage(author.default_place)).toBe(1);
    const own = author.places[SIGNATURES_DOC];
    if (!own) throw new Error("own");
    expect(entryKind(own)).toBe("text");
    expect(entryPage(own)).toBe(1);
    // Строка без запасного места: страницы нет.
    expect(entryPage(byId("consultant").default_place)).toBeNull();
  });

  it("сводка по документам: свои места и общие", () => {
    expect(documentPlacesOf(byId("author"))).toEqual([
      { docId: SIGNATURES_DOC, status: "own" },
    ]);
    expect(documentPlacesOf(byId("supervisor"))).toEqual([
      { docId: SIGNATURES_DOC, status: "shared" },
      { docId: "nda", status: "shared" },
    ]);
  });

  it("миллиметры без хвоста", () => {
    expect(mm(110)).toBe("110");
    expect(mm(12.46)).toBe("12.5");
  });
});
