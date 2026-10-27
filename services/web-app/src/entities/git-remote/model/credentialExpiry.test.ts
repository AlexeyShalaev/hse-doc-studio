import { describe, expect, it } from "vitest";
import {
  EXPIRING_SOON_DAYS,
  credentialExpiry,
  worstExpiry,
} from "./credentialExpiry";

const NOW = Date.parse("2026-10-27T12:00:00Z");
const inDays = (days: number): string =>
  new Date(NOW + days * 24 * 60 * 60 * 1000).toISOString();

describe("credentialExpiry", () => {
  it("без срока или с мусором срока нет", () => {
    expect(credentialExpiry(null, NOW).state).toBe("none");
    expect(credentialExpiry(undefined, NOW).state).toBe("none");
    expect(credentialExpiry("вчера", NOW).state).toBe("none");
  });

  it("далеко, скоро и просрочен", () => {
    expect(credentialExpiry(inDays(90), NOW)).toMatchObject({
      state: "ok",
      days: 90,
    });
    expect(credentialExpiry(inDays(EXPIRING_SOON_DAYS), NOW).state).toBe(
      "soon",
    );
    expect(credentialExpiry(inDays(2.2), NOW)).toMatchObject({
      state: "soon",
      days: 3,
    });
    expect(credentialExpiry(inDays(-5), NOW)).toMatchObject({
      state: "expired",
      days: 5,
    });
    expect(credentialExpiry(inDays(0), NOW).state).toBe("expired");
  });

  it("worstExpiry выбирает самый срочный", () => {
    expect(worstExpiry([null, inDays(90), inDays(5)], NOW)).toMatchObject({
      state: "soon",
      days: 5,
    });
    expect(worstExpiry([inDays(5), inDays(-1)], NOW).state).toBe("expired");
    expect(worstExpiry([], NOW).state).toBe("none");
    expect(worstExpiry([null], NOW).state).toBe("none");
  });
});
