import { describe, expect, it } from "vitest";
import {
  defaultColumnToken,
  parseColumnSpec,
  retargetAlign,
  serializeColumnSpec,
} from "./columnSpec";

const REQ_SPEC = String.raw`|l|>{\raggedright\arraybackslash}p{0.28\textwidth}|>{\raggedright\arraybackslash}p{0.28\textwidth}|>{\centering\arraybackslash}p{0.22\textwidth}|`;

describe("parseColumnSpec", () => {
  it("parses the requirements column spec with borders and alignment", () => {
    const parsed = parseColumnSpec(REQ_SPEC);
    expect(parsed.columns).toHaveLength(4);
    expect(parsed.columns[0]).toEqual({
      token: "l",
      align: "left",
      leftBorder: "|",
    });
    expect(parsed.columns[1]?.align).toBe("left");
    expect(parsed.columns[1]?.token).toBe(
      String.raw`>{\raggedright\arraybackslash}p{0.28\textwidth}`,
    );
    expect(parsed.columns[3]?.align).toBe("center");
    expect(parsed.rightBorder).toBe("|");
  });

  it("parses simple alignments", () => {
    const parsed = parseColumnSpec("lcr");
    expect(parsed.columns.map((c) => c.align)).toEqual([
      "left",
      "center",
      "right",
    ]);
    expect(parsed.columns.every((c) => c.leftBorder === "")).toBe(true);
  });

  it("expands *{n}{cols} repeats", () => {
    const parsed = parseColumnSpec("|*{3}{c}|");
    expect(parsed.columns).toHaveLength(3);
    expect(parsed.columns.every((c) => c.token === "c")).toBe(true);
    expect(parsed.columns[0]?.leftBorder).toBe("|");
    expect(parsed.rightBorder).toBe("|");
  });

  it("keeps @{…} inter-column material as border", () => {
    const parsed = parseColumnSpec(String.raw`l@{\hspace{1cm}}l`);
    expect(parsed.columns).toHaveLength(2);
    expect(parsed.columns[1]?.leftBorder).toBe(String.raw`@{\hspace{1cm}}`);
  });
});

describe("serializeColumnSpec", () => {
  it("round-trips every spec byte-for-byte", () => {
    for (const spec of [
      REQ_SPEC,
      "lcr",
      "|c|c|",
      String.raw`l@{\hspace{1cm}}l`,
      String.raw`>{\centering\arraybackslash}X|X`,
    ]) {
      expect(serializeColumnSpec(parseColumnSpec(spec))).toBe(spec);
    }
  });
});

describe("retargetAlign", () => {
  it("swaps the letter for simple columns", () => {
    expect(retargetAlign("l", "center")).toBe("c");
    expect(retargetAlign("c", "right")).toBe("r");
    expect(retargetAlign("r", "left")).toBe("l");
  });

  it("swaps the alignment prefix for paragraph columns", () => {
    expect(
      retargetAlign(
        String.raw`>{\raggedright\arraybackslash}p{0.28\textwidth}`,
        "center",
      ),
    ).toBe(String.raw`>{\centering\arraybackslash}p{0.28\textwidth}`);
    expect(retargetAlign("p{2cm}", "right")).toBe(
      String.raw`>{\raggedleft\arraybackslash}p{2cm}`,
    );
  });

  it("leaves the token untouched for the 'other' alignment", () => {
    expect(retargetAlign("X", "other")).toBe("X");
  });
});

describe("defaultColumnToken", () => {
  it("mirrors a sibling or falls back to l", () => {
    expect(defaultColumnToken(null)).toBe("l");
    expect(defaultColumnToken("p{3cm}")).toBe("p{3cm}");
  });
});
