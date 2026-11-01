import { describe, expect, it } from "vitest";
import {
  deviceCountdown,
  maskDeviceCode,
  normalizeDeviceCode,
} from "./DeviceCodeCard";

describe("код устройства", () => {
  it("нормализует ввод и отвергает чужие символы", () => {
    expect(normalizeDeviceCode(" bcdf 2345 ")).toBe("BCDF-2345");
    expect(normalizeDeviceCode("bcdf-2345")).toBe("BCDF-2345");
    expect(normalizeDeviceCode("AEIO-0001")).toBeNull();
    expect(normalizeDeviceCode("BCDF-234")).toBeNull();
  });

  it("маска ставит дефис после четвёртого знака", () => {
    expect(maskDeviceCode("bcdf2")).toBe("BCDF-2");
    expect(maskDeviceCode("bc")).toBe("BC");
  });

  it("отсчёт срока: минуты и секунды, после срока null", () => {
    const now = Date.parse("2026-11-01T09:40:00Z");
    expect(deviceCountdown("2026-11-01T09:48:42Z", now)).toBe("8:42");
    expect(deviceCountdown("2026-11-01T09:39:00Z", now)).toBeNull();
  });
});
