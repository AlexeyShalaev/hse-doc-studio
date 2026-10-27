import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { downloadBlob } from "./downloadBlob";

describe("downloadBlob", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    Reflect.deleteProperty(URL, "createObjectURL");
    Reflect.deleteProperty(URL, "revokeObjectURL");
  });

  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("нажимает на ссылку с нужным именем и освобождает адрес", () => {
    const create = vi.fn(() => "blob:demo");
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    const blob = new Blob(["x"]);
    downloadBlob(blob, "project.bundle");
    expect(create).toHaveBeenCalledWith(blob);
    expect(click).toHaveBeenCalledTimes(1);
    const link = click.mock.contexts[0] as HTMLAnchorElement;
    expect(link.download).toBe("project.bundle");
    expect(link.href).toBe("blob:demo");
    // Адрес живёт ещё какое-то время, чтобы браузер успел начать загрузку.
    expect(revoke).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(revoke).toHaveBeenCalledWith("blob:demo");
    // Ссылка не остаётся в документе.
    expect(document.querySelector("a[download]")).toBeNull();
  });
});
