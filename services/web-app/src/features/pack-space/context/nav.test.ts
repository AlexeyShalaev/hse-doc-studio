import { describe, expect, it } from "vitest";
import { buildSpaceUrl, isMove, type SpaceHere } from "./nav";

const REF = { pack: "p", template: "t", version: "1.0" };
const here = (search = "", tab: SpaceHere["tab"] = "result"): SpaceHere => ({
  workspaceId: "w1",
  ref: REF,
  tab,
  search,
});
const B = "/pack-studio/w/w1/t/p/t/1.0";

describe("buildSpaceUrl", () => {
  it("без изменений даёт тот же адрес", () => {
    expect(buildSpaceUrl(here("sel=documents%3Ax&i.kind=research"))).toBe(
      `${B}/result?sel=documents%3Ax&i.kind=research`,
    );
  });

  it("на той же вкладке правит параметры, null убирает", () => {
    const url = buildSpaceUrl(here("sel=a%3Ab&doc=x"), {
      sel: "documents:y",
      doc: null,
    });
    expect(url).toBe(`${B}/result?sel=documents%3Ay`);
  });

  it("смена вкладки сбрасывает параметры вкладки, но оставляет условия, случай и панель", () => {
    const search = "i.kind=research&case=c1&changes=1&sel=a%3Ab&doc=x&at=%2Fp";
    expect(buildSpaceUrl(here(search), { tab: "check", part: "cases" })).toBe(
      `${B}/check?i.kind=research&case=c1&changes=1&part=cases`,
    );
  });

  it("смена версии тоже сбрасывает параметры вкладки", () => {
    const next = { ...REF, version: "2.0" };
    expect(buildSpaceUrl(here("sel=a%3Ab&i.kind=x"), { ref: next })).toBe(
      "/pack-studio/w/w1/t/p/t/2.0/result?i.kind=x",
    );
  });

  it("условия заменяются целиком, порядок по имени; невалидное отбрасывается", () => {
    const url = buildSpaceUrl(here("i.old=1&sel=a%3Ab"), {
      inputs: { staffing: "solo", kind: "research", "BAD KEY": "x", empty: "" },
    });
    expect(url).toBe(`${B}/result?sel=a%3Ab&i.kind=research&i.staffing=solo`);
  });

  it("случай и панель", () => {
    expect(
      buildSpaceUrl(here(), { case: "company-supervisor", changes: true }),
    ).toBe(`${B}/result?changes=1&case=company-supervisor`);
    expect(
      buildSpaceUrl(here("case=c&changes=1"), { case: null, changes: false }),
    ).toBe(`${B}/result`);
    expect(buildSpaceUrl(here(), { case: "bad id!" })).toBe(`${B}/result`);
  });

  it("extra: параметры области без своего поля", () => {
    expect(
      buildSpaceUrl(here("compare=1", "check"), {
        extra: { compare: null, at: "/a/0" },
      }),
    ).toBe(`${B}/check?at=%2Fa%2F0`);
  });

  it("isMove: вкладка или версия другие, а то же самое не переход", () => {
    expect(isMove(here(), { tab: "result" })).toBe(false);
    expect(isMove(here(), { ref: { ...REF } })).toBe(false);
    expect(isMove(here(), { tab: "content" })).toBe(true);
    expect(isMove(here(), { ref: { ...REF, version: "2.0" } })).toBe(true);
    expect(isMove(here(), { sel: "a:b" })).toBe(false);
  });
});
