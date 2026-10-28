import axios, {
  type AxiosAdapter,
  type InternalAxiosRequestConfig,
} from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n, toast } from "@shared/lib";
import { installDemoAdapter } from "./demo/adapter";
import { createDemoRouter, demoError, demoJson } from "./demo/router";
import { ApiError, adminClient, apiClient, createApiClient } from "./client";
import { setCsrfToken, setUnauthorizedHandler } from "./session";

type Seen = InternalAxiosRequestConfig[];

const stub =
  (status: number, body: unknown, seen: Seen = []): AxiosAdapter =>
  (config) => {
    seen.push(config);
    const response = {
      data: body,
      status,
      statusText: "",
      headers: {},
      config,
    };
    return status >= 400
      ? Promise.reject(
          new axios.AxiosError("x", "ERR_BAD_REQUEST", config, {}, response),
        )
      : Promise.resolve(response);
  };

describe("createApiClient", () => {
  beforeEach(() => {
    setCsrfToken(null);
    setUnauthorizedHandler(null);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends cookies and the interface language", async () => {
    const seen: Seen = [];
    const client = createApiClient({ baseURL: "/api/v1" });
    client.defaults.adapter = stub(200, {}, seen);
    await client.get("/x");
    expect(seen[0]?.withCredentials).toBe(true);
    expect(seen[0]?.headers.get("X-Interface-Language")).toBeTruthy();
  });

  it("adds X-CSRF-Token to unsafe methods only", async () => {
    const seen: Seen = [];
    const client = createApiClient({ baseURL: "/api/v1" });
    client.defaults.adapter = stub(200, {}, seen);
    setCsrfToken("tok-1");
    await client.get("/x");
    await client.head("/x");
    for (const method of ["post", "put", "patch", "delete"] as const) {
      await client.request({ url: "/x", method });
    }
    const byMethod = Object.fromEntries(
      seen.map((c) => [c.method, c.headers.get("X-CSRF-Token")]),
    );
    expect(byMethod).toEqual({
      get: undefined,
      head: undefined,
      post: "tok-1",
      put: "tok-1",
      patch: "tok-1",
      delete: "tok-1",
    });
  });

  it("sends no CSRF header while there is no token (local mode)", async () => {
    const seen: Seen = [];
    const client = createApiClient({ baseURL: "/api/v1" });
    client.defaults.adapter = stub(200, {}, seen);
    await client.post("/x", {});
    expect(seen[0]?.headers.get("X-CSRF-Token")).toBeUndefined();
  });

  it("picks up a token that changes between requests", async () => {
    const seen: Seen = [];
    const client = createApiClient({ baseURL: "/api/v1" });
    client.defaults.adapter = stub(200, {}, seen);
    setCsrfToken("a");
    await client.post("/x");
    setCsrfToken("b");
    await client.post("/x");
    expect(seen.map((c) => c.headers.get("X-CSRF-Token"))).toEqual(["a", "b"]);
  });

  it("does not toast a 401 and notifies the handler once for a burst", async () => {
    const error = vi.spyOn(toast, "error").mockImplementation(() => "");
    let release: () => void = () => undefined;
    const handler = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          release = resolve;
        }),
    );
    setUnauthorizedHandler(handler);
    const client = createApiClient({ baseURL: "/api/v1" });
    client.defaults.adapter = stub(401, {
      detail: "Нужен вход",
      code: "auth_required",
    });
    const results = await Promise.allSettled([
      client.get("/projects"),
      client.post("/projects", {}),
    ]);
    expect(results.every((r) => r.status === "rejected")).toBe(true);
    const first = results[0];
    expect(first?.status === "rejected" && first.reason).toBeInstanceOf(
      ApiError,
    );
    expect(error).not.toHaveBeenCalled();
    expect(handler).toHaveBeenCalledTimes(1);
    release();
  });

  it("does not loop on 401 from bootstrap or login", async () => {
    const handler = vi.fn(() => undefined);
    setUnauthorizedHandler(handler);
    const client = createApiClient({ baseURL: "/api/v1" });
    client.defaults.adapter = stub(401, {
      detail: "no",
      code: "auth_required",
    });
    await client.get("/session/bootstrap").catch(() => undefined);
    await client.post("/auth/login", {}).catch(() => undefined);
    expect(handler).not.toHaveBeenCalled();
  });

  it("refreshes the session on csrf_failed and still shows the toast", async () => {
    const error = vi.spyOn(toast, "error").mockImplementation(() => "");
    const handler = vi.fn(() => undefined);
    setUnauthorizedHandler(handler);
    const client = createApiClient({ baseURL: "/api/v1" });
    client.defaults.adapter = stub(403, {
      detail: "CSRF",
      code: "csrf_failed",
    });
    await client.post("/projects", {}).catch(() => undefined);
    expect(handler).toHaveBeenCalledTimes(1);
    expect(error).toHaveBeenCalledTimes(1);
  });

  it("still toasts other mutation errors", async () => {
    const error = vi.spyOn(toast, "error").mockImplementation(() => "");
    const client = createApiClient({ baseURL: "/api/v1" });
    client.defaults.adapter = stub(500, { detail: "boom", code: "x" });
    await client.post("/x").catch(() => undefined);
    expect(error).toHaveBeenCalledTimes(1);
  });

  it("exports separate api and admin clients", () => {
    expect(apiClient.defaults.baseURL).toMatch(/\/api\/v1$/);
    expect(adminClient.defaults.baseURL).toMatch(/\/api\/admin$/);
  });

  it("works with the demo adapter (regression)", async () => {
    const client = createApiClient({ baseURL: "/api/v1" });
    installDemoAdapter(
      client,
      createDemoRouter([
        { method: "GET", pattern: "/ok", handler: () => demoJson({ a: 1 }) },
        {
          method: "GET",
          pattern: "/nope",
          handler: () => demoError(409, "conflict", "c"),
        },
      ]),
    );
    expect((await client.get("/ok")).data).toEqual({ a: 1 });
    await expect(client.get("/nope")).rejects.toMatchObject({
      status: 409,
      code: "conflict",
    });
  });
});

describe("отказ по роли (forbidden_role)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const run = async (body: unknown) => {
    const spy = vi.spyOn(toast, "error").mockImplementation(() => "");
    const client = createApiClient({ baseURL: "/api/v1" });
    client.defaults.adapter = stub(403, body);
    await expect(client.patch("/projects/p1", {})).rejects.toBeInstanceOf(
      ApiError,
    );
    return spy;
  };

  it("тост называет нужную роль словами интерфейса", async () => {
    await i18n.changeLanguage("ru");
    const spy = await run({
      detail: "Forbidden",
      code: "forbidden_role",
      required_role: "editor",
    });
    expect(spy.mock.calls[0]?.[0]).toBe(
      "Недостаточно прав: нужна роль «Редактор».",
    );
    await i18n.changeLanguage("en");
    const spyEn = await run({
      detail: "Forbidden",
      code: "forbidden_role",
      required_role: "owner",
    });
    expect(spyEn.mock.calls.at(-1)?.[0]).toBe(
      "Not enough permissions: the “Owner” role is required.",
    );
    await i18n.changeLanguage("ru");
  });

  it("без названия роли читается как обычный отказ", async () => {
    await i18n.changeLanguage("ru");
    const spy = await run({ detail: "Forbidden", code: "forbidden_role" });
    expect(spy.mock.calls[0]?.[0]).toBe(
      "Недостаточно прав для этого действия.",
    );
  });
});
