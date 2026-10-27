import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { vcsApi } from "./vcsApi";
import { VcsCommitSchema } from "./vcsSchemas";

describe("vcsApi.getHistoryPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const capture = async (
    params: Parameters<typeof vcsApi.getHistoryPage>[1],
  ) => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: [] });
    await vcsApi.getHistoryPage("p1", params);
    const [url, config] = get.mock.calls[0] ?? [];
    return axios.getUri({ url: String(url), ...config });
  };

  it("repeats kind instead of using brackets and drops empty filters", async () => {
    const uri = await capture({
      kind: ["edit", "sync"],
      authorEmail: "",
      q: "",
      sync: "all",
    });
    expect(uri).toBe(
      "/projects/p1/vcs/history?kind=edit&kind=sync&limit=100&offset=0",
    );
  });

  it("sends the sync filter, author and paging when set", async () => {
    const uri = await capture({
      authorEmail: "anna@edu.hse.ru",
      sync: "unpushed",
      q: "рис",
      limit: 20,
      offset: 40,
    });
    const params = new URL(uri, "http://x").searchParams;
    expect(params.get("author_email")).toBe("anna@edu.hse.ru");
    expect(params.get("sync")).toBe("unpushed");
    expect(params.get("q")).toBe("рис");
    expect(params.get("limit")).toBe("20");
    expect(params.get("offset")).toBe("40");
  });
});

describe("VcsCommitSchema", () => {
  it("accepts a commit from an older backend without sync fields", () => {
    const parsed = VcsCommitSchema.parse({
      id: "a",
      short_id: "a",
      kind: "edit",
      message: "m",
      author: "x",
      created_at: "2026-10-26T10:00:00Z",
      parents: [],
      refs: [],
    });
    expect(parsed.sync).toBeUndefined();
  });
});
