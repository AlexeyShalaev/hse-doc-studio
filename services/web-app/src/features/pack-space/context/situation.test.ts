import { describe, expect, it } from "vitest";
import {
  parseOutcomeSearch,
  writeOutcomeSearch,
} from "@features/pack-outcome/lib/urlState";
import { MAX_INPUTS, readSituation, writeInputs } from "./situation";

describe("условия студента в адресе", () => {
  it("читает i.* и case, лишнее и невалидное отбрасывает", () => {
    expect(
      readSituation(
        "i.kind=research&i.Bad=x&i.empty=&case=c1&sel=a%3Ab&i.nda=%00",
      ),
    ).toEqual({ inputs: { kind: "research" }, caseId: "c1" });
    expect(readSituation("case=%20bad").caseId).toBeNull();
  });

  it("не больше 64 условий и 128 знаков в значении", () => {
    const many = Array.from({ length: 80 }, (_, i) => `i.k${String(i)}=v`).join(
      "&",
    );
    expect(Object.keys(readSituation(many).inputs)).toHaveLength(MAX_INPUTS);
    expect(readSituation(`i.k=${"x".repeat(129)}`).inputs).toEqual({});
    expect(Object.keys(readSituation(`i.k=${"x".repeat(128)}`).inputs)).toEqual(
      ["k"],
    );
  });

  it("круг: запись и чтение дают те же условия", () => {
    const inputs = { staffing: "team2", kind: "research", "work.lang": "ru" };
    const params = new URLSearchParams("sel=a%3Ab");
    writeInputs(params, inputs);
    expect(params.get("sel")).toBe("a:b");
    expect(readSituation(params.toString()).inputs).toEqual(inputs);
    writeInputs(params, { kind: "vkr" });
    expect(readSituation(params.toString()).inputs).toEqual({ kind: "vkr" });
  });

  it("формат совпадает с прежним экраном «Результат»: ссылка с него читается в новом и обратно", () => {
    const old = writeOutcomeSearch(new URLSearchParams(), {
      inputs: { kind: "research", staffing: "solo" },
    });
    expect(readSituation(old.toString()).inputs).toEqual({
      kind: "research",
      staffing: "solo",
    });
    const params = new URLSearchParams();
    writeInputs(params, { kind: "research", staffing: "solo" });
    expect(parseOutcomeSearch(params).inputs).toEqual({
      kind: "research",
      staffing: "solo",
    });
  });
});
