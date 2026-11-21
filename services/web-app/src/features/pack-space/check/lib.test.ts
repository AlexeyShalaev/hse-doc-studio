import { describe, expect, it } from "vitest";
import { filePathIn, pinParam, readCheck, witnessInputs } from "./lib";

describe("readCheck", () => {
  it("часть и сравнение из query, чужое значение даёт «Замечания»", () => {
    expect(readCheck("")).toEqual({ part: "issues", compare: false });
    expect(readCheck("?part=cases")).toEqual({ part: "cases", compare: false });
    expect(readCheck("?part=map&compare=1")).toEqual({
      part: "map",
      compare: true,
    });
    expect(readCheck("?part=other&compare=yes")).toEqual({
      part: "issues",
      compare: false,
    });
  });
});

describe("witnessInputs", () => {
  const known = [
    { id: "kind", default: "course" },
    { id: "staffing", default: "one" },
  ];

  it("значения ложатся поверх нынешних условий, лишнее остаётся", () => {
    expect(
      witnessInputs(known, { staffing: "two" }, null, { kind: "research" }),
    ).toEqual({ staffing: "two", kind: "research" });
  });

  it("условия, которых нет у версии, не пишутся", () => {
    expect(witnessInputs(known, {}, null, { unknown: "x", kind: "a" })).toEqual(
      {
        kind: "a",
      },
    );
  });

  it("значение по умолчанию без готового случая не пишется и снимает прежнее", () => {
    expect(
      witnessInputs(known, { kind: "research" }, null, { kind: "course" }),
    ).toEqual({});
  });

  it("поверх готового случая значение по умолчанию записывается", () => {
    expect(witnessInputs(known, {}, "company", { kind: "course" })).toEqual({
      kind: "course",
    });
  });

  it("пока условия версии не пришли, пишется всё как есть", () => {
    expect(witnessInputs(undefined, {}, null, { a: "1" })).toEqual({ a: "1" });
  });
});

describe("filePathIn", () => {
  it("путь от каталога версии; выход за каталог не открывается", () => {
    expect(filePathIn("p/templates/t/versions/1", "version.yaml")).toBe(
      "p/templates/t/versions/1/version.yaml",
    );
    expect(filePathIn("p/versions/1", "../x")).toBeNull();
    expect(filePathIn("p/versions/1", "/etc/passwd")).toBeNull();
    expect(filePathIn("", "version.yaml")).toBeNull();
    expect(filePathIn("p/versions/1", "")).toBeNull();
  });
});

describe("pinParam", () => {
  it("закрепление условия лежит в `p.<условие>`", () => {
    expect(pinParam("kind")).toBe("p.kind");
  });
});
