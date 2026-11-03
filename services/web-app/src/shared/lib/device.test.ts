import { describe, expect, it } from "vitest";
import { describeAgent } from "./device";

describe("describeAgent", () => {
  it("браузер и система из типичных строк", () => {
    expect(
      describeAgent(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/156.0.0.0 Safari/537.36",
      ),
    ).toBe("Chrome · macOS");
    expect(
      describeAgent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
      ),
    ).toBe("Firefox · Windows");
    expect(
      describeAgent(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
      ),
    ).toBe("Safari · iOS");
    expect(
      describeAgent(
        "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120.0 Safari/537.36 Edg/120.0",
      ),
    ).toBe("Edge · Windows");
  });

  it("неизвестная строка даёт пустое описание", () => {
    expect(describeAgent("")).toBe("");
    expect(describeAgent("custom-client/1.0")).toBe("");
  });
});
