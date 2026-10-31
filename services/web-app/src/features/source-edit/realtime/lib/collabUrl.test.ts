import { describe, expect, it } from "vitest";
import { collabUrl } from "./collabUrl";

describe("collabUrl", () => {
  it("uses the page origin and ws scheme when the API base is relative", () => {
    expect(
      collabUrl("", "p1", "chapters/a b.tex", {
        protocol: "http:",
        host: "localhost:17251",
      }),
    ).toBe(
      "ws://localhost:17251/api/collab/v1/projects/p1/room?path=chapters%2Fa+b.tex",
    );
  });

  it("switches to wss for an https API base", () => {
    expect(collabUrl("https://studio.example.org/", "p1", "m.tex")).toBe(
      "wss://studio.example.org/api/collab/v1/projects/p1/room?path=m.tex",
    );
  });
});
