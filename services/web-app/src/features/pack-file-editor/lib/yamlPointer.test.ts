import { describe, expect, it } from "vitest";
import { parsePointer, pointerLine } from "./yamlPointer";

const TEXT = `id: "1"
meta_fields:
  nda:
    supported_kinds: [project]
  "tricky/key":
    label: x
pack_submission:
  profiles:
    - id: a
      items:
        - doc: x
          when: y
    - id: b
      signing_slots:
        - slot: s1
          when:
            all: [a]
        - slot: s2
          optional: true
checks_version:
  disabled: false
`;

describe("указатель JSON в строку YAML", () => {
  it("разбирает сегменты и экранирование", () => {
    expect(parsePointer("")).toEqual([]);
    expect(parsePointer("/a/b~1c/d~0e")).toEqual(["a", "b/c", "d~e"]);
    expect(parsePointer("a/b")).toBeNull();
  });

  it("находит ключ, вложенный ключ и элемент последовательности", () => {
    expect(pointerLine(TEXT, "/meta_fields")).toBe(2);
    expect(pointerLine(TEXT, "/meta_fields/nda/supported_kinds")).toBe(4);
    expect(pointerLine(TEXT, "/pack_submission/profiles/0")).toBe(9);
    expect(pointerLine(TEXT, "/pack_submission/profiles/0/items/0/when")).toBe(
      12,
    );
    expect(
      pointerLine(TEXT, "/pack_submission/profiles/1/signing_slots/0/when"),
    ).toBe(16);
    expect(
      pointerLine(TEXT, "/pack_submission/profiles/1/signing_slots/1"),
    ).toBe(18);
    expect(pointerLine(TEXT, "/checks_version/disabled")).toBe(21);
  });

  it("понимает ключ в кавычках с косой чертой", () => {
    expect(pointerLine(TEXT, "/meta_fields/tricky~1key/label")).toBe(6);
  });

  it("ненайденный сегмент оставляет ближайшего найденного предка", () => {
    expect(pointerLine(TEXT, "/pack_submission/profiles/9/when")).toBe(8);
    expect(pointerLine(TEXT, "/nothing")).toBe(1);
  });

  it("пустой текст и чужой указатель не дают строки", () => {
    expect(pointerLine("", "/a")).toBeNull();
    expect(pointerLine(TEXT, "not-a-pointer")).toBeNull();
  });

  it("корневой указатель ведёт на начало документа", () => {
    expect(pointerLine(TEXT, "")).toBe(1);
  });
});
