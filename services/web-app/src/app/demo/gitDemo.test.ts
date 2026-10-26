import axios, { type AxiosAdapter, type AxiosResponse } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ZodType } from "zod";
import {
  createDemoRouter,
  installDemoAdapter,
  type DemoResponse,
} from "@shared/api/demo";
import {
  CiPreviewSchema,
  CiWriteSchema,
  CloneResultSchema,
  ConflictDiffSchema,
  ConflictFileDetailSchema,
  ConflictSessionSchema,
  GIT_UI_STATES,
  GitContentsSchema,
  GitErrorBodySchema,
  GitStatusSchema,
  HistoryFacetsSchema,
  OperationSchema,
  OperationStartedSchema,
  SyncResultSchema,
  type GitOperation,
} from "@entities/git-sync";
import {
  CloneDefaultsSchema,
  GIT_PROBE_RELATIONS,
  GitCredentialListSchema,
  GitCredentialSchema,
  GitHostListSchema,
  ProbeSchema,
  SecretsStatusSchema,
  SharedFolderSchema,
} from "@entities/git-remote";
import { ProfileSchema } from "@entities/profile";
import { getWorld, gitDemoRoutes, resetWorld } from "./routes";
import { SCENARIOS, projectOf, type DemoScenarioId } from "./scenarios";

const router = createDemoRouter(gitDemoRoutes);
const PROJECT = "22222222-2222-4222-8222-222222222222";

const call = async (
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  options: {
    body?: unknown;
    query?: Record<string, string | string[]>;
    forward?: () => Promise<AxiosResponse>;
  } = {},
): Promise<DemoResponse> => {
  const found = router.match(method, path);
  if (!found) throw new Error(`no demo route for ${method} ${path}`);
  return found.handler({
    method,
    path,
    params: found.params,
    query: options.query ?? {},
    body: options.body ?? null,
    forward:
      options.forward ??
      (() => Promise.reject(new Error("no real backend in tests"))),
  });
};

const parsed = async <T>(
  response: Promise<DemoResponse>,
  schema: ZodType<T>,
  status = 200,
): Promise<T> => {
  const res = await response;
  expect(res.status).toBe(status);
  return schema.parse(res.data);
};

const errorOf = async (response: Promise<DemoResponse>) => {
  const res = await response;
  expect(res.status).toBeGreaterThanOrEqual(400);
  return { status: res.status, body: GitErrorBodySchema.parse(res.data) };
};

const status = (id = PROJECT) =>
  parsed(call("GET", `/projects/${id}/git`), GitStatusSchema);

const operation = (id: string) =>
  parsed(call("GET", `/git/operations/${id}`), OperationSchema);

const startSync = async (): Promise<string> =>
  (
    await parsed(
      call("POST", `/projects/${PROJECT}/git/sync`, { body: {} }),
      OperationStartedSchema,
      202,
    )
  ).operation_id;

const EXPECTED_STATE: Record<DemoScenarioId, string> = {
  not_connected: "no_remote",
  connect_warnings: "no_remote",
  connect_large_files: "no_remote",
  connect_no_profile: "no_remote",
  unfetched: "unfetched",
  up_to_date: "up_to_date",
  ahead: "ahead",
  behind: "behind",
  diverged: "diverged",
  diverged_conflicts: "diverged",
  syncing: "syncing",
  conflicts: "conflicts",
  auth_failed: "auth_failed",
  offline: "offline",
  error: "error",
  schema_newer: "blocked",
  off_branch: "blocked",
  read_only: "blocked",
  no_profile: "blocked",
  shared_folder: "up_to_date",
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-26T10:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("demo scenarios", () => {
  it.each(SCENARIOS.map((s) => s.id))(
    "%s gives a status that satisfies the contract",
    async (id) => {
      resetWorld(id);
      const current = await status();
      expect(current.ui_state).toBe(EXPECTED_STATE[id]);
    },
  );

  it("covers every ui_state of the contract", async () => {
    const seen = new Set<string>();
    for (const scenario of SCENARIOS) {
      resetWorld(scenario.id);
      seen.add((await status()).ui_state);
    }
    for (const state of GIT_UI_STATES) expect(seen).toContain(state);
  });

  it("shows a running operation in the syncing scenario and can cancel it", async () => {
    resetWorld("syncing");
    const current = await status();
    expect(current.operation?.cancellable).toBe(true);
    const id = current.operation?.id ?? "";
    const cancelled = await parsed(
      call("POST", `/git/operations/${id}/cancel`),
      OperationSchema,
    );
    expect(cancelled.status).toBe("cancelled");
    expect((await status()).ui_state).toBe("diverged");
  });

  it("answers an unknown project with the scenario state", async () => {
    resetWorld("ahead");
    const a = await status("33333333-3333-4333-8333-333333333333");
    expect(a.ahead).toBe(4);
    expect(a.outgoing.length).toBeLessThanOrEqual(5);
  });
});

describe("demo connect flow", () => {
  beforeEach(() => {
    resetWorld("not_connected");
  });

  const probe = (url: string, credentialId: string | null = null) =>
    parsed(
      call("POST", "/git/remote/probe", {
        body: { url, credential_id: credentialId, project_id: PROJECT },
      }),
      ProbeSchema,
    );

  it("never reports a token that was pasted into the address", async () => {
    const result = await probe(
      "https://ghp_secret123@github.com/ivan/repo.git",
    );
    expect(result.url.token_stripped).toBe(true);
    expect(JSON.stringify(result)).not.toContain("ghp_secret123");
    expect(result.url.display_url).toBe("https://github.com/ivan/repo.git");
  });

  it("reaches every probe relation by address", async () => {
    const urls: Record<string, string> = {
      empty: "https://github.com/ivan/new-repo",
      studio_project: "",
      same_project: "https://github.com/ivan/same",
      same_project_unrelated_history: "https://github.com/ivan/unrelated",
      other_project: "https://github.com/ivan/other",
      not_studio_project: "https://github.com/ivan/plain",
      unknown: "https://github.com/ivan/offline",
    };
    const relations = new Set<string>();
    for (const url of Object.values(urls)) {
      if (url === "") continue;
      relations.add((await probe(url)).relation);
    }
    const noProject = await parsed(
      call("POST", "/git/remote/probe", {
        body: { url: "https://github.com/ivan/repo" },
      }),
      ProbeSchema,
    );
    relations.add(noProject.relation);
    for (const relation of GIT_PROBE_RELATIONS) {
      expect(relations).toContain(relation);
    }
  });

  it("returns refusals as ok: false with a code", async () => {
    const auth = await probe("https://github.com/ivan/auth-repo");
    expect(auth.ok).toBe(false);
    expect(auth.error?.code).toBe("auth_failed");
    const withToken = await probe(
      "https://github.com/ivan/auth-repo",
      "00000000-0000-4000-8000-000000000001",
    );
    expect(withToken.ok).toBe(true);
    const offline = await probe("https://github.com/ivan/offline");
    expect(offline.error?.code).toBe("offline");
    expect(offline.reachable).toBe(false);
  });

  it("rejects an unreadable address with 400 url_invalid", async () => {
    const { status: code, body } = await errorOf(
      call("POST", "/git/remote/probe", { body: { url: "not a url" } }),
    );
    expect(code).toBe(400);
    expect(body.code).toBe("url_invalid");
    const scheme = await errorOf(
      call("POST", "/git/remote/probe", { body: { url: "ext::sh" } }),
    );
    expect(scheme.body.code).toBe("url_scheme_forbidden");
  });

  it("asks to confirm an unknown ssh server key and then connects", async () => {
    const url = "git@gitlab.hse.ru:ivan/coursework.git";
    const first = await probe(url);
    expect(first.error?.code).toBe("host_key_unknown");
    const fingerprint = first.error?.host_keys?.[0]?.fingerprint_sha256 ?? "";
    expect(fingerprint).toMatch(/^SHA256:/);
    const trust = await call("POST", "/git/hosts/trust", {
      body: { host: "gitlab.hse.ru", fingerprint_sha256: fingerprint },
    });
    expect(trust.status).toBe(204);
    expect((await probe(url)).ok).toBe(true);
    const hosts = await parsed(call("GET", "/git/hosts"), GitHostListSchema);
    expect(hosts.map((h) => h.host)).toContain("gitlab.hse.ru");
  });

  it("connects an empty repository and the project becomes ahead", async () => {
    const result = await parsed(
      call("PUT", `/projects/${PROJECT}/git/remote`, {
        body: {
          url: "https://github.com/ivan/new-repo",
          credential_id: "00000000-0000-4000-8000-000000000001",
          adopt: null,
        },
      }),
      GitStatusSchema,
    );
    expect(result.connected).toBe(true);
    expect(result.ui_state).toBe("ahead");
    expect(result.relation).toBe("remote_empty");
    expect(result.remote?.credential?.kind).toBe("pat");
    expect(result.remote?.web_url).toBe("https://github.com/ivan/new-repo");
  });

  it("explains why a repository cannot be connected", async () => {
    const put = (url: string, adopt: string | null = null) =>
      errorOf(
        call("PUT", `/projects/${PROJECT}/git/remote`, {
          body: { url, credential_id: null, adopt },
        }),
      );
    expect((await put("https://github.com/ivan/plain")).body.code).toBe(
      "not_a_studio_project",
    );
    const other = await put("https://github.com/ivan/other");
    expect(other.body.code).toBe("unrelated_histories");
    expect(other.body.can_adopt).toBe(false);
    const unrelated = await put("https://github.com/ivan/unrelated");
    expect(unrelated.body.can_adopt).toBe(true);
    const adopted = await parsed(
      call("PUT", `/projects/${PROJECT}/git/remote`, {
        body: {
          url: "https://github.com/ivan/unrelated",
          credential_id: null,
          adopt: "merge_remote",
        },
      }),
      GitStatusSchema,
    );
    expect(adopted.ui_state).toBe("diverged");
    expect((await put("https://github.com/ivan/same")).body.code).toBe(
      "remote_exists",
    );
  });

  it("disconnects and optionally forgets the credential", async () => {
    resetWorld("up_to_date");
    await status();
    const gone = await call("DELETE", `/projects/${PROJECT}/git/remote`, {
      query: { forget_credential: "true" },
    });
    expect(gone.status).toBe(204);
    expect((await status()).ui_state).toBe("no_remote");
    const credentials = await parsed(
      call("GET", "/git/credentials"),
      GitCredentialListSchema,
    );
    expect(credentials.map((c) => c.kind)).not.toContain("pat");
  });

  it("requires a profile before connecting", async () => {
    resetWorld("no_profile");
    const failure = await errorOf(
      call("PUT", `/projects/${PROJECT}/git/remote`, {
        body: {
          url: "https://github.com/ivan/new-repo",
          credential_id: null,
          adopt: null,
        },
      }),
    );
    expect(failure.body.code).toBe("profile_required");
  });
});

describe("demo sync flow", () => {
  const finishSync = async (): Promise<GitOperation> => {
    const id = await startSync();
    const running = await operation(id);
    expect(running.status).toBe("running");
    expect((await status()).ui_state).toBe("syncing");
    await vi.advanceTimersByTimeAsync(5_000);
    return operation(id);
  };

  it("pushes what is ahead and returns to up_to_date", async () => {
    resetWorld("ahead");
    const done = await finishSync();
    expect(done.status).toBe("succeeded");
    const result = SyncResultSchema.parse(done.result);
    expect(result.outcome).toBe("pushed");
    expect(result.pushed_commits).toBe(4);
    const after = await status();
    expect(after.ui_state).toBe("up_to_date");
    expect(after.last_sync?.outcome).toBe("pushed");
    expect(after.outgoing).toEqual([]);
  });

  it("fast-forwards when behind and merges when diverged", async () => {
    resetWorld("behind");
    expect(SyncResultSchema.parse((await finishSync()).result).outcome).toBe(
      "fast_forwarded",
    );
    resetWorld("diverged");
    const merged = SyncResultSchema.parse((await finishSync()).result);
    expect(merged.outcome).toBe("merged");
    expect(merged.auto.length).toBeGreaterThan(0);
    expect(merged.merge_commit).toMatch(/^[0-9a-f]{40}$/);
  });

  it("reports progress with a percent while fetching", async () => {
    resetWorld("ahead");
    const id = await startSync();
    await vi.advanceTimersByTimeAsync(1_500);
    const op = await operation(id);
    expect(op.phase).toBe("fetch");
    expect(op.percent).toBeGreaterThan(0);
    expect(op.cancellable).toBe(true);
  });

  it("refuses a second sync while one is running", async () => {
    resetWorld("ahead");
    const id = await startSync();
    const busy = await errorOf(
      call("POST", `/projects/${PROJECT}/git/sync`, { body: {} }),
    );
    expect(busy.status).toBe(409);
    expect(busy.body.code).toBe("sync_busy");
    expect(busy.body.operation_id).toBe(id);
  });

  it("fails the operation with the stored reason when offline", async () => {
    resetWorld("offline");
    const done = await finishSync();
    expect(done.status).toBe("failed");
    expect(done.error?.code).toBe("offline");
    expect((await status()).last_error?.code).toBe("offline");
  });

  it.each([
    ["schema_newer", 409, "remote_schema_newer"],
    ["off_branch", 409, "off_branch"],
    ["read_only", 423, "project_read_only"],
    ["no_profile", 409, "profile_required"],
  ] as const)("%s blocks sync with %i %s", async (id, code, error) => {
    resetWorld(id);
    const failure = await errorOf(
      call("POST", `/projects/${PROJECT}/git/sync`, { body: {} }),
    );
    expect(failure.status).toBe(code);
    expect(failure.body.code).toBe(error);
  });

  it("fetch fails with the scenario error and works otherwise", async () => {
    resetWorld("auth_failed");
    expect(
      (await errorOf(call("POST", `/projects/${PROJECT}/git/fetch`))).body.code,
    ).toBe("auth_failed");
    resetWorld("unfetched");
    const fetched = await parsed(
      call("POST", `/projects/${PROJECT}/git/fetch`),
      GitStatusSchema,
    );
    expect(fetched.ui_state).toBe("behind");
  });

  it("updates auto fetch settings with the 60 s floor", async () => {
    resetWorld("up_to_date");
    const updated = await parsed(
      call("PATCH", `/projects/${PROJECT}/git/settings`, {
        body: { auto_fetch: false, interval_s: 10, shared_folder_ack: true },
      }),
      GitStatusSchema,
    );
    expect(updated.auto_fetch.enabled).toBe(false);
    expect(updated.auto_fetch.interval_s).toBe(60);
  });

  it("serves contents, CI and bundle endpoints", async () => {
    resetWorld("up_to_date");
    await parsed(
      call("GET", `/projects/${PROJECT}/git/contents`),
      GitContentsSchema,
    );
    for (const provider of ["github", "gitlab"]) {
      const body = {
        provider,
        docs: "all",
        publish: "artifacts",
        triggers: ["push"],
        overwrite: false,
      };
      const preview = await parsed(
        call("POST", `/projects/${PROJECT}/git/ci/preview`, { body }),
        CiPreviewSchema,
      );
      expect(preview.files[0]?.content).toContain("hse-doc-studio build");
      const written = await parsed(
        call("POST", `/projects/${PROJECT}/git/ci/write`, {
          body: { ...body, overwrite: true },
        }),
        CiWriteSchema,
      );
      expect(written.written).toEqual(preview.files.map((f) => f.path));
    }
    const exported = await call(
      "POST",
      `/projects/${PROJECT}/git/bundle/export`,
      {
        body: { password: "secret" },
      },
    );
    expect(exported.headers?.["content-disposition"]).toMatch(
      /filename="coursework-\d{8}-\d{4}\.bundle\.hseenc"/,
    );
    expect(exported.data).toBeInstanceOf(Blob);
  });

  it("builds the CI file from the options and remembers what was written", async () => {
    resetWorld("up_to_date");
    const request = (overrides: Record<string, unknown>) => ({
      provider: "github",
      docs: "all",
      publish: "artifacts",
      triggers: ["push"],
      overwrite: false,
      ...overrides,
    });
    const preview = (overrides: Record<string, unknown> = {}) =>
      parsed(
        call("POST", `/projects/${PROJECT}/git/ci/preview`, {
          body: request(overrides),
        }),
        CiPreviewSchema,
      );
    const fresh = await preview();
    expect(fresh.files[0]).toMatchObject({ exists: false, same: false });
    expect(fresh.command).toBe("hse-doc-studio build --all");

    const picked = await preview({ docs: ["thesis"], publish: "release" });
    expect(picked.command).toBe("hse-doc-studio build --doc thesis");
    expect(picked.files[0]?.content).toContain("action-gh-release");

    // Отличающийся файл без подтверждения не записывается.
    const gitlab = request({ provider: "gitlab" });
    const refused = await parsed(
      call("POST", `/projects/${PROJECT}/git/ci/write`, { body: gitlab }),
      CiWriteSchema,
    );
    expect(refused.written).toEqual([]);
    const accepted = await parsed(
      call("POST", `/projects/${PROJECT}/git/ci/write`, {
        body: { ...gitlab, overwrite: true },
      }),
      CiWriteSchema,
    );
    expect(accepted.written).toEqual([".gitlab-ci.yml"]);
    const after = await preview({ provider: "gitlab" });
    expect(after.files[0]).toMatchObject({ exists: true, same: true });
  });

  it("checks bundle files before importing", async () => {
    resetWorld("up_to_date");
    const form = (name: string, password?: string) => {
      const data = new FormData();
      data.append("file", new File(["x"], name));
      if (password) data.append("password", password);
      return data;
    };
    const send = (data: FormData) =>
      call("POST", `/projects/${PROJECT}/git/bundle/import`, { body: data });
    expect((await errorOf(send(form("broken.bundle")))).body.code).toBe(
      "bundle_invalid",
    );
    expect((await errorOf(send(form("a.bundle.hseenc")))).body.code).toBe(
      "bundle_password_required",
    );
    expect(
      (await errorOf(send(form("a.bundle.hseenc", "wrong")))).body.code,
    ).toBe("bundle_password_wrong");
    await parsed(send(form("a.bundle")), OperationStartedSchema, 202);
  });

  it("answers the file-specific bundle failures", async () => {
    const form = (name: string) => {
      const data = new FormData();
      data.append("file", new File(["x"], name));
      return data;
    };
    const send = (name: string) => {
      resetWorld("up_to_date");
      return call("POST", `/projects/${PROJECT}/git/bundle/import`, {
        body: form(name),
      });
    };
    const other = await errorOf(send("other-project.bundle"));
    expect(other.status).toBe(409);
    expect(other.body.code).toBe("unrelated_histories");
    expect((await errorOf(send("old-part.bundle"))).body.code).toBe(
      "bundle_prerequisites_missing",
    );
    // «late» принимается, а ломается уже при слиянии.
    await parsed(send("late.bundle"), OperationStartedSchema, 202);
  });
});

describe("demo conflicts", () => {
  const conflictsPath = `/projects/${PROJECT}/git/conflicts`;

  it("a merge with conflicts leads to the conflict session", async () => {
    resetWorld("diverged_conflicts");
    const id = await startSync();
    await vi.advanceTimersByTimeAsync(5_000);
    const done = await operation(id);
    expect(SyncResultSchema.parse(done.result).outcome).toBe("conflicts");
    const after = await status();
    expect(after.ui_state).toBe("conflicts");
    expect(after.pending?.files_open).toBe(6);
    const session = await parsed(
      call("GET", conflictsPath),
      ConflictSessionSchema,
    );
    expect(session.counts).toEqual({ conflict: 6, auto: 4, total: 10 });
    expect(session.unresolved).toBe(6);
  });

  it("serves a detail for every conflict kind and a diff for each view", async () => {
    resetWorld("conflicts");
    const session = await parsed(
      call("GET", conflictsPath),
      ConflictSessionSchema,
    );
    const kinds = new Set<string>();
    for (const file of session.files.filter((f) => f.action === "conflict")) {
      const detail = await parsed(
        call("GET", `${conflictsPath}/file`, { query: { path: file.path } }),
        ConflictFileDetailSchema,
      );
      kinds.add(detail.kind);
      for (const view of ["ours", "theirs", "result"]) {
        await parsed(
          call("GET", `${conflictsPath}/diff`, {
            query: { path: file.path, view },
          }),
          ConflictDiffSchema,
        );
      }
    }
    expect([...kinds].sort()).toEqual(["binary", "delete", "json", "text"]);
  });

  it("serves blobs for both sides of a picture", async () => {
    resetWorld("conflicts");
    const blob = await call("GET", `${conflictsPath}/blob`, {
      query: { path: "images/architecture.png", side: "theirs" },
    });
    expect(blob.data).toBeInstanceOf(Blob);
    expect((blob.data as Blob).type).toBe("image/svg+xml");
  });

  it("counts drafts, refuses to resolve while open and applies once complete", async () => {
    resetWorld("conflicts");
    const session = await parsed(
      call("GET", conflictsPath),
      ConflictSessionSchema,
    );
    const unresolved = await errorOf(
      call("POST", `${conflictsPath}/resolve`, {
        body: {
          fingerprint: session.fingerprint,
          resolutions: null,
          push: true,
        },
      }),
    );
    expect(unresolved.status).toBe(422);
    expect(unresolved.body.code).toBe("unresolved_conflicts");
    expect(unresolved.body.paths).toHaveLength(6);

    const outdated = await errorOf(
      call("POST", `${conflictsPath}/resolve`, {
        body: { fingerprint: "stale", resolutions: null, push: true },
      }),
    );
    expect(outdated.body.code).toBe("plan_outdated");

    await call("PUT", `${conflictsPath}/draft`, {
      body: {
        resolutions: {
          "main.tex": {
            kind: "hunks",
            hunks: { "main.tex:a41c": { choice: "mine" } },
          },
        },
      },
    });
    const partial = await parsed(
      call("GET", conflictsPath),
      ConflictSessionSchema,
    );
    const main = partial.files.find((f) => f.path === "main.tex");
    expect(main?.open_hunks).toBe(2);
    expect(main?.resolved).toBe(false);
    expect(partial.drafts_saved_at).not.toBeNull();

    const everything = {
      "main.tex": { kind: "file", choice: "theirs" },
      ".hse-studio/forms/title-page.json": { kind: "file", choice: "mine" },
      "images/architecture.png": { kind: "file", choice: "newest" },
      "chapters/appendix.tex": { kind: "file", choice: "mine" },
      ".hse-studio/frozen/coursework.pdf": { kind: "file", choice: "theirs" },
      "chapters/Appendix-B.tex": { kind: "file", choice: "mine" },
    };
    const started = await parsed(
      call("POST", `${conflictsPath}/resolve`, {
        body: {
          fingerprint: session.fingerprint,
          resolutions: everything,
          push: true,
        },
      }),
      OperationStartedSchema,
      202,
    );
    await vi.advanceTimersByTimeAsync(5_000);
    const done = await operation(started.operation_id);
    expect(done.kind).toBe("resolve");
    expect(done.status).toBe("succeeded");
    const after = await status();
    expect(after.ui_state).toBe("up_to_date");
    expect(after.pending).toBeNull();
  });

  it("abort drops the session and leaves the project diverged", async () => {
    resetWorld("conflicts");
    const aborted = await parsed(
      call("DELETE", conflictsPath),
      GitStatusSchema,
    );
    expect(aborted.pending).toBeNull();
    expect(aborted.ui_state).toBe("diverged");
    expect((await errorOf(call("GET", conflictsPath))).body.code).toBe(
      "no_conflicts",
    );
  });
});

describe("demo credentials, profile and clone", () => {
  beforeEach(() => {
    resetWorld("not_connected");
  });

  it("never returns a token and reports only its family", async () => {
    const created = await parsed(
      call("POST", "/git/credentials", {
        body: {
          kind: "pat",
          label: "Рабочий",
          host: "github.com",
          username: "ivan",
          token: "github_pat_SECRETVALUE",
        },
      }),
      GitCredentialSchema,
      201,
    );
    expect(created.token_family).toBe("github_pat");
    expect(created.status).toBe("unverified");
    const list = await call("GET", "/git/credentials");
    expect(JSON.stringify(list.data)).not.toContain("SECRETVALUE");
    expect(JSON.stringify(created)).not.toContain("SECRETVALUE");
    await parsed(
      call("PATCH", `/git/credentials/${created.id}`, {
        body: { label: "Новое имя", token: "" },
      }),
      GitCredentialSchema,
    );
  });

  it("generates an ssh key with a public part and a fingerprint", async () => {
    const created = await parsed(
      call("POST", "/git/credentials", {
        body: { kind: "ssh_key", label: "Ключ", host: "git.example.com" },
      }),
      GitCredentialSchema,
      201,
    );
    expect(created.public_key).toMatch(/^ssh-ed25519 /);
    expect(created.fingerprint_sha256).toMatch(/^SHA256:/);
  });

  it("refuses to delete a credential in use unless forced", async () => {
    const inUse = "00000000-0000-4000-8000-000000000001";
    const refused = await errorOf(call("DELETE", `/git/credentials/${inUse}`));
    expect(refused.status).toBe(409);
    expect(refused.body.code).toBe("credential_in_use");
    expect(refused.body.projects?.length).toBe(1);
    const forced = await call("DELETE", `/git/credentials/${inUse}`, {
      query: { force: "true" },
    });
    expect(forced.status).toBe(204);
  });

  it("replacing a known host key needs the typed host name", async () => {
    const changed = await errorOf(
      call("POST", "/git/hosts/trust", {
        body: { host: "github.com", fingerprint_sha256: "SHA256:other" },
      }),
    );
    expect(changed.body.code).toBe("host_key_changed");
    expect(changed.body.expected).toMatch(/^SHA256:/);
    const confirmed = await call("POST", "/git/hosts/trust", {
      body: {
        host: "github.com",
        fingerprint_sha256: "SHA256:other",
        replace: true,
        confirm_host: "github.com",
      },
    });
    expect(confirmed.status).toBe(204);
  });

  it("serves secrets status and shared folder detection", async () => {
    resetWorld("shared_folder");
    const secrets = await parsed(
      call("GET", "/git/secrets/status"),
      SecretsStatusSchema,
    );
    expect(secrets.data_dir_shared_folder?.provider).toBe("yandex_disk");
    const found = await parsed(
      call("GET", "/git/shared-folder", {
        query: { folder: "/Users/ivan/Yandex.Disk/work" },
      }),
      SharedFolderSchema,
    );
    expect(found.detected).toBe(true);
    const none = await parsed(
      call("GET", "/git/shared-folder", {
        query: { folder: "/Users/ivan/work" },
      }),
      SharedFolderSchema,
    );
    expect(none.detected).toBe(false);
  });

  it("validates the profile with FastAPI style issues and updates the gate", async () => {
    resetWorld("no_profile");
    expect((await status()).blocked?.reason).toBe("profile_required");
    const bad = await call("PUT", "/profile", {
      body: { name: "", email: "x" },
    });
    expect(bad.status).toBe(422);
    const issues = (bad.data as { detail: { loc: string[]; code: string }[] })
      .detail;
    expect(issues.map((i) => i.loc[1])).toEqual(["name", "email"]);
    const saved = await parsed(
      call("PUT", "/profile", {
        body: { name: "Мария Орлова", email: "m.orlova@edu.hse.ru" },
      }),
      ProfileSchema,
    );
    expect(saved.commit_preview).toBe("Мария Орлова <m.orlova@edu.hse.ru>");
    const after = await status();
    expect(after.profile_ok).toBe(true);
    expect(after.blocked).toBeNull();
    const cleared = await parsed(call("DELETE", "/profile"), ProfileSchema);
    expect(cleared.is_default).toBe(true);
  });

  it("clones a repository through an operation with a result", async () => {
    const defaults = await parsed(
      call("GET", "/git/clone/defaults", { query: { name: "Курсовая" } }),
      CloneDefaultsSchema,
    );
    expect(defaults.folder).toContain("HSE Doc Studio");
    const started = await parsed(
      call("POST", "/git/clone", {
        body: {
          url: "https://github.com/ivan/coursework",
          folder: "~/p",
          credential_id: null,
        },
      }),
      OperationStartedSchema,
      202,
    );
    await vi.advanceTimersByTimeAsync(2_000);
    const mid = await operation(started.operation_id);
    expect(mid.status).toBe("running");
    expect(mid.kind).toBe("clone");
    await vi.advanceTimersByTimeAsync(5_000);
    const done = await operation(started.operation_id);
    expect(done.status).toBe("succeeded");
    expect(CloneResultSchema.parse(done.result).access).toBe("full");
  });

  it("fails a clone on a refusing address and a busy folder", async () => {
    const started = await parsed(
      call("POST", "/git/clone", {
        body: { url: "https://github.com/ivan/missing", folder: "~/p" },
      }),
      OperationStartedSchema,
      202,
    );
    await vi.advanceTimersByTimeAsync(5_000);
    const failed = await operation(started.operation_id);
    expect(failed.status).toBe("failed");
    expect(failed.error?.code).toBe("not_found_or_no_access");
    expect(
      (
        await errorOf(
          call("POST", "/git/clone", {
            body: { url: "https://github.com/ivan/x", folder: "~/busy" },
          }),
        )
      ).body.code,
    ).toBe("folder_not_empty");
  });

  it("cannot cancel an operation that is registering the project", async () => {
    const started = await parsed(
      call("POST", "/git/clone", {
        body: { url: "https://github.com/ivan/coursework", folder: "~/p" },
      }),
      OperationStartedSchema,
      202,
    );
    await vi.advanceTimersByTimeAsync(4_300);
    const failure = await errorOf(
      call("POST", `/git/operations/${started.operation_id}/cancel`),
    );
    expect(failure.body.code).toBe("operation_not_cancellable");
  });
});

describe("demo folder choice for cloning", () => {
  it("falls back to a stub for folder inspection when there is no backend", async () => {
    const fresh = await call("GET", "/fs/inspect", {
      query: { path: "~/HSE Doc Studio/paper" },
    });
    expect(fresh.status).toBe(200);
    expect(fresh.data).toMatchObject({
      exists: false,
      is_dir: true,
      has_project: false,
    });
    const busy = await call("GET", "/fs/inspect", {
      query: { path: "~/busy" },
    });
    expect(busy.data).toMatchObject({ exists: true, has_project: false });
    const taken = await call("GET", "/fs/inspect", {
      query: { path: "~/exists" },
    });
    expect(taken.data).toMatchObject({ exists: true, has_project: true });
  });

  it("answers folder browsing with a small tree when there is no backend", async () => {
    const root = await call("GET", "/fs/browse");
    expect(root.data).toMatchObject({ parent: null, is_root: true });
    const entries = (root.data as { entries: { name: string }[] }).entries;
    expect(entries.length).toBeGreaterThan(0);
  });

  it("prefers the real backend answer when it responds", async () => {
    const real = {
      path: "/real",
      exists: true,
      is_dir: true,
      has_project: false,
      project: null,
    };
    const res = await call("GET", "/fs/inspect", {
      query: { path: "/real" },
      forward: () => Promise.resolve({ data: real } as AxiosResponse),
    });
    expect(res.data).toEqual(real);
  });
});

describe("demo history enrichment", () => {
  const real = [
    {
      id: "a1",
      short_id: "a1",
      kind: "edit",
      message: "Правка введения",
      author: "Иван Смирнов",
      created_at: "2026-10-26T09:00:00Z",
      parents: ["b"],
      refs: [],
    },
    {
      id: "b1",
      short_id: "b1",
      kind: "compile",
      message: "Сборка",
      author: "Иван Смирнов",
      created_at: "2026-10-25T09:00:00Z",
      parents: [],
      refs: [],
    },
    {
      id: "c1",
      short_id: "c1",
      kind: "manual",
      message: "Рисунок",
      author: "Анна Петрова",
      created_at: "2026-10-24T09:00:00Z",
      parents: [],
      refs: [],
    },
    {
      id: "d1",
      short_id: "d1",
      kind: "edit",
      message: "Список литературы",
      author: "Анна Петрова",
      created_at: "2026-10-23T09:00:00Z",
      parents: [],
      refs: [],
    },
    {
      id: "e1",
      short_id: "e1",
      kind: "init",
      message: "Первая версия",
      author: "Иван Смирнов",
      created_at: "2026-10-22T09:00:00Z",
      parents: [],
      refs: [],
    },
  ];
  const forward = () => Promise.resolve({ data: real } as AxiosResponse);

  it("marks unpushed, pushed and incoming versions once a remote is connected", async () => {
    resetWorld("diverged");
    const res = await call("GET", `/projects/${PROJECT}/vcs/history`, {
      forward,
    });
    const commits = res.data as {
      sync: string | null;
      author_email: string;
      is_merge: boolean;
    }[];
    const marks = commits.map((c) => c.sync);
    expect(marks.filter((m) => m === "incoming")).toHaveLength(2);
    expect(marks).toContain("unpushed");
    expect(marks).toContain("pushed");
    expect(commits.every((c) => c.author_email.includes("@"))).toBe(true);
  });

  it("leaves sync empty without a remote and filters by sync and kind", async () => {
    resetWorld("not_connected");
    const plain = await call("GET", `/projects/${PROJECT}/vcs/history`, {
      forward,
    });
    expect(
      (plain.data as { sync: string | null }[]).every((c) => c.sync === null),
    ).toBe(true);
    resetWorld("ahead");
    const unpushed = await call("GET", `/projects/${PROJECT}/vcs/history`, {
      forward,
      query: { sync: "unpushed", kind: ["edit", "compile"] },
    });
    expect((unpushed.data as { kind: string }[]).map((c) => c.kind)).toEqual([
      "edit",
      "compile",
      "edit",
    ]);
  });
});

describe("demo history without a backend", () => {
  const down = () => Promise.reject(new Error("no backend"));

  it("makes up a history with sync, merge and template-update rows", async () => {
    resetWorld("ahead");
    const res = await call("GET", `/projects/${PROJECT}/vcs/history`, {
      forward: down,
    });
    const commits = res.data as {
      kind: string;
      sync: string | null;
      is_merge: boolean;
    }[];
    const kinds = new Set(commits.map((c) => c.kind));
    expect(kinds).toContain("sync");
    expect(kinds).toContain("template_update");
    expect(kinds).toContain("manual");
    expect(commits.some((c) => c.is_merge)).toBe(true);
    expect(commits.some((c) => c.sync === "unpushed")).toBe(true);
    expect(commits.some((c) => c.sync === "pushed")).toBe(true);
  });

  it("gives known people their profile e-mail so that Only mine matches", async () => {
    resetWorld("ahead");
    const res = await call("GET", `/projects/${PROJECT}/vcs/history`, {
      forward: down,
      query: { author_email: "ivan.smirnov@edu.hse.ru" },
    });
    const commits = res.data as { author: string }[];
    expect(commits.length).toBeGreaterThan(0);
    expect(commits.every((c) => c.author === "Иван Смирнов")).toBe(true);
  });

  it("filters by the date window", async () => {
    resetWorld("ahead");
    const since = new Date(Date.now() - 36 * 3_600_000).toISOString();
    const res = await call("GET", `/projects/${PROJECT}/vcs/history`, {
      forward: down,
      query: { since },
    });
    const commits = res.data as { created_at: string }[];
    expect(commits.length).toBeGreaterThan(0);
    expect(
      commits.every((c) => Date.parse(c.created_at) >= Date.parse(since)),
    ).toBe(true);
    const old = await call("GET", `/projects/${PROJECT}/vcs/history`, {
      forward: down,
      query: { until: since },
    });
    expect((old.data as unknown[]).length).toBeGreaterThan(0);
  });
});

describe("demo differences of incoming versions", () => {
  it("answers for a version that came from the repository", async () => {
    resetWorld("behind");
    const incoming = projectOf(getWorld(), PROJECT).incoming[0];
    const res = await call("GET", `/projects/${PROJECT}/vcs/diff`, {
      query: { to_id: incoming?.id ?? "" },
      forward: () => Promise.reject(new Error("must not be asked")),
    });
    const diff = res.data as {
      to_id: string;
      files: { path: string; patch: string; binary: boolean }[];
    };
    expect(diff.to_id).toBe(incoming?.id);
    expect(diff.files).toHaveLength(1);
    expect(diff.files[0]?.patch).toContain("@@");
    expect(diff.files[0]?.binary).toBe(false);
  });

  it("hands every other version to the real backend", async () => {
    resetWorld("behind");
    const res = await call("GET", `/projects/${PROJECT}/vcs/diff`, {
      query: { to_id: "abc123" },
      forward: () =>
        Promise.resolve({ data: { files: [] }, status: 200 } as AxiosResponse),
    });
    expect(res.data).toEqual({ files: [] });
  });
});

describe("history facets", () => {
  it("satisfies the shared facets schema", () => {
    expect(
      HistoryFacetsSchema.parse({
        kinds: { edit: 2 },
        authors: [{ name: "A", email: null, count: 2 }],
      }).kinds.edit,
    ).toBe(2);
  });
});

describe("demo adapter", () => {
  it("answers matched routes and hands the rest to the real transport", async () => {
    const fallback = vi.fn<AxiosAdapter>().mockImplementation((config) =>
      Promise.resolve({
        data: { real: true },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      }),
    );
    const client = axios.create({ baseURL: "/api/v1", adapter: fallback });
    resetWorld("up_to_date");
    installDemoAdapter(client, router);

    const demo = await client.get(`/projects/${PROJECT}/git`);
    expect(GitStatusSchema.parse(demo.data).connected).toBe(true);
    expect(fallback).not.toHaveBeenCalled();

    const real = await client.get("/projects");
    expect(real.data).toEqual({ real: true });
    expect(fallback).toHaveBeenCalledTimes(1);
  });

  it("rejects error statuses like a real axios failure with the body", async () => {
    const client = axios.create({
      baseURL: "/api/v1",
      adapter: vi.fn<AxiosAdapter>(),
    });
    resetWorld("no_profile");
    installDemoAdapter(client, router);
    const failure = await client
      .post(`/projects/${PROJECT}/git/sync`, {})
      .catch((e: unknown) => e);
    expect(axios.isAxiosError(failure)).toBe(true);
    if (axios.isAxiosError(failure)) {
      expect(failure.response?.status).toBe(409);
      expect(failure.response?.data).toMatchObject({
        code: "profile_required",
      });
    }
  });

  it("passes query params and repeated kinds to handlers", async () => {
    const client = axios.create({
      baseURL: "/api/v1",
      adapter: vi.fn<AxiosAdapter>(),
    });
    const handler = vi.fn().mockReturnValue({ status: 200, data: [] });
    installDemoAdapter(
      client,
      createDemoRouter([{ method: "GET", pattern: "/x/:id", handler }]),
    );
    await client.get("/x/7?a=1", {
      params: { kind: ["edit", "sync"], q: "рис" },
    });
    const request = handler.mock.calls[0]?.[0] as {
      params: Record<string, string>;
      query: Record<string, string | string[]>;
    };
    expect(request.params).toEqual({ id: "7" });
    expect(request.query).toEqual({ a: "1", kind: ["edit", "sync"], q: "рис" });
  });
});

describe("demo app settings", () => {
  it("answers with defaults and the demo interval when there is no backend", async () => {
    resetWorld("not_connected");
    const res = await call("GET", "/settings");
    expect(res.status).toBe(200);
    expect(res.data).toMatchObject({
      theme: "system",
      latex_passes: 2,
      git_fetch_interval_s: 300,
    });
  });

  it("keeps the real backend settings and only replaces the interval", async () => {
    resetWorld("not_connected");
    const forward = vi.fn(() =>
      Promise.resolve({
        data: { theme: "dark", interface_language: "en", latex_passes: 3 },
      } as AxiosResponse),
    );
    const res = await call("GET", "/settings", { forward });
    expect(res.data).toMatchObject({
      theme: "dark",
      interface_language: "en",
      latex_passes: 3,
      git_fetch_interval_s: 300,
    });
  });

  it("saves the interval in memory without bothering the backend", async () => {
    resetWorld("not_connected");
    const forward = vi.fn(() =>
      Promise.reject(new Error("must not be called")),
    );
    const saved = await call("PUT", "/settings", {
      body: { git_fetch_interval_s: 600 },
      forward,
    });
    expect(forward).not.toHaveBeenCalled();
    expect(saved.data).toMatchObject({ git_fetch_interval_s: 600 });
    const again = await call("GET", "/settings");
    expect(again.data).toMatchObject({ git_fetch_interval_s: 600 });
  });

  it("returns to the default when the scenario is reset", async () => {
    await call("PUT", "/settings", { body: { git_fetch_interval_s: 900 } });
    resetWorld("up_to_date");
    const res = await call("GET", "/settings");
    expect(res.data).toMatchObject({ git_fetch_interval_s: 300 });
  });
});
