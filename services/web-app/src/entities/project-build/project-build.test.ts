import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AUTO_FETCH_GAP_MS,
  LocalBuildsSchema,
  ProjectBuildsSchema,
  describeCloudDoc,
  describeLocalDoc,
  isMeteredConnection,
  markAutoFetched,
  resetAutoFetchMemo,
  shortCommit,
  shouldAutoFetch,
  type DocumentBuildStatus,
  type DocumentBuilds,
} from ".";

const build = (over: Record<string, unknown> = {}) => ({
  at: "2026-11-04T09:55:00Z",
  commit: "9f2c1e7a4b0d",
  pages: 14,
  fresh: true,
  sha256: "a".repeat(64),
  size: 1000,
  ...over,
});

const cloudDoc = (over: Partial<DocumentBuilds> = {}): DocumentBuilds => ({
  doc_id: "tz",
  cloud: null,
  cloud_running: false,
  cloud_failed_at: null,
  studio: null,
  ...over,
});

const localDoc = (
  over: Partial<DocumentBuildStatus> = {},
): DocumentBuildStatus => ({
  doc_id: "tz",
  local: null,
  cloud: null,
  cloud_running: false,
  studio: null,
  relation: "none",
  can_fetch: false,
  ...over,
});

describe("статус сборок в облаке", () => {
  it("«собрано в облаке, в Студии нет», «в Студии, в облаке нет», оба, не собрано, идёт сборка", () => {
    expect(describeCloudDoc(cloudDoc({ cloud: build() })).key).toBe(
      "cloudOnly",
    );
    expect(
      describeCloudDoc(
        cloudDoc({ studio: { ...build(), artifact_id: "a", by_name: "Анна" } }),
      ).key,
    ).toBe("studioOnly");
    expect(
      describeCloudDoc(
        cloudDoc({
          cloud: build(),
          studio: {
            ...build({ at: "2026-11-04T09:00:00Z" }),
            artifact_id: "a",
            by_name: null,
          },
        }),
      ).key,
    ).toBe("both");
    expect(describeCloudDoc(cloudDoc()).key).toBe("none");
    expect(describeCloudDoc(cloudDoc({ cloud_running: true })).running).toBe(
      true,
    );
  });

  it("устаревшая сборка подсвечивается предупреждением, неизвестная версия нет", () => {
    expect(
      describeCloudDoc(cloudDoc({ cloud: build({ fresh: false }) })).tone,
    ).toBe("warn");
    expect(
      describeCloudDoc(cloudDoc({ cloud: build({ fresh: null }) })).fresh,
    ).toBeNull();
  });
});

describe("статус сборок в локальной Студии", () => {
  it("в облаке собрано, у вас нет: можно получить", () => {
    const view = describeLocalDoc(
      localDoc({ cloud: build(), relation: "cloud_only", can_fetch: true }),
    );
    expect(view.key).toBe("local.cloudOnly");
    expect(view.canFetch).toBe(true);
    expect(view.at).toBe("2026-11-04T09:55:00Z");
  });

  it("локальная сборка новее: предлагается заменить только с подтверждением", () => {
    const view = describeLocalDoc(
      localDoc({
        local: {
          at: "2026-11-04T09:59:00Z",
          commit: "x",
          fresh: true,
          sha256: "b",
          pages: 1,
          from_cloud: false,
        },
        cloud: build(),
        relation: "local_newer",
      }),
    );
    expect(view.localNewer).toBe(true);
    expect(view.canFetch).toBe(false);
  });

  it("получена из облака и совпадает", () => {
    const view = describeLocalDoc(
      localDoc({
        local: {
          at: "2026-11-04T09:55:00Z",
          commit: "9f2c1e7a4b0d",
          fresh: true,
          sha256: "a",
          pages: 1,
          from_cloud: true,
        },
        cloud: build(),
        relation: "same",
      }),
    );
    expect(view.key).toBe("local.same");
    expect(view.fromCloud).toBe(true);
  });

  it("коммит короткий", () => {
    expect(shortCommit("9f2c1e7a4b0d")).toBe("9f2c1e7");
    expect(shortCommit(null)).toBeNull();
  });
});

describe("автополучение", () => {
  beforeEach(() => {
    resetAutoFetchMemo();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("не чаще раза в несколько минут на проект", () => {
    expect(shouldAutoFetch("p1", 1000)).toBe(true);
    markAutoFetched("p1", 1000);
    expect(shouldAutoFetch("p1", 1000 + AUTO_FETCH_GAP_MS - 1)).toBe(false);
    expect(shouldAutoFetch("p1", 1000 + AUTO_FETCH_GAP_MS)).toBe(true);
    expect(shouldAutoFetch("p2", 1000)).toBe(true);
  });

  it("не качает на мобильной сети и при экономии трафика", () => {
    vi.stubGlobal("navigator", { connection: { type: "cellular" } });
    expect(isMeteredConnection()).toBe(true);
    expect(shouldAutoFetch("p1", 1)).toBe(false);
    vi.stubGlobal("navigator", { connection: { saveData: true } });
    expect(isMeteredConnection()).toBe(true);
    vi.stubGlobal("navigator", { connection: { type: "wifi" } });
    expect(isMeteredConnection()).toBe(false);
  });
});

describe("контракт сборок", () => {
  it("принимает ответы облака и локальной Студии", () => {
    expect(() =>
      ProjectBuildsSchema.parse({
        head: null,
        dirty: false,
        max_pdf_bytes: 1,
        documents: [cloudDoc()],
      }),
    ).not.toThrow();
    expect(() =>
      LocalBuildsSchema.parse({
        connected: true,
        cloud_error: null,
        local_head: null,
        local_dirty: false,
        cloud_head: null,
        documents: [localDoc()],
      }),
    ).not.toThrow();
  });
});
