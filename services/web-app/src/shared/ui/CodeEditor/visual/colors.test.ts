import { describe, expect, it } from "vitest";
import { colorToCss } from "./colors";

describe("colorToCss", () => {
  it("resolves standard xcolor names", () => {
    expect(colorToCss("red")).toMatch(/^#/);
    expect(colorToCss("blue")).toMatch(/^#/);
    expect(colorToCss("black")).toMatch(/^#/);
    expect(colorToCss("GRAY")).toBe(colorToCss("gray"));
  });

  it("resolves the HSE brand blue", () => {
    expect(colorToCss("hseblue")).toBe("#102D69");
  });

  it("passes through hex specs", () => {
    expect(colorToCss("102D69")).toBe("#102D69");
    expect(colorToCss("#abc")).toBe("#abc");
  });

  it("returns null for xcolor mixes / unknown names", () => {
    expect(colorToCss("blue!15")).toBeNull();
    expect(colorToCss("mycustomcolor")).toBeNull();
    expect(colorToCss("")).toBeNull();
  });
});
