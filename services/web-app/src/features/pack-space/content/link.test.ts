import { describe, expect, it } from "vitest";
import { buildSpaceUrl, type SpaceHere } from "../context/nav";
import { contentDocumentPatch, contentPartPatch } from "./link";

const REF = { pack: "p", template: "t", version: "1.0" };
const here = (search: string, tab: SpaceHere["tab"]): SpaceHere => ({
  workspaceId: "w1",
  ref: REF,
  tab,
  search,
});
const B = "/pack-studio/w/w1/t/p/t/1.0";

describe("ссылки на «Содержимое»", () => {
  it("«Текст документа» из «Результата»: документ, основной файл, условия остаются", () => {
    const url = buildSpaceUrl(
      here("sel=documents%3Ats&i.kind=research&changes=1", "result"),
      contentDocumentPatch("ts", { file: "ts/ts.tex" }),
    );
    expect(url).toBe(
      `${B}/content?i.kind=research&changes=1&doc=ts&file=ts%2Fts.tex`,
    );
  });

  it("сегмент по умолчанию («Текст») в адрес не пишется, другие пишутся", () => {
    expect(buildSpaceUrl(here("", "result"), contentDocumentPatch("ts"))).toBe(
      `${B}/content?doc=ts`,
    );
    expect(
      buildSpaceUrl(
        here("", "result"),
        contentDocumentPatch("ts", { segment: "signatures" }),
      ),
    ).toBe(`${B}/content?doc=ts&seg=signatures`);
  });

  it("внутри вкладки смена документа сбрасывает сегмент, файл и указатель", () => {
    const url = buildSpaceUrl(
      here("doc=a&seg=terms&file=a%2Fa.tex&at=%2Fforms", "content"),
      contentDocumentPatch("b"),
    );
    expect(url).toBe(`${B}/content?doc=b`);
  });

  it("раздел: сбрасывает документ и сегмент, переносит файл и указатель", () => {
    expect(
      buildSpaceUrl(
        here("doc=a&seg=terms", "content"),
        contentPartPatch("fields"),
      ),
    ).toBe(`${B}/content?part=fields`);
    expect(
      buildSpaceUrl(
        here("", "check"),
        contentPartPatch("forms", { at: "/forms/1" }),
      ),
    ).toBe(`${B}/content?part=forms&at=%2Fforms%2F1`);
    expect(
      buildSpaceUrl(
        here("", "result"),
        contentPartPatch("files", { file: "a/pack.yaml" }),
      ),
    ).toBe(`${B}/content?part=files&file=a%2Fpack.yaml`);
  });
});
