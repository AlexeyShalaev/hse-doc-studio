import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { registerPendingSave } from "../pendingSaves";
import {
  RELOAD_GUARD_MS,
  RELOAD_STAMP_KEY,
  handleStaleBuild,
  installStaleBuildGuard,
  reloadToNewBuild,
} from "./staleBuild";
import { useStaleBuildStore } from "./staleBuildStore";

const reload = vi.fn();

beforeEach(() => {
  reload.mockReset();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: {
      reload,
      pathname: "/",
      search: "",
      hash: "",
      href: "http://localhost/",
    },
  });
  window.sessionStorage.clear();
  useStaleBuildStore.setState({ reason: null, screenShown: false });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("handleStaleBuild", () => {
  it("первая ошибка чанка перезагружает страницу и ставит метку времени", () => {
    expect(handleStaleBuild("chunk", 1_000_000)).toBe("reloading");
    expect(reload).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.getItem(RELOAD_STAMP_KEY)).toBe("1000000");
    expect(useStaleBuildStore.getState().reason).toBe("chunk");
  });

  it("повтор сразу после перезагрузки не зацикливает: только сообщение", () => {
    handleStaleBuild("chunk", 1_000_000);
    reload.mockClear();
    expect(handleStaleBuild("chunk", 1_000_000 + 5_000)).toBe("notice");
    expect(reload).not.toHaveBeenCalled();
    expect(useStaleBuildStore.getState().reason).toBe("chunk");
  });

  it("после окна защиты вкладка снова может перезагрузиться", () => {
    handleStaleBuild("chunk", 1_000_000);
    reload.mockClear();
    expect(handleStaleBuild("chunk", 1_000_000 + RELOAD_GUARD_MS + 1)).toBe(
      "reloading",
    );
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("метка из будущего не блокирует перезагрузку навсегда", () => {
    window.sessionStorage.setItem(RELOAD_STAMP_KEY, "9999999999999");
    expect(handleStaleBuild("chunk", 1_000_000)).toBe("reloading");
  });

  it("при несохранённом вводе не перезагружает, а оставляет баннер", () => {
    const off = registerPendingSave(
      () => undefined,
      () => true,
    );
    expect(handleStaleBuild("chunk", 1_000_000)).toBe("notice");
    expect(reload).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem(RELOAD_STAMP_KEY)).toBeNull();
    expect(useStaleBuildStore.getState().reason).toBe("chunk");
    off();
  });

  it("чистый редактор перезагрузке не мешает", () => {
    const off = registerPendingSave(
      () => undefined,
      () => false,
    );
    expect(handleStaleBuild("chunk", 1_000_000)).toBe("reloading");
    off();
  });

  it("без sessionStorage автоперезагрузки нет: защититься от цикла нечем", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(handleStaleBuild("chunk", 1_000_000)).toBe("notice");
    expect(reload).not.toHaveBeenCalled();
  });

  it("новая версия по опросу только показывает баннер", () => {
    expect(handleStaleBuild("version", 1_000_000)).toBe("notice");
    expect(reload).not.toHaveBeenCalled();
    expect(useStaleBuildStore.getState().reason).toBe("version");
  });
});

describe("reloadToNewBuild", () => {
  it("сначала просит редакторы сохранить правки, потом перезагружает", async () => {
    const order: string[] = [];
    const off = registerPendingSave(() => {
      order.push("flush");
    });
    reload.mockImplementation(() => order.push("reload"));
    await reloadToNewBuild();
    expect(order).toEqual(["flush", "reload"]);
    off();
  });

  it("перезагружает, даже если сохранение упало", async () => {
    const off = registerPendingSave(() => {
      throw new Error("save failed");
    });
    await reloadToNewBuild();
    expect(reload).toHaveBeenCalledTimes(1);
    off();
  });
});

describe("installStaleBuildGuard", () => {
  it("vite:preloadError с ошибкой чанка запускает перезагрузку и не отменяется", () => {
    const off = installStaleBuildGuard();
    const event = new Event("vite:preloadError", { cancelable: true });
    Object.assign(event, {
      payload: new TypeError(
        "Failed to fetch dynamically imported module: /assets/admin-x.js",
      ),
    });
    window.dispatchEvent(event);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(false);
    off();
  });

  it("чужие ошибки не трогает", () => {
    const off = installStaleBuildGuard();
    const event = new Event("vite:preloadError");
    Object.assign(event, { payload: new Error("Network Error") });
    window.dispatchEvent(event);
    expect(reload).not.toHaveBeenCalled();
    expect(useStaleBuildStore.getState().reason).toBeNull();
    off();
  });

  it("отказ промиса с ошибкой импорта тоже считается устаревшей сборкой", () => {
    const off = installStaleBuildGuard();
    const event = new Event("unhandledrejection");
    Object.assign(event, {
      reason: new TypeError("Importing a module script failed."),
    });
    window.dispatchEvent(event);
    expect(reload).toHaveBeenCalledTimes(1);
    off();
  });
});
