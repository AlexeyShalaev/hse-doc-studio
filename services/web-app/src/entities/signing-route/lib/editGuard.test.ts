import { describe, expect, it } from "vitest";
import { makeSigningRouteSummary } from "../testing/fixtures";
import {
  affectedHeld,
  createGuardMemory,
  docOfPath,
  folderOf,
  guardKey,
  heldDocsOf,
  isOwnTarget,
  type GuardDoc,
} from "./editGuard";

const DOCS: GuardDoc[] = [
  { id: "topic", name: "Заявление о выборе темы", folder: "topic" },
  { id: "review", name: "Отзыв руководителя", folder: "review" },
  { id: "vkr--ivanov", name: "ВКР", folder: "ivanov/vkr" },
  { id: "root", name: "Корневой", folder: "" },
];

describe("heldDocsOf", () => {
  it("takes the documents of active routes with their round", () => {
    const held = heldDocsOf([
      makeSigningRouteSummary({
        id: "r1",
        round: 2,
        docs: ["topic", "review"],
      }),
    ]);
    expect(held).toEqual([
      { docId: "topic", routeId: "r1", round: 2 },
      { docId: "review", routeId: "r1", round: 2 },
    ]);
  });

  it("does not hold documents of paused, returned, completed or draft routes", () => {
    const statuses = [
      "draft",
      "paused",
      "returned",
      "completed",
      "cancelled",
    ] as const;
    const routes = statuses.map((status) =>
      makeSigningRouteSummary({ id: status, status, docs: ["topic"] }),
    );
    expect(heldDocsOf(routes)).toEqual([]);
  });

  it("holds nothing while the server does not send docs yet (before R16)", () => {
    const route = makeSigningRouteSummary();
    delete (route as { docs?: string[] }).docs;
    expect(heldDocsOf([route])).toEqual([]);
  });
});

describe("guardKey", () => {
  it("is per project, document, route and round", () => {
    expect(guardKey("p1", { docId: "topic", routeId: "r1", round: 3 })).toBe(
      "hds.route-guard.p1.topic.r1.3",
    );
  });
});

describe("paths", () => {
  it("folderOf takes the folder of the main source", () => {
    expect(folderOf("topic/topic.tex")).toBe("topic");
    expect(folderOf("ivanov/vkr/vkr.tex")).toBe("ivanov/vkr");
    expect(folderOf("./slides\\pres.tex")).toBe("slides");
    expect(folderOf("main.tex")).toBe("");
  });

  it("docOfPath finds the document folder, shared files have none", () => {
    expect(docOfPath("topic/sections/intro.tex", DOCS)).toBe("topic");
    expect(docOfPath("topic", DOCS)).toBe("topic");
    expect(docOfPath("ivanov/vkr/img/a.png", DOCS)).toBe("vkr--ivanov");
    expect(docOfPath("topical/x.tex", DOCS)).toBeNull();
    expect(docOfPath("common/meta.tex", DOCS)).toBeNull();
    expect(docOfPath("refs.bib", DOCS)).toBeNull();
  });
});

describe("affectedHeld and isOwnTarget", () => {
  const held = [
    { docId: "topic", routeId: "r1", round: 1 },
    { docId: "review", routeId: "r1", round: 1 },
  ];

  it("a file of a document touches only that document", () => {
    expect(affectedHeld({ paths: ["topic/a.tex"] }, held, DOCS)).toEqual([
      held[0],
    ]);
    expect(isOwnTarget({ paths: ["topic/a.tex"] }, DOCS)).toBe(true);
  });

  it("a file of a document not on signing touches nothing", () => {
    expect(affectedHeld({ paths: ["ivanov/vkr/vkr.tex"] }, held, DOCS)).toEqual(
      [],
    );
  });

  it("shared files and project fields touch every held document", () => {
    expect(affectedHeld({ paths: ["common/refs.bib"] }, held, DOCS)).toEqual(
      held,
    );
    expect(affectedHeld({ project: true }, held, DOCS)).toEqual(held);
    expect(isOwnTarget({ paths: ["common/refs.bib"] }, DOCS)).toBe(false);
    expect(isOwnTarget({ project: true }, DOCS)).toBe(false);
  });

  it("a batch of documents lists them", () => {
    expect(
      affectedHeld({ docIds: ["topic", "review", "root"] }, held, DOCS),
    ).toEqual(held);
    expect(isOwnTarget({ docIds: ["topic", "review"] }, DOCS)).toBe(false);
    expect(isOwnTarget({ docIds: ["topic"] }, DOCS)).toBe(true);
  });
});

describe("createGuardMemory", () => {
  it("keeps the answer in sessionStorage for the whole session", () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
    } as Storage;
    createGuardMemory(() => storage).add("k");
    // Другая вкладка той же сессии (или перезагрузка) читает тот же ответ.
    expect(createGuardMemory(() => storage).has("k")).toBe(true);
    expect(createGuardMemory(() => storage).has("other")).toBe(false);
  });

  it("remembers until reload when the storage throws", () => {
    const broken = {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
    } as unknown as Storage;
    const memory = createGuardMemory(() => broken);
    expect(memory.has("k")).toBe(false);
    memory.add("k");
    expect(memory.has("k")).toBe(true);
    expect(createGuardMemory(() => broken).has("k")).toBe(false);
  });

  it("works without any storage", () => {
    const memory = createGuardMemory(() => null);
    memory.add("k");
    expect(memory.has("k")).toBe(true);
  });
});
