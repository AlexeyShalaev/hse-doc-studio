import { describe, expect, it } from "vitest";
import { defineSpaceSlots, mergeSpaceSlots } from "./spaceSlots";

const A = () => <div>a</div>;
const B = () => <div>b</div>;

describe("mergeSpaceSlots", () => {
  it("областям по очереди: каждая кладёт свои слоты, чужие не трогает", () => {
    const merged = mergeSpaceSlots([
      ["../nav/slots.tsx", defineSpaceSlots({ header: A, contextBar: B })],
      [
        "../changes/slots.tsx",
        defineSpaceSlots({ changesButton: A, changes: B }),
      ],
      ["../result/slots.tsx", defineSpaceSlots({ main: { result: A } })],
      [
        "../content/slots.tsx",
        defineSpaceSlots({ main: { content: B }, nav: { content: A } }),
      ],
    ]);
    expect(merged.header).toBe(A);
    expect(merged.changes).toBe(B);
    expect(merged.main).toEqual({ result: A, content: B });
    expect(merged.nav).toEqual({ content: A });
  });

  it("слот на других вкладках тот же слот: две области на одной вкладке не уживаются", () => {
    expect(() =>
      mergeSpaceSlots([
        ["../result/slots.tsx", { main: { result: A } }],
        ["../situation/slots.tsx", { main: { result: B } }],
      ]),
    ).toThrow(/main\.result.*result\/slots\.tsx.*situation\/slots\.tsx/);
  });

  it("одиночный слот тоже занимает одна область", () => {
    expect(() =>
      mergeSpaceSlots([
        ["../nav/slots.tsx", { header: A }],
        ["../shell2/slots.tsx", { header: B }],
      ]),
    ).toThrow(/«header» занят/);
  });

  it("пусто: пустые слоты", () => {
    expect(mergeSpaceSlots([])).toEqual({});
  });
});
