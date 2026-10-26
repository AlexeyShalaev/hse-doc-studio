import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ApiError, apiClient } from "@shared/api";
import {
  createDemoRouter,
  demoError,
  demoJson,
  installDemoAdapter,
} from "@shared/api/demo";
import { gitSyncApi, readGitError } from "./gitSyncApi";

const PROJECT = "11111111-1111-4111-8111-111111111111";

const caught = async (run: () => Promise<unknown>): Promise<unknown> => {
  try {
    await run();
  } catch (error) {
    return error;
  }
  throw new Error("expected the call to fail");
};

describe("flat git error bodies", () => {
  const originalAdapter = apiClient.defaults.adapter;

  beforeEach(() => {
    installDemoAdapter(
      apiClient,
      createDemoRouter([
        {
          method: "PUT",
          pattern: "/projects/:projectId/git/remote",
          handler: () =>
            demoError(409, "credential_in_use", "Доступ используется.", {
              projects: [{ project_id: "p1", name: "Курсовая" }],
            }),
        },
        {
          method: "POST",
          pattern: "/projects/:projectId/git/sync",
          handler: () =>
            demoError(409, "sync_busy", "Синхронизация уже идёт.", {
              operation_id: "op-7",
            }),
        },
        {
          method: "POST",
          pattern: "/projects/:projectId/git/conflicts/resolve",
          handler: () =>
            demoError(409, "unresolved_conflicts", "Есть нерешённое.", {
              paths: ["a.tex", "b.tex"],
            }),
        },
        {
          method: "POST",
          pattern: "/projects/:projectId/git/fetch",
          handler: () => demoError(404, "not_found_or_no_access", "Нет."),
        },
        {
          method: "POST",
          pattern: "/projects/:projectId/git/bundle/export",
          handler: () =>
            demoJson(
              new Blob([
                JSON.stringify({
                  detail: "Нечего выгружать.",
                  code: "sync_incomplete",
                }),
              ]),
              409,
            ),
        },
      ]),
    );
  });

  afterEach(() => {
    if (originalAdapter !== undefined) {
      apiClient.defaults.adapter = originalAdapter;
    }
  });

  it("keeps the flat extras on ApiError.data", async () => {
    const error = await caught(() =>
      gitSyncApi.connectRemote(PROJECT, { url: "https://x/y.git" } as never),
    );
    expect(error).toBeInstanceOf(ApiError);
    const api = error as ApiError;
    expect(api.code).toBe("credential_in_use");
    expect(api.detail).toBe("Доступ используется.");
    expect(api.data).toEqual({
      projects: [{ project_id: "p1", name: "Курсовая" }],
    });
  });

  it("reads typed extras through readGitError", async () => {
    const busy = readGitError(
      await caught(() => gitSyncApi.startSync(PROJECT)),
    );
    expect(busy?.code).toBe("sync_busy");
    expect(busy?.operation_id).toBe("op-7");

    const unresolved = readGitError(
      await caught(() =>
        gitSyncApi.resolveConflicts(PROJECT, { fingerprint: "f" }),
      ),
    );
    expect(unresolved?.paths).toEqual(["a.tex", "b.tex"]);
  });

  it("leaves data empty when the body has no extras", async () => {
    const error = (await caught(() =>
      gitSyncApi.fetchRemote(PROJECT),
    )) as ApiError;
    expect(error.code).toBe("not_found_or_no_access");
    expect(error.data).toBeNull();
  });

  it("returns null for errors that are not ApiError", () => {
    expect(readGitError(new Error("boom"))).toBeNull();
  });

  it("decodes an error body that arrives as a Blob", async () => {
    const error = (await caught(() =>
      gitSyncApi.exportBundle(PROJECT),
    )) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("sync_incomplete");
    expect(error.detail).toBe("Нечего выгружать.");
  });
});
