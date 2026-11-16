import { describe, expect, it } from "vitest";
import {
  COURSEWORK_OUTCOME,
  VKR_CHECKS,
  VKR_OUTCOME,
  elementInfos,
} from "@entities/pack-studio/reference";
import { describeElement } from "./elements";

const vkr = { ...VKR_OUTCOME, checks: VKR_CHECKS };

describe("описание элемента по результату", () => {
  it("документ, поле, анкета и участник называются по ответу", () => {
    const doc = vkr.documents[0];
    expect(
      describeElement(vkr, { section: "documents", id: doc?.id ?? "" }, "ru"),
    ).toMatchObject({
      kind: "document",
      title: doc?.name.ru,
    });
    expect(
      describeElement(vkr, { section: "meta", id: "year" }, "ru").kind,
    ).toBe("meta");
    const form = vkr.forms[0];
    const field = form?.fields[0];
    expect(
      describeElement(vkr, { section: "forms", id: form?.id ?? "" }, "ru").kind,
    ).toBe("form");
    const fieldInfo = describeElement(
      vkr,
      { section: "forms", id: `${form?.id ?? ""}/${field?.id ?? ""}` },
      "ru",
    );
    expect(fieldInfo.kind).toBe("form_field");
    expect(fieldInfo.title).toContain(": ");
    expect(
      describeElement(vkr, { section: "participants", id: "supervisor" }, "ru")
        .kind,
    ).toBe("participant");
  });

  it("точка, пункт, дополнительный файл с косой чертой в источнике", () => {
    const point = vkr.points.find((p) => p.extra_items.length > 0);
    expect(point).toBeDefined();
    const extra = point?.extra_items[0];
    expect(
      describeElement(vkr, { section: "points", id: point?.id ?? "" }, "ru")
        .kind,
    ).toBe("point");
    expect(
      describeElement(
        vkr,
        {
          section: "points",
          id: `${point?.id ?? ""}/${point?.items[0]?.doc_id ?? ""}`,
        },
        "ru",
      ),
    ).toMatchObject({ kind: "point_item" });
    expect(
      describeElement(
        vkr,
        { section: "points", id: `${point?.id ?? ""}/${extra?.source ?? ""}` },
        "ru",
      ),
    ).toMatchObject({ kind: "point_extra", title: extra?.output_name });
  });

  it("маршрут: точка, шаг с номером, пара", () => {
    const point = vkr.points.find((p) => p.route.pairs.length > 0);
    const pair = point?.route.pairs[0];
    expect(
      describeElement(vkr, { section: "route", id: point?.id ?? "" }, "ru")
        .kind,
    ).toBe("route");
    expect(
      describeElement(
        vkr,
        { section: "route", id: `${point?.id ?? ""}/step/2` },
        "ru",
      ),
    ).toMatchObject({ kind: "route_step", step: 2 });
    expect(
      describeElement(
        vkr,
        {
          section: "route",
          id: `${point?.id ?? ""}/${pair?.doc_id ?? ""}/${pair?.slot_id ?? ""}`,
        },
        "ru",
      ).kind,
    ).toBe("route_pair");
  });

  it("пропущенная пара отличается от пары маршрута", () => {
    const point = COURSEWORK_OUTCOME.points.find(
      (p) => p.route.skipped.length > 0,
    );
    if (!point) return;
    const skipped = point.route.skipped[0];
    expect(
      describeElement(
        COURSEWORK_OUTCOME,
        {
          section: "route",
          id: `${point.id}/${skipped?.doc_id ?? ""}/${skipped?.slot_id ?? ""}`,
        },
        "ru",
      ).kind,
    ).toBe("route_skipped");
  });

  it("правило проверки по названию; без части checks остаётся id", () => {
    const id = VKR_CHECKS[0]?.id ?? "";
    expect(describeElement(vkr, { section: "checks", id }, "ru").kind).toBe(
      "check",
    );
    expect(
      describeElement(VKR_OUTCOME, { section: "checks", id }, "ru"),
    ).toMatchObject({
      kind: "unknown",
      title: id,
    });
  });

  it("неизвестный элемент и отсутствие результата не падают", () => {
    expect(
      describeElement(vkr, { section: "documents", id: "nope" }, "ru"),
    ).toMatchObject({
      kind: "unknown",
      title: "nope",
    });
    expect(
      describeElement(undefined, { section: "route", id: "a/step/1" }, "ru")
        .title,
    ).toBe("a/step/1");
  });

  it("описание согласовано с идентификаторами сервера: все элементы эталона опознаются", () => {
    for (const outcome of [vkr, COURSEWORK_OUTCOME]) {
      for (const key of elementInfos(outcome).keys()) {
        const [section, ...rest] = key.split(":");
        const info = describeElement(
          outcome,
          { section: section as "documents", id: rest.join(":") },
          "ru",
        );
        expect(info.kind, key).not.toBe("unknown");
      }
    }
  });
});
