import { describe, expect, it } from "vitest";
import {
  packFilesPath,
  packNewVersionPath,
  packOutcomePath,
  packRulePath,
  packWorkspacePath,
} from "./routes";
import { isSpaceTab, legacyToSpace, spacePath } from "./spaceRoutes";

const WS = "w1";
const VKR = "hse-cs-se/templates/vkr/versions/2026.1.2";
const FILE = `${VKR}/version.yaml`;
// Куда подставит вход, когда в старом адресе версии нет (последнее место или умолчание).
const FALLBACK = { pack: "hse", template: "tpl", version: "9.9.9" };

/** Как вход строит итоговый адрес: версия из адреса или подставленная, вкладка так же. */
const toNew = (url: string, ws = WS): string | null => {
  const [path = "", query = ""] = url.split("?");
  const target = legacyToSpace(ws, path, query);
  if (!target) return null;
  return spacePath(
    ws,
    target.ref ?? FALLBACK,
    target.tab ?? "result",
    target.search,
  );
};

const BASE = "/pack-studio/w/w1";
const RESULT = `${BASE}/result/hse-cs-se/vkr/2026.1.2`;
const NEW = `${BASE}/t/hse-cs-se/vkr/2026.1.2`;
const FB = `${BASE}/t/hse/tpl/9.9.9`;

describe("перенаправления: старый адрес, новый адрес", () => {
  const table: [string, string][] = [
    [RESULT, `${NEW}/result`],
    [
      `${RESULT}?selected=documents%3Athesis`,
      `${NEW}/result?sel=documents%3Athesis`,
    ],
    [
      `${RESULT}?i.kind=research&i.nda=yes`,
      `${NEW}/result?i.kind=research&i.nda=yes`,
    ],
    [
      `${RESULT}?scenario=company-supervisor`,
      `${NEW}/result?case=company-supervisor`,
    ],
    [`${RESULT}?state=head&mode=student&tab=rules`, `${NEW}/result`],
    [
      `${RESULT}?view=matrix&against=base`,
      `${NEW}/check?against=base&part=cases`,
    ],
    [
      `${RESULT}?view=atlas&p.kind=research`,
      `${NEW}/check?p.kind=research&part=map`,
    ],
    [
      `${RESULT}?view=compare&left=base&right=tree`,
      `${NEW}/check?left=base&right=tree&compare=1`,
    ],
    [`${RESULT}?view=lint`, `${NEW}/check?part=issues`],
    [
      `${RESULT}?view=result&example=auto%3Anormal`,
      `${NEW}/result?example=auto%3Anormal`,
    ],
    [`${BASE}/result`, `${FB}/result`],
    [`${BASE}/result?i.kind=research`, `${FB}/result?i.kind=research`],
    [`${BASE}/result?view=matrix`, `${FB}/check?part=cases`],
    [
      `${BASE}?file=${encodeURIComponent(FILE)}`,
      `${NEW}/content?file=${encodeURIComponent(FILE)}`,
    ],
    [
      `${BASE}?file=${encodeURIComponent(FILE)}&at=%2Fa%2F0&pane=form&from=%2Fback`,
      `${NEW}/content?file=${encodeURIComponent(FILE)}&at=%2Fa%2F0&pane=form&from=%2Fback`,
    ],
    [`${BASE}?view=files`, `${FB}/content?part=files`],
    [
      `${BASE}?file=hse-cs-se%2Fpack.yaml`,
      `${FB}/content?file=hse-cs-se%2Fpack.yaml`,
    ],
    [
      "/pack-studio/w/a%20b/result/p/t/2026.1.2",
      "/pack-studio/w/a%20b/t/p/t/2026.1.2/result",
    ],
    // Флаг `ux` из 0.38.0 ничего не значит: отбрасывается.
    [`${RESULT}?ux=1&view=atlas`, `${NEW}/check?part=map`],
    [`${BASE}?ux=2&view=files`, `${FB}/content?part=files`],
  ];
  it.each(table)("%s -> %s", (from, to) => {
    expect(toNew(from, from.includes("a%20b") ? "a b" : WS)).toBe(to);
  });

  // Ссылки прежнего вида строили эти функции (письма, закладки, «Назад к результату»): каждая
  // доходит до своего экрана.
  it("адреса функций прежнего вида ведут на свой экран", () => {
    const ref = { pack: "hse-cs-se", template: "vkr", version: "2026.1.2" };
    const enc = encodeURIComponent(FILE);
    expect(toNew(packWorkspacePath(WS))).toBe(`${FB}/result`);
    expect(toNew(packWorkspacePath(WS, FILE))).toBe(
      `${NEW}/content?file=${enc}`,
    );
    expect(toNew(packFilesPath(WS))).toBe(`${FB}/content?part=files`);
    expect(toNew(packOutcomePath(WS, ref, "selected=documents%3Ats"))).toBe(
      `${NEW}/result?sel=documents%3Ats`,
    );
    expect(toNew(packOutcomePath(WS, null))).toBe(`${FB}/result`);
    expect(
      toNew(
        packRulePath(WS, FILE, {
          pointer: "/supported_kinds",
          pane: "form",
          from: packOutcomePath(WS, ref),
        }),
      ),
    ).toBe(
      `${NEW}/content?file=${enc}&at=%2Fsupported_kinds&pane=form&from=${encodeURIComponent(packOutcomePath(WS, ref))}`,
    );
    const copy = legacyToSpace(
      WS,
      ...(packNewVersionPath(WS, ref).split("?") as [string, string]),
    );
    expect(copy).toMatchObject({
      ref: null,
      template: { pack: "hse-cs-se", template: "vkr" },
      tab: "result",
      search: "copy=1",
    });
  });

  it("корень пространства без параметров: вход выбирает версию и вкладку сам", () => {
    expect(legacyToSpace(WS, BASE, "")).toEqual({
      ref: null,
      template: null,
      tab: null,
      search: "",
    });
  });

  it("?newVersion=пак/шаблон ведёт на «Результат» шаблона и оставляет подсказку copy=1", () => {
    expect(
      legacyToSpace(WS, BASE, "view=files&newVersion=hse-cs-se%2Fvkr"),
    ).toEqual({
      ref: null,
      template: { pack: "hse-cs-se", template: "vkr" },
      tab: "result",
      search: "copy=1",
    });
  });

  it("файл в папке версии даёт версию из пути", () => {
    expect(
      legacyToSpace(WS, BASE, `file=${encodeURIComponent(FILE)}`)?.ref,
    ).toEqual({
      pack: "hse-cs-se",
      template: "vkr",
      version: "2026.1.2",
    });
  });

  it("не старый адрес: новый, чужое пространство, лишние сегменты, битое кодирование", () => {
    expect(legacyToSpace(WS, `${NEW}/result`, "")).toBeNull();
    expect(legacyToSpace(WS, "/pack-studio/w/w2/result", "")).toBeNull();
    expect(legacyToSpace(WS, `${BASE}/result/a/b`, "")).toBeNull();
    expect(legacyToSpace(WS, `${BASE}/files`, "")).toBeNull();
    expect(legacyToSpace(WS, `${BASE}/result/%E0%A4%A/b/c`, "")).toBeNull();
  });
});

describe("spacePath", () => {
  const ref = { pack: "p q", template: "t", version: "1.0" };
  it("кодирует сегменты и принимает query со знаком вопроса и без", () => {
    expect(spacePath("w 1", ref, "content", "doc=a")).toBe(
      "/pack-studio/w/w%201/t/p%20q/t/1.0/content?doc=a",
    );
    expect(spacePath("w", ref, "check", "?part=cases")).toBe(
      "/pack-studio/w/w/t/p%20q/t/1.0/check?part=cases",
    );
    expect(spacePath("w", ref, "result")).toBe(
      "/pack-studio/w/w/t/p%20q/t/1.0/result",
    );
  });
  it("isSpaceTab знает ровно три вкладки", () => {
    expect(["result", "content", "check"].every(isSpaceTab)).toBe(true);
    expect(isSpaceTab("files")).toBe(false);
    expect(isSpaceTab(undefined)).toBe(false);
  });
});
