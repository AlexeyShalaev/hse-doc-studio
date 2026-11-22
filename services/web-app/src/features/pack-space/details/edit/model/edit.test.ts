import { describe, expect, it } from "vitest";
import {
  COURSEWORK_OUTCOME,
  VKR_OUTCOME,
} from "@entities/pack-studio/reference";
import { diffOutcomes, tallyDelta } from "./delta";
import {
  HISTORY_DEPTH,
  emptyHistory,
  markRedone,
  markUndone,
  pushEdit,
  redoTarget,
  undoTarget,
} from "./history";
import { dataOf, placeOf } from "./place";
import { guardHolds, planChange, planDelete, type RuleEdit } from "./plan";
import { decodePointer, resolvePointer, sameData } from "./pointer";
import { isEditableShape, isUnder, recordOf, shapeOf } from "./shape";

const manifest = {
  langs: ["ru", "en"],
  pack_submission: {
    profiles: [
      {
        id: "topic-approval",
        items: [{ doc_id: "report", skip_if_nda: true }],
        signing_slots: [
          { doc_id: "topic_application", slot_id: "co_supervisor" },
          {
            doc_id: "topic_application",
            slot_id: "academic_supervisor",
            when: { person: "supervisor", role: "company" },
          },
        ],
      },
    ],
  },
};
const WHEN = "/pack_submission/profiles/0/signing_slots/1/when";
const label = { subject: "slot_when", place: "x" };

describe("указатель", () => {
  it("разбирает экранирование и читает запись с индексами списков", () => {
    expect(decodePointer("/a~1b/c~0d")).toEqual(["a/b", "c~d"]);
    const found = resolvePointer(manifest, WHEN);
    expect(found?.path).toEqual([
      "pack_submission",
      "profiles",
      0,
      "signing_slots",
      1,
      "when",
    ]);
    expect(found?.exists).toBe(true);
    expect(found?.value).toEqual({ person: "supervisor", role: "company" });
  });

  it("отсутствующий ключ существующего родителя это запись без значения", () => {
    const found = resolvePointer(
      manifest,
      "/pack_submission/profiles/0/signing_slots/0/when",
    );
    expect(found?.exists).toBe(false);
  });

  it("нет родителя: запись не читается", () => {
    expect(resolvePointer(manifest, "/nope/x/y")).toBeNull();
    expect(resolvePointer(manifest, "/langs/9/x")).toBeNull();
  });

  it("сравнение данных не зависит от порядка ключей", () => {
    expect(sameData({ a: 1, b: [1, 2] }, { b: [1, 2], a: 1 })).toBe(true);
    expect(sameData({ a: 1 }, { a: 2 })).toBe(false);
    expect(sameData([1], [1, 2])).toBe(false);
  });
});

describe("вид записи", () => {
  it("узнаёт правки, которые экран ведёт по месту", () => {
    expect(shapeOf("/supported_kinds")).toEqual({
      kind: "list",
      list: "kinds",
    });
    expect(shapeOf("/supported_staffing")).toEqual({
      kind: "list",
      list: "staffing",
    });
    expect(shapeOf("/variants/0/supported_langs")).toEqual({
      kind: "list",
      list: "langs",
    });
    expect(shapeOf("/pack_submission/profiles/0/items/1/skip_if_nda")).toEqual({
      kind: "flag",
      flag: "skip_if_nda",
    });
    expect(shapeOf("/forms/0/sections/0/fields/1/visible_if")).toEqual({
      kind: "visibleIf",
    });
    expect(shapeOf(WHEN)).toEqual({ kind: "when" });
    expect(shapeOf("/checks_version/disabled")).toEqual({
      kind: "checks",
      list: "disabled",
    });
  });

  it("порядок подписания целиком не правится по месту", () => {
    const route = shapeOf("/pack_submission/profiles/0/signing_route");
    expect(route).toEqual({ kind: "route" });
    expect(isEditableShape(route)).toBe(false);
    expect(isEditableShape(shapeOf("/signatures/route"))).toBe(false);
    expect(isEditableShape(null)).toBe(false);
  });

  it("незнакомое остаётся только «Открыть правило»", () => {
    expect(shapeOf("/meta_fields/x/required_at")).toBeNull();
    expect(shapeOf("/pack_submission/profiles/0/when")).toBeNull();
  });

  it("запись правила целиком: слот, пункт, файл точки", () => {
    expect(recordOf(WHEN)).toEqual({
      kind: "slot",
      pointer: "/pack_submission/profiles/0/signing_slots/1",
      list: "/pack_submission/profiles/0/signing_slots",
      index: 1,
    });
    expect(
      recordOf("/pack_submission/profiles/2/items/0/skip_if_nda")?.kind,
    ).toBe("item");
    expect(
      recordOf("/pack_submission/profiles/2/extra_items/3/supported_kinds")
        ?.kind,
    ).toBe("extra");
    expect(recordOf("/supported_kinds")).toBeNull();
    expect(isUnder(WHEN, "/pack_submission/profiles/0/signing_slots/1")).toBe(
      true,
    );
    expect(isUnder("/a/b1", "/a/b")).toBe(false);
  });
});

describe("правка и обратная правка", () => {
  it("значение: обратная это исходное значение записи", () => {
    const planned = planChange(
      "version.yaml",
      WHEN,
      manifest,
      { type: "set", value: { person: "supervisor", role: "university" } },
      label,
    );
    expect(planned.ok).toBe(true);
    if (!planned.ok) return;
    expect(planned.edit.forward).toEqual([
      {
        op: "set",
        path: ["pack_submission", "profiles", 0, "signing_slots", 1, "when"],
        value: { person: "supervisor", role: "university" },
      },
    ]);
    expect(planned.edit.inverse).toEqual([
      {
        op: "set",
        path: ["pack_submission", "profiles", 0, "signing_slots", 1, "when"],
        value: { person: "supervisor", role: "company" },
      },
    ]);
  });

  it("новый ключ откатывается удалением", () => {
    const pointer = "/pack_submission/profiles/0/items/0/optional";
    const planned = planChange(
      "version.yaml",
      pointer,
      manifest,
      { type: "set", value: true },
      label,
    );
    expect(planned.ok && planned.edit.inverse[0]?.op).toBe("delete");
  });

  it("убрать ключ: обратная возвращает значение", () => {
    const planned = planChange(
      "version.yaml",
      WHEN,
      manifest,
      { type: "remove" },
      label,
    );
    expect(planned.ok && planned.edit.forward[0]?.op).toBe("delete");
    expect(planned.ok && planned.edit.inverse[0]).toMatchObject({
      op: "set",
      value: { person: "supervisor", role: "company" },
    });
  });

  it("то же значение и отсутствующий ключ это «без изменений»", () => {
    expect(
      planChange(
        "version.yaml",
        WHEN,
        manifest,
        { type: "set", value: { role: "company", person: "supervisor" } },
        label,
      ),
    ).toEqual({ ok: false, reason: "unchanged" });
    expect(
      planChange(
        "version.yaml",
        "/pack_submission/profiles/0/signing_slots/0/when",
        manifest,
        { type: "remove" },
        label,
      ),
    ).toEqual({ ok: false, reason: "unchanged" });
  });

  it("записи нет в манифесте: правка не строится", () => {
    expect(
      planChange(
        "version.yaml",
        "/nope/x/when",
        manifest,
        { type: "remove" },
        label,
      ),
    ).toEqual({ ok: false, reason: "missing" });
  });

  it("удаление слота: вставка обратно по тому же индексу целиком", () => {
    const record = recordOf(WHEN);
    expect(record).not.toBeNull();
    if (!record) return;
    const planned = planDelete("version.yaml", record, manifest, label);
    expect(planned.ok).toBe(true);
    if (!planned.ok) return;
    expect(planned.edit.forward).toEqual([
      {
        op: "delete",
        path: ["pack_submission", "profiles", 0, "signing_slots", 1],
      },
    ]);
    expect(planned.edit.inverse).toEqual([
      {
        op: "insert",
        path: ["pack_submission", "profiles", 0, "signing_slots"],
        index: 1,
        value: {
          doc_id: "topic_application",
          slot_id: "academic_supervisor",
          when: { person: "supervisor", role: "company" },
        },
      },
    ]);
  });

  it("охрана: откат ждёт состояния после правки, повтор состояния до неё", () => {
    const planned = planChange(
      "version.yaml",
      WHEN,
      manifest,
      { type: "remove" },
      label,
    );
    if (!planned.ok) throw new Error("planned");
    const after = structuredClone<typeof manifest>(manifest);
    delete (
      after.pack_submission.profiles[0]?.signing_slots[1] as Record<
        string,
        unknown
      >
    ).when;
    expect(guardHolds(after, planned.edit.after)).toBe(true);
    expect(guardHolds(manifest, planned.edit.after)).toBe(false);
    expect(guardHolds(manifest, planned.edit.before)).toBe(true);
    // Длина списка для удалённого слота.
    const record = recordOf(WHEN);
    if (!record) throw new Error("record");
    const deleted = planDelete("version.yaml", record, manifest, label);
    if (!deleted.ok) throw new Error("deleted");
    const shorter = structuredClone<typeof manifest>(manifest);
    shorter.pack_submission.profiles[0]?.signing_slots.pop();
    expect(guardHolds(shorter, deleted.edit.after)).toBe(true);
    expect(guardHolds(manifest, deleted.edit.after)).toBe(false);
  });

  it("данные и место: документ, слот, пункт", () => {
    expect(placeOf("files/report/doc.yaml", "/supported_kinds", {})).toBe(
      "report",
    );
    expect(placeOf("version.yaml", WHEN, manifest)).toBe(
      "topic_application / academic_supervisor",
    );
    expect(
      placeOf(
        "version.yaml",
        "/pack_submission/profiles/0/items/0/skip_if_nda",
        manifest,
      ),
    ).toBe("report");
    expect(dataOf(undefined, "version.yaml")).toBeUndefined();
  });
});

const edit = (n: number): RuleEdit => ({
  id: `e${String(n)}`,
  file: "version.yaml",
  pointer: "/x",
  action: "set",
  subject: "slot_when",
  place: "",
  forward: [],
  inverse: [],
  before: { kind: "record", pointer: "/x", exists: false, value: undefined },
  after: { kind: "record", pointer: "/x", exists: true, value: n },
  at: n,
});

describe("стек правок", () => {
  it("отмена двигает курсор, повтор возвращает, новая правка обрезает повтор", () => {
    let h = pushEdit(pushEdit(emptyHistory, edit(1)), edit(2));
    expect(undoTarget(h)?.id).toBe("e2");
    expect(redoTarget(h)).toBeNull();
    h = markUndone(h);
    expect(undoTarget(h)?.id).toBe("e1");
    expect(redoTarget(h)?.id).toBe("e2");
    h = markRedone(h);
    expect(redoTarget(h)).toBeNull();
    h = markUndone(markUndone(h));
    expect(undoTarget(h)).toBeNull();
    h = pushEdit(h, edit(3));
    expect(h.entries.map((e) => e.id)).toEqual(["e3"]);
  });

  it("глубина ограничена: старые правки забываются", () => {
    let h = emptyHistory;
    for (let i = 0; i < HISTORY_DEPTH + 5; i += 1) h = pushEdit(h, edit(i));
    expect(h.entries).toHaveLength(HISTORY_DEPTH);
    expect(h.cursor).toBe(HISTORY_DEPTH);
    expect(h.entries[0]?.id).toBe("e5");
  });
});

describe("что поменялось в результате", () => {
  it("одинаковый отпечаток это пустой список", () => {
    expect(diffOutcomes(VKR_OUTCOME, VKR_OUTCOME, "ru")).toEqual([]);
  });

  it("документ вышел из комплекта: минус; вернулся: плюс", () => {
    const after = structuredClone(VKR_OUTCOME);
    const doc = after.documents.find((d) => d.state === "active");
    if (!doc) throw new Error("no active document");
    doc.state = "inactive";
    after.fingerprint = "other";
    const down = diffOutcomes(VKR_OUTCOME, after, "ru");
    expect(down).toHaveLength(1);
    expect(down[0]).toMatchObject({
      symbol: "-",
      section: "documents",
      id: doc.id,
    });
    const up = diffOutcomes(after, VKR_OUTCOME, "ru");
    expect(up[0]).toMatchObject({ symbol: "+", id: doc.id });
    expect(tallyDelta([...down, ...up])).toEqual({
      added: 1,
      changed: 0,
      removed: 1,
    });
  });

  it("пара перешла из маршрута в пропущенные: минус пары; шаг изменился: тильда", () => {
    const after = structuredClone(COURSEWORK_OUTCOME);
    const point = after.points[0];
    if (!point) throw new Error("no point");
    const pair = point.route.pairs.find(
      (p) => p.slot_id === "academic_supervisor",
    );
    if (!pair) throw new Error("no pair");
    point.route.pairs = point.route.pairs.filter((p) => p !== pair);
    point.route.steps = [
      point.route.steps[0] ?? [],
      point.route.steps[1] ?? [],
    ];
    after.fingerprint = "other";
    const changes = diffOutcomes(COURSEWORK_OUTCOME, after, "ru");
    expect(changes.some((c) => c.symbol === "-" && c.section === "route")).toBe(
      true,
    );
  });
});
